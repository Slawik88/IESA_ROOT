"""FastAPI/routers/showcase.py — Витрина недели.

5 тёмных карточек косметики со скидкой 10–30%, ротация раз в ISO-неделю.
Скрытность до reveal и скидочная цена считаются ТОЛЬКО на сервере."""
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.cosmetics import COSMETICS
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.repositories import showcase as sc_repo
from infrastructure.repositories.economy_ledger import apply_balance_change, find_reference_replay
from services.cosmetics import buy as cosmetics_buy

router = APIRouter(prefix="/showcase", tags=["showcase"])

# Block 14 (стимул покупок): бонус комплекта «весь набор» — от 200✨ (2 предмета)
# до 400✨ (полный набор из SHOWCASE_SLOTS). Плюс пол цены: не дешевле 60% суммы
# (макс 40% off), чтобы наборы не уходили в бесценок — «не так дёшево».
SHOWCASE_BUNDLE_MIN = 200
SHOWCASE_BUNDLE_MAX = 400


def _bundle_discount(count: int) -> int:
    """✨-бонус за комплект, линейно 200 (2 предмета) → 400 (полный набор)."""
    slots = sc_repo.SHOWCASE_SLOTS
    if count <= 2:
        return SHOWCASE_BUNDLE_MIN
    if count >= slots:
        return SHOWCASE_BUNDLE_MAX
    step = (SHOWCASE_BUNDLE_MAX - SHOWCASE_BUNDLE_MIN) / (slots - 2)
    return round(SHOWCASE_BUNDLE_MIN + (count - 2) * step)


def _bundle_price(disc_sum: int, count: int) -> int:
    return max(round(disc_sum * 0.6), disc_sum - _bundle_discount(count), 1)


async def _owned_ids(db, user_id: int) -> set[str]:
    async with db.execute(
        "SELECT cosmetic_id FROM user_cosmetics WHERE user_id = ?", (user_id,)
    ) as c:
        return {r[0] for r in await c.fetchall()}


def _zarniki_price(cos: dict) -> int:
    """Базовая ✨-цена предмета (все shop-предметы имеют зарниковый вариант)."""
    for opt in cos.get("price") or []:
        if "zarniki" in opt:
            return int(opt["zarniki"])
    return 0


def _discounted(base: int, pct: int) -> int:
    return max(1, int(math.floor(base * (100 - pct) / 100)))


def _seconds_to_next_week() -> int:
    """Секунды до следующего понедельника 00:00 UTC (смена week_key).
    (8 − isoweekday) % 7 → Вт=6 … Вс=1; 0 (сам понедельник) → 7."""
    now = datetime.now(timezone.utc)
    days_ahead = (8 - now.isoweekday()) % 7 or 7
    next_monday = (now + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return int((next_monday - now).total_seconds())


@router.get("/")
async def get_showcase(db=Depends(get_db), user=Depends(require_tg_user)):
    wk = sc_repo.week_key()
    slots = await sc_repo.get_week_slots(db, wk)
    state = await sc_repo.get_user_state(db, user["id"], wk)
    out = []
    for i, s in enumerate(slots):
        cos = COSMETICS.get(s["cosmetic_id"])
        if not cos:
            continue  # предмет убран из реестра после генерации недели
        st = state.get(i, {})
        revealed = st.get("revealed", False)
        base = _zarniki_price(cos)
        item = {
            "slot_idx": i,
            "slot": cos["slot"],
            "rarity": cos["rarity"],
            "revealed": revealed,
            "purchased": st.get("purchased", False),
        }
        if revealed:
            item.update({
                "cosmetic_id": s["cosmetic_id"],
                "name": cos["name"],
                "discount_pct": s["discount_pct"],
                "price_base": base,
                "price": _discounted(base, s["discount_pct"]),
            })
        out.append(item)

    # Комплект «весь набор» (block 14): агрегат по ещё не купленным и не имеющимся
    # предметам витрины — сумма недельных скидок минус бонус комплекта. Считаем по
    # ВСЕМ слотам (не только раскрытым) — цену показываем общей суммой, отдельные
    # предметы не раскрываем. Нужно ≥2 предмета, иначе «комплекта» нет.
    owned = await _owned_ids(db, user["id"])
    b_base = b_disc = b_count = 0
    for i, s in enumerate(slots):
        cos = COSMETICS.get(s["cosmetic_id"])
        if not cos or state.get(i, {}).get("purchased") or s["cosmetic_id"] in owned:
            continue
        base = _zarniki_price(cos)
        b_base += base
        b_disc += _discounted(base, s["discount_pct"])
        b_count += 1
    bundle = None
    if b_count >= 2:
        bp = _bundle_price(b_disc, b_count)
        bundle = {"count": b_count, "price": bp, "sum": b_disc,
                  "base_sum": b_base, "savings": b_base - bp}

    return {"week": wk, "slots": out, "rotates_in_sec": _seconds_to_next_week(),
            "bundle": bundle}


class SlotRequest(BaseModel):
    slot_idx: int


@router.post("/reveal")
async def reveal_slot(body: SlotRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    wk = sc_repo.week_key()
    slots = await sc_repo.get_week_slots(db, wk)
    if not (0 <= body.slot_idx < len(slots)):
        raise HTTPException(400, "Нет такого слота витрины.")
    await sc_repo.reveal(db, user["id"], wk, body.slot_idx)
    s = slots[body.slot_idx]
    cos = COSMETICS.get(s["cosmetic_id"])
    if not cos:
        raise HTTPException(404, "Предмет недели больше не существует.")
    base = _zarniki_price(cos)
    return {
        "cosmetic_id": s["cosmetic_id"],
        "name": cos["name"],
        "slot": cos["slot"],
        "rarity": cos["rarity"],
        "discount_pct": s["discount_pct"],
        "price_base": base,
        "price": _discounted(base, s["discount_pct"]),
    }


@router.post("/buy")
async def buy_slot(
    body: SlotRequest, db=Depends(get_db), user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    key = request_key.strip()
    if not key or len(key) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    wk = sc_repo.week_key()
    slots = await sc_repo.get_week_slots(db, wk)
    if not (0 <= body.slot_idx < len(slots)):
        raise HTTPException(400, "Нет такого слота витрины.")
    state = await sc_repo.get_user_state(db, user["id"], wk)
    st = state.get(body.slot_idx, {})
    if not st.get("revealed"):
        raise HTTPException(400, "Сначала открой карточку — покупка вслепую недоступна.")
    if st.get("purchased"):
        return {"ok": True, "message": "Эта покупка уже обработана.", "price": 0}

    s = slots[body.slot_idx]
    cos = COSMETICS.get(s["cosmetic_id"])
    if not cos:
        raise HTTPException(404, "Предмет недели больше не существует.")
    price = _discounted(_zarniki_price(cos), s["discount_pct"])
    ok, msg = await cosmetics_buy(
        db, user["id"], s["cosmetic_id"], price_override={"zarniki": price},
        idempotency_key=f"showcase-slot:{key}",
    )
    if not ok:
        raise HTTPException(400, msg)
    await sc_repo.mark_purchased(db, user["id"], wk, body.slot_idx)
    return {"ok": True, "message": msg, "price": price}


@router.post("/buy-bundle")
async def buy_bundle(
    db=Depends(get_db), user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    """Купить «весь набор» витрины одним действием со скидкой комплекта (block 14).
    Берёт все ещё не купленные и не имеющиеся предметы, раскрывает их и выдаёт за
    (сумма недельных скидок − бонус комплекта). Атомарно, цена считается на сервере."""
    uid = user["id"]
    wk = sc_repo.week_key()
    key = request_key.strip()
    if not key or len(key) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    operation_key = f"showcase-bundle:{key}"
    eligible: list[tuple[int, str]] = []
    price = 0
    try:
        async with db.connection.transaction():
            await db.execute(
                "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (uid,)
            )
            async with db.execute(
                "SELECT 1 FROM users WHERE user_tg_id = ? FOR UPDATE", (uid,)
            ) as cursor:
                await cursor.fetchone()
            replay = await find_reference_replay(
                db, uid,
                reason_code="showcase_bundle_purchase",
                idempotency_key=operation_key,
                source_type="cosmetics", reference_type="showcase_week",
                reference_id=wk,
            )
            if replay is not None:
                paid = int(abs(replay.deltas.get("zarniki", 0)))
                return {"ok": True, "count": 0, "price": paid,
                        "message": "Покупка набора уже обработана."}

            slots = await sc_repo.get_week_slots(db, wk)
            state = await sc_repo.get_user_state(db, uid, wk)
            owned = await _owned_ids(db, uid)
            disc_sum = 0
            for index, slot in enumerate(slots):
                cos = COSMETICS.get(slot["cosmetic_id"])
                if not cos or state.get(index, {}).get("purchased") or slot["cosmetic_id"] in owned:
                    continue
                eligible.append((index, slot["cosmetic_id"]))
                disc_sum += _discounted(_zarniki_price(cos), slot["discount_pct"])
            if len(eligible) < 2:
                raise HTTPException(400, "Комплект доступен, когда осталось хотя бы 2 предмета.")
            price = _bundle_price(disc_sum, len(eligible))
            await apply_balance_change(
                db, uid, {"zarniki": -price},
                reason_code="showcase_bundle_purchase",
                idempotency_key=operation_key,
                source_type="cosmetics", reference_type="showcase_week",
                reference_id=wk,
                metadata={"week": wk, "cosmetic_ids": [cid for _, cid in eligible]},
                note=f"showcase:{wk}×{len(eligible)}",
            )
            for index, cosmetic_id in eligible:
                await db.execute(
                    "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
                    "ON CONFLICT DO NOTHING", (uid, cosmetic_id))
                await db.execute(
                    "INSERT INTO showcase_state (user_id, week_key, slot_idx, revealed, purchased) "
                    "VALUES (?, ?, ?, TRUE, TRUE) ON CONFLICT (user_id, week_key, slot_idx) "
                    "DO UPDATE SET revealed = TRUE, purchased = TRUE", (uid, wk, index))
    except InsufficientBalance:
        raise HTTPException(400, f"Недостаточно Зарников: нужно {price}✨.")
    except IdempotencyConflict:
        raise HTTPException(400, "Этот запрос уже использован для другого набора.")

    # Ачивка «Модник» — весь набор разом (вне транзакции покупки, самокоммит).
    try:
        from services.achievements import increment_metric
        await increment_metric(db, uid, "cosmetics_bought", delta=float(len(eligible)))
        await db.commit()
    except Exception:
        pass

    return {"ok": True, "count": len(eligible), "price": price,
            "message": f"🎁 Куплен весь набор ({len(eligible)} шт.) за {price}✨!"}
