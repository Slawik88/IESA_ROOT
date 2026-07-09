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


def _apply_luck_bonus(table: list, bonus: float) -> list:
    """Boost 'valuable' entry weights by (1 + bonus). Used for potion_luck items."""
    if bonus <= 0:
        return table
    mult = 1.0 + bonus
    return [
        {**entry, "weight": entry["weight"] * mult} if entry.get("valuable") else entry
        for entry in table
    ]


async def _consume_luck_potions(db, user_id: int) -> float:
    """Check inventory for gacha luck items. Consume one and return total bonus, or 0.
    lucky_charm переехал сюда из открытия яиц (БЛОК19 Ч.2): теперь это +15% удача на крутку."""
    for item_id in ("potion_luck_s", "potion_luck_m", "lucky_charm"):
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
            (user_id, item_id),
        ) as c:
            row = await c.fetchone()
        if row:
            from core.registry import ITEMS_REGISTRY as _REG
            item = _REG.get(item_id, {})
            buff_value = item.get("buff_value", 0.15)
            # Consume one use
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (user_id, item_id),
            )
            return buff_value
    return 0.0


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
        # H3: лочим строку игрока на весь спин — параллельные крутки не уйдут в минус
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,))
        async with db.execute("SELECT 1 FROM users WHERE user_tg_id = ? FOR UPDATE", (user_id,)) as _lk:
            await _lk.fetchone()

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
        pity_before = await gacha_repo.get_pity_locked(db, user_id, spin_type)
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
            # Apply potion_luck bonus if user has one in inventory
            luck_bonus = await _consume_luck_potions(db, user_id)
            if luck_bonus > 0:
                modified_table = _apply_luck_bonus(modified_table, luck_bonus)
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
            # Achievement: star_gacha — legendary+ drops from gacha
            legendary_count = sum(
                1 for dup in summary.get("dup_outcomes", [])
                if dup.get("rarity") == "legendary"  # mythic-питомцев нет в PET_SPECIES (M6)
            )
            if legendary_count:
                await _incr_ach(db, user_id, "legendary_gacha_drops", delta=float(legendary_count))
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
    """Perform `count` spins. Tokens have ABSOLUTE PRIORITY (same rule as
    roll_single) — up to `count` spin_token_<type> are consumed first, one
    token per spin; only the REMAINING spins (if any) are charged currency,
    at the usual 10% multi-discount. Было: всегда списывалась валюта со
    скидкой, жетоны не проверялись вообще — игрок с полным стаком жетонов
    платил Морой/Алмазами за ×10, хотя должен был крутить бесплатно.

    Returns (True, [result_dict, ...]) or (False, error_str).
    """
    cost = SPIN_COSTS.get(spin_type)
    if cost is None:
        return False, "Неизвестный тип крутки."

    count = min(count, SPIN_MULTI_COUNT)
    discount = SPIN_MULTI_DISCOUNT
    token_id = SPIN_TOKEN_IDS.get(spin_type, "")
    table = GACHA_TABLES.get(spin_type, [])

    try:
        await db.execute("BEGIN IMMEDIATE")
        # H3: лочим строку игрока на весь мульти-спин (защита от овердрафта)
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,))
        async with db.execute("SELECT 1 FROM users WHERE user_tg_id = ? FOR UPDATE", (user_id,)) as _lk:
            await _lk.fetchone()

        # ── Tokens first: up to `count` — каждый закрывает один спин бесплатно ──
        tokens_available = 0
        if token_id:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
                (user_id, token_id),
            ) as c:
                row = await c.fetchone()
            tokens_available = row[0] if row else 0
        tokens_to_use = min(count, tokens_available)
        paid_spins = count - tokens_to_use

        if tokens_to_use:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
                (tokens_to_use, user_id, token_id),
            )

        total_mora = cost["mora"] * paid_spins * (1.0 - discount)
        total_dias = cost["diamonds"] * paid_spins * (1.0 - discount)

        if paid_spins:
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

        pity_current = await gacha_repo.get_pity_locked(db, user_id, spin_type)
        results = []
        for i in range(count):
            pity_before = pity_current
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
                pity_current = 0
            else:
                pity_after = await gacha_repo.incr_pity(db, user_id, spin_type)
                pity_current = pity_after

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
                "used_token": i < tokens_to_use,
            })

        await db.commit()

        # Achievements: same tracking as roll_single, aggregated across all spins
        # in this multi-spin. Without this, 10x spins never advanced
        # gacha_spins / legendary_gacha_drops on either bot or site.
        try:
            await _incr_ach(db, user_id, "gacha_spins", delta=float(count))
            legendary_count = sum(
                1 for r in results for dup in r.get("dup_outcomes", [])
                if dup.get("rarity") == "legendary"  # mythic-питомцев нет в PET_SPECIES (M6)
            )
            if legendary_count:
                await _incr_ach(db, user_id, "legendary_gacha_drops", delta=float(legendary_count))
            await db.commit()
        except Exception:
            pass

        return True, results

    except Exception as e:
        await db.rollback()
        return False, f"Ошибка: {e}"


# ── Cosmetic theme drops ───────────────────────────────────────────────────────

# Per-spin chance of an additional rare profile-theme drop, by spin tier.
THEME_DROP_CHANCES = {"mora": 0.03, "diamond": 0.08}


async def maybe_grant_theme_drop(db, user_id: int, spin_type: str) -> dict | None:
    """Small chance to unlock a profile theme from this spin tier's pool.

    Shared by bot and FastAPI gacha handlers so the website grants the same
    cosmetic theme drops as the Telegram bot. No commit — caller must commit.
    Returns {"theme_id": str, "theme_name": str} if a theme was granted, else None.
    """
    from core.themes import THEME_GACHA_DROPS, THEMES
    from infrastructure.repositories.themes import list_owned, grant_theme

    pool = THEME_GACHA_DROPS.get(spin_type, [])
    if not pool:
        return None
    chance = THEME_DROP_CHANCES.get(spin_type, 0.02)
    if random.random() >= chance:
        return None
    try:
        owned = await list_owned(db, user_id)
        available = [t for t in pool if t not in owned]
        if not available:
            return None
        tid = random.choice(available)
        await grant_theme(db, user_id, tid)
        return {"theme_id": tid, "theme_name": THEMES.get(tid, {}).get("name", tid)}
    except Exception:
        return None
