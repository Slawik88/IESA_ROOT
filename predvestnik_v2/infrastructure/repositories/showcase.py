"""
infrastructure/repositories/showcase.py — Витрина недели.

Каждый понедельник (ISO-неделя) — 5 случайных shop-косметик разных слотов со
скидкой 10–30%. Каждый товар изначально «тёмная карточка»: игрок видит только
слот и цвет редкости, тап по карточке раскрывает предмет и цену (reveal хранится
на сервере — синхронно между устройствами). 1 покупка слота на игрока в неделю.
Генерация ленивая и детерминированная (seed = week_key) — крон не нужен,
оба процесса (бот/веб) построят одинаковую витрину без гонки благодаря
ON CONFLICT DO NOTHING.
"""
import json
import random
from datetime import datetime, timezone

from core.cosmetics import COSMETICS

SHOWCASE_SLOTS = 5
SHOWCASE_DISCOUNT_MIN = 10   # %
SHOWCASE_DISCOUNT_MAX = 30   # %


def week_key() -> str:
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"W{iso[0]}-{iso[1]:02d}"


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS weekly_showcase (
            week_key     TEXT PRIMARY KEY,
            slots_json   TEXT NOT NULL,
            generated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS showcase_state (
            user_id   BIGINT NOT NULL,
            week_key  TEXT NOT NULL,
            slot_idx  INTEGER NOT NULL,
            revealed  BOOLEAN NOT NULL DEFAULT FALSE,
            purchased BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (user_id, week_key, slot_idx)
        )
    """)
    await db.commit()


def _generate_slots(wk: str) -> list[dict]:
    """5 предметов разных слотов из shop-пула, скидка на каждый — детерминированно
    от week_key (оба процесса построят одну и ту же витрину)."""
    rng = random.Random(wk)
    by_slot: dict[str, list[str]] = {}
    for cid, cos in COSMETICS.items():
        if cos.get("source") == "shop" and cos.get("price"):
            by_slot.setdefault(cos["slot"], []).append(cid)
    slots_order = [s for s in by_slot if by_slot[s]]
    rng.shuffle(slots_order)
    picked: list[dict] = []
    for slot in slots_order[:SHOWCASE_SLOTS]:
        cid = rng.choice(sorted(by_slot[slot]))  # sorted: стабильность выбора
        picked.append({
            "cosmetic_id": cid,
            "discount_pct": rng.randint(SHOWCASE_DISCOUNT_MIN, SHOWCASE_DISCOUNT_MAX),
        })
    return picked


async def get_week_slots(db, wk: str) -> list[dict]:
    """Слоты витрины недели; создаёт при первом обращении (идемпотентно)."""
    async with db.execute(
        "SELECT slots_json FROM weekly_showcase WHERE week_key = ?", (wk,)
    ) as c:
        row = await c.fetchone()
    if row:
        return json.loads(row[0])
    slots = _generate_slots(wk)
    await db.execute(
        "INSERT INTO weekly_showcase (week_key, slots_json) VALUES (?, ?) "
        "ON CONFLICT (week_key) DO NOTHING",
        (wk, json.dumps(slots, ensure_ascii=False)),
    )
    await db.commit()
    # Перечитываем: при гонке двух процессов выигравшая версия — единая истина
    async with db.execute(
        "SELECT slots_json FROM weekly_showcase WHERE week_key = ?", (wk,)
    ) as c:
        row = await c.fetchone()
    return json.loads(row[0]) if row else slots


async def get_user_state(db, user_id: int, wk: str) -> dict[int, dict]:
    async with db.execute(
        "SELECT slot_idx, revealed, purchased FROM showcase_state "
        "WHERE user_id = ? AND week_key = ?",
        (user_id, wk),
    ) as c:
        return {r["slot_idx"]: {"revealed": bool(r["revealed"]),
                                "purchased": bool(r["purchased"])}
                for r in await c.fetchall()}


async def reveal(db, user_id: int, wk: str, slot_idx: int) -> None:
    await db.execute(
        "INSERT INTO showcase_state (user_id, week_key, slot_idx, revealed) "
        "VALUES (?, ?, ?, TRUE) "
        "ON CONFLICT (user_id, week_key, slot_idx) DO UPDATE SET revealed = TRUE",
        (user_id, wk, slot_idx),
    )
    await db.commit()


async def mark_purchased(db, user_id: int, wk: str, slot_idx: int) -> None:
    await db.execute(
        "UPDATE showcase_state SET purchased = TRUE "
        "WHERE user_id = ? AND week_key = ? AND slot_idx = ?",
        (user_id, wk, slot_idx),
    )
    await db.commit()
