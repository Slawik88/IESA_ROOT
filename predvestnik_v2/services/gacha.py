"""
services/gacha.py
Pure gacha business logic.
No bot/django imports. All DB writes happen inside one transaction per roll.
"""
import random

from core.constants import (
    SPIN_COSTS, SPIN_MULTI_DISCOUNT, SPIN_MULTI_COUNT,
    PITY_SOFT, PITY_HARD, SPIN_TOKEN_IDS,
)
from core.registry import GACHA_TABLES, PITY_HARD_REWARD, PET_SPECIES
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import gacha as gacha_repo
from infrastructure.repositories.zoo import grant_duplicate
from services.achievements import increment_metric as _incr_ach


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _apply_pity_modifier(table: list, pity_count: int, soft_threshold: int) -> list:
    """Return a copy of the table with doubled weights on 'valuable' entries
    once the soft pity threshold has been reached."""
    if pity_count < soft_threshold:
        return table
    return [
        {**entry, "weight": entry["weight"] * 2} if entry.get("valuable") else entry
        for entry in table
    ]


def _choose_entry(table: list) -> dict:
    total = sum(e["weight"] for e in table)
    r = random.uniform(0, total)
    cumulative = 0.0
    for entry in table:
        cumulative += entry["weight"]
        if r <= cumulative:
            return entry
    return table[-1]


async def _apply_entry(db, user_id: int, entry: dict) -> dict:
    """Apply one drop entry to the user account (no commit).
    Returns a human-readable summary dict."""
    summary: dict = {
        "type": entry["type"],
        "mora": 0.0,
        "diamonds": 0.0,
        "items": [],      # [{"id": str, "qty": int, "name": str}]
        "dup_outcomes": [],  # from grant_duplicate
    }

    async def _add(item_id: str, qty: int) -> None:
        from core.registry import ITEMS_REGISTRY
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (user_id, item_id, qty, qty),
        )
        name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        summary["items"].append({"id": item_id, "qty": qty, "name": name})

    etype = entry["type"]

    if etype == "mora":
        amount = float(random.randint(entry["min"], entry["max"]))
        await eco_repo.add_balance(db, user_id, mora=amount, commit=False, source="gacha_drop")
        summary["mora"] = amount

    elif etype == "item":
        await _add(entry["id"], entry.get("qty", 1))

    elif etype == "combo":
        for it in entry.get("items", []):
            await _add(it["id"], it.get("qty", 1))
        if entry.get("diamond_bonus", 0) > 0:
            bonus = float(entry["diamond_bonus"])
            await eco_repo.add_balance(db, user_id, diamonds=bonus, commit=False, source="gacha_drop")
            summary["diamonds"] += bonus

    elif etype == "diamond":
        qty = float(entry.get("qty", 1))
        await eco_repo.add_balance(db, user_id, diamonds=qty, commit=False, source="gacha_drop")
        summary["diamonds"] = qty

    elif etype in ("pet_dup", "pet_dup_multi"):
        rarity = entry["rarity"]
        count = entry.get("count", 1)
        species_pool = [s for s, d in PET_SPECIES.items() if d["rarity"] == rarity]
        for _ in range(count):
            species_id = random.choice(species_pool)
            dup = await grant_duplicate(db, user_id, species_id)
            dup["species_id"] = species_id
            dup["species_name"] = PET_SPECIES.get(species_id, {}).get("name", species_id)
            summary["dup_outcomes"].append(dup)
            # Overflow compensation: grant mora/stardust
            if dup["outcome"] == "overflow" and dup.get("overflow"):
                ov = dup["overflow"]
                if ov["mora"] > 0:
                    await eco_repo.add_balance(db, user_id, mora=ov["mora"], commit=False)
                    summary["mora"] += ov["mora"]
                if ov.get("stardust", 0) > 0:
                    await _add("star_dust_s", ov["stardust"])

    return summary


# ── Public roll functions ─────────────────────────────────────────────────────

async def get_token_count(db, user_id: int, spin_type: str) -> int:
    """Return how many spin tokens of this type the user owns."""
    token_id = SPIN_TOKEN_IDS.get(spin_type, "")
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
        (user_id, token_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def roll_single(
    db,
    user_id: int,
    spin_type: str,
) -> tuple[bool, dict | str]:
    """Perform one spin.

    Tokens are ALWAYS used first automatically: if the user has a
    spin_token_<type> in inventory, it is consumed instead of mora/diamonds.

    Returns:
        (True, result_dict) on success, (False, error_str) on failure.

    result_dict keys:
        spin_type, mora, diamonds, items, dup_outcomes,
        pity_before, pity_after, hard_pity_triggered, is_valuable, used_token
    """
    cost = SPIN_COSTS.get(spin_type)
    if cost is None:
        return False, "Неизвестный тип крутки."

    table = GACHA_TABLES.get(spin_type, [])
    if not table:
        return False, "Таблица крутки не найдена."

    token_id = SPIN_TOKEN_IDS.get(spin_type, "")

    try:
        await db.execute("BEGIN IMMEDIATE")

        # ── Deduct cost: tokens have ABSOLUTE PRIORITY ────────────────────────
        used_token = False
        if token_id:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
                (user_id, token_id),
            ) as c:
                row = await c.fetchone()
            if row:
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 "
                    "WHERE user_id = ? AND item_id = ?",
                    (user_id, token_id),
                )
                used_token = True

        gacha_source = f"gacha_{spin_type}"
        if not used_token:
            bal = await eco_repo.get_balance(db, user_id)
            if cost["mora"] > 0 and bal["user_balance_mora"] < cost["mora"]:
                await db.rollback()
                return False, f"Недостаточно Моры (нужно {cost['mora']:.0f} 🪙)."
            if cost["diamonds"] > 0 and bal["user_balance_diamonds"] < cost["diamonds"]:
                await db.rollback()
                return False, f"Недостаточно Алмазов (нужно {cost['diamonds']:.0f} 💎)."
            if cost["mora"] > 0:
                await eco_repo.add_balance(db, user_id, mora=-cost["mora"], commit=False,
                                           source=gacha_source)
            if cost["diamonds"] > 0:
                await eco_repo.add_balance(db, user_id, diamonds=-cost["diamonds"], commit=False,
                                           source=gacha_source)

        # ── Pity check ────────────────────────────────────────────────────────
        pity_before = await gacha_repo.get_pity(db, user_id, spin_type)
        hard_pity_triggered = False
        chosen: dict

        if pity_before + 1 >= PITY_HARD[spin_type]:
            chosen = dict(PITY_HARD_REWARD[spin_type])
            chosen["valuable"] = True
            hard_pity_triggered = True
        else:
            modified_table = _apply_pity_modifier(
                table, pity_before, PITY_SOFT[spin_type]
            )
            chosen = _choose_entry(modified_table)

        # ── Apply drop ────────────────────────────────────────────────────────
        summary = await _apply_entry(db, user_id, chosen)

        # ── Update pity ───────────────────────────────────────────────────────
        is_valuable = chosen.get("valuable", False)
        if hard_pity_triggered or is_valuable:
            await gacha_repo.reset_pity(db, user_id, spin_type)
            pity_after = 0
        else:
            pity_after = await gacha_repo.incr_pity(db, user_id, spin_type)

        # ── Log ───────────────────────────────────────────────────────────────
        await gacha_repo.log_history(db, user_id, spin_type, {
            "type": summary["type"],
            "mora": summary["mora"],
            "diamonds": summary["diamonds"],
            "items": [i["id"] for i in summary["items"]],
            "dup_count": len(summary["dup_outcomes"]),
        })

        await db.commit()
        # Achievement: gacha_spins
        try:
            await _incr_ach(db, user_id, "gacha_spins", delta=1.0)
            await db.commit()
        except Exception:
            pass

        return True, {
            "spin_type": spin_type,
            **summary,
            "pity_before": pity_before,
            "pity_after": pity_after,
            "hard_pity_triggered": hard_pity_triggered,
            "is_valuable": is_valuable,
            "used_token": used_token,
        }

    except Exception as e:
        await db.rollback()
        return False, f"Ошибка: {e}"


async def roll_multi(
    db,
    user_id: int,
    spin_type: str,
    count: int = 10,
) -> tuple[bool, list | str]:
    """Perform `count` spins at a 10% discount. Deducts cost up-front.

    Returns (True, [result_dict, ...]) or (False, error_str).
    """
    cost = SPIN_COSTS.get(spin_type)
    if cost is None:
        return False, "Неизвестный тип крутки."

    count = min(count, SPIN_MULTI_COUNT)
    discount = SPIN_MULTI_DISCOUNT
    total_mora = cost["mora"] * count * (1.0 - discount)
    total_dias = cost["diamonds"] * count * (1.0 - discount)
    table = GACHA_TABLES.get(spin_type, [])

    try:
        await db.execute("BEGIN IMMEDIATE")

        bal = await eco_repo.get_balance(db, user_id)
        if total_mora > 0 and bal["user_balance_mora"] < total_mora:
            await db.rollback()
            return False, f"Недостаточно Моры (нужно {total_mora:.0f} 🪙)."
        if total_dias > 0 and bal["user_balance_diamonds"] < total_dias:
            await db.rollback()
            return False, f"Недостаточно Алмазов (нужно {total_dias:.0f} 💎)."

        if total_mora > 0:
            await eco_repo.add_balance(db, user_id, mora=-total_mora, commit=False)
        if total_dias > 0:
            await eco_repo.add_balance(db, user_id, diamonds=-total_dias, commit=False)

        results = []
        for _ in range(count):
            pity_before = await gacha_repo.get_pity(db, user_id, spin_type)
            hard_pity_triggered = False

            if pity_before + 1 >= PITY_HARD[spin_type]:
                chosen = dict(PITY_HARD_REWARD[spin_type])
                chosen["valuable"] = True
                hard_pity_triggered = True
            else:
                modified_table = _apply_pity_modifier(
                    table, pity_before, PITY_SOFT[spin_type]
                )
                chosen = _choose_entry(modified_table)

            summary = await _apply_entry(db, user_id, chosen)

            is_valuable = chosen.get("valuable", False)
            if hard_pity_triggered or is_valuable:
                await gacha_repo.reset_pity(db, user_id, spin_type)
                pity_after = 0
            else:
                pity_after = await gacha_repo.incr_pity(db, user_id, spin_type)

            await gacha_repo.log_history(db, user_id, spin_type, {
                "type": summary["type"],
                "mora": summary["mora"],
                "diamonds": summary["diamonds"],
                "items": [i["id"] for i in summary["items"]],
                "dup_count": len(summary["dup_outcomes"]),
            })

            results.append({
                "spin_type": spin_type,
                **summary,
                "pity_before": pity_before,
                "pity_after": pity_after,
                "hard_pity_triggered": hard_pity_triggered,
                "is_valuable": is_valuable,
            })

        await db.commit()
        return True, results

    except Exception as e:
        await db.rollback()
        return False, f"Ошибка: {e}"
