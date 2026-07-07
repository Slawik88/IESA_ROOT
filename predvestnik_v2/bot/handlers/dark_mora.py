"""
bot/handlers/dark_mora.py
Тёмная Мора mechanics: Контрабанда + Культ Бездны.
"""
import random
from datetime import datetime, timezone, timedelta

from aiogram import Router, types
from bot.filters.text_commands import TextCmd
from infrastructure.repositories.dark_mora import (
    get_dark_mora_balance, add_dark_mora,
    get_cooldown, set_cooldown,
)
from infrastructure.repositories import economy as eco_repo
from services.utils import format_currency

from core.constants import (
    DARK_MORA_CONTRABANDA_COOLDOWN_DAYS, DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS,
    DARK_MORA_CONTRABANDA_MIN_STAKE, DARK_MORA_CONTRABANDA_MAX_STAKE,
    DARK_MORA_CONTRABANDA_SUCCESS_CHANCE, DARK_MORA_CONTRABANDA_FAIL_CHANCE,
    DARK_MORA_CONTRABANDA_MORA_PER_DARK,
    DARK_MORA_CULT_HOUR_START, DARK_MORA_CULT_HOUR_END,
    DARK_MORA_CULT_STREAK_MIN, DARK_MORA_CULT_LEVEL_MIN,
    DARK_MORA_CULT_PETS_MIN, DARK_MORA_CULT_COOLDOWN_DAYS,
    DARK_MORA_CULT_REWARD_MIN, DARK_MORA_CULT_REWARD_MAX,
)

router = Router(name="dark_mora_router")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _format_cooldown(dt: datetime) -> str:
    now = _now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = dt - now
    if diff.total_seconds() <= 0:
        return "уже доступно"
    days = diff.days
    hours, rem = divmod(diff.seconds, 3600)
    mins = rem // 60
    if days > 0:
        return f"{days}д {hours}ч"
    if hours > 0:
        return f"{hours}ч {mins}м"
    return f"{mins}м"


# ── Баланс Тёмной Моры ────────────────────────────────────────────────────────

@router.message(TextCmd(["тёмная мора", "темная мора", "тмора", "dark mora", "баланс тморы"]))
async def cmd_dark_balance(message: types.Message, db):
    user_id = message.from_user.id
    balance = await get_dark_mora_balance(db, user_id)
    await message.answer(
        f"🌑 <b>ТЁМНАЯ МОРА</b>\n\n"
        f"Баланс: <code>{balance:.0f} 🌑</code>\n\n"
        f"<i>Тёмная Мора — нелегальная валюта теневого рынка.\n"
        f"Способы получить: «бот контрабанда», «бот ритуал».</i>",
        parse_mode="HTML",
    )


# ── Контрабанда ───────────────────────────────────────────────────────────────

@router.message(TextCmd(["контрабанда"]))
async def cmd_contrabanda(message: types.Message, db, text_args: str = None):
    user_id = message.from_user.id

    # Check cooldown
    cd = await get_cooldown(db, user_id, "contrabanda")
    now = _now_utc()
    if cd:
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=timezone.utc)
        if cd > now:
            return await message.answer(
                f"🌑 <b>Контрабанда</b>\n\n"
                f"⏳ Следующая попытка через: <code>{_format_cooldown(cd)}</code>",
                parse_mode="HTML",
            )

    # Parse stake
    raw = (text_args or "").strip()
    if not raw:
        return await message.answer(
            f"🌑 <b>КОНТРАБАНДА</b>\n\n"
            f"Конвертируй Мору в Тёмную Мору.\n"
            f"• 40% успех → 1 🌑 за каждые {int(DARK_MORA_CONTRABANDA_MORA_PER_DARK)} 🪙\n"
            f"• 35% провал → теряешь половину ставки\n"
            f"• 25% поймали → теряешь всю ставку + {DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS}д бан\n\n"
            f"<code>бот контрабанда, [сумма {int(DARK_MORA_CONTRABANDA_MIN_STAKE)}-{int(DARK_MORA_CONTRABANDA_MAX_STAKE)}]</code>",
            parse_mode="HTML",
        )

    try:
        stake = float(raw.replace(" ", "").replace(",", "."))
    except ValueError:
        return await message.answer("❌ Укажи сумму числом. Пример: <code>бот контрабанда, 1500</code>", parse_mode="HTML")

    stake = round(stake)
    if stake < DARK_MORA_CONTRABANDA_MIN_STAKE or stake > DARK_MORA_CONTRABANDA_MAX_STAKE:
        return await message.answer(
            f"❌ Ставка должна быть от <code>{int(DARK_MORA_CONTRABANDA_MIN_STAKE)}</code> "
            f"до <code>{int(DARK_MORA_CONTRABANDA_MAX_STAKE)}</code> 🪙.",
            parse_mode="HTML",
        )

    # Deduct full stake upfront
    ok, err = await eco_repo.spend_mora(db, user_id, stake, source="contrabanda_stake", note="контрабанда")
    if not ok:
        return await message.answer(f"❌ {err}", parse_mode="HTML")

    roll = random.random()

    if roll < DARK_MORA_CONTRABANDA_SUCCESS_CHANCE:
        # SUCCESS: stake spent, gain dark mora
        dark_gained = max(1, int(stake / DARK_MORA_CONTRABANDA_MORA_PER_DARK))
        # Set cooldown FIRST — so if add_dark_mora fails, user can't retry for free
        cooldown_until = now + timedelta(days=DARK_MORA_CONTRABANDA_COOLDOWN_DAYS)
        await set_cooldown(db, user_id, "contrabanda", cooldown_until)
        await add_dark_mora(db, user_id, dark_gained, source="contrabanda", note=f"ставка {stake:.0f}")
        text = (
            f"🌑 <b>Контрабанда удалась!</b>\n\n"
            f"├ Потрачено: <code>{format_currency(stake)} 🪙</code>\n"
            f"├ Получено: <code>+{dark_gained} 🌑</code>\n"
            f"└ Следующая попытка: через {DARK_MORA_CONTRABANDA_COOLDOWN_DAYS} дней"
        )
    elif roll < DARK_MORA_CONTRABANDA_SUCCESS_CHANCE + DARK_MORA_CONTRABANDA_FAIL_CHANCE:
        # FAIL: return half stake — set cooldown first
        cooldown_until = now + timedelta(days=DARK_MORA_CONTRABANDA_COOLDOWN_DAYS)
        await set_cooldown(db, user_id, "contrabanda", cooldown_until)
        refund = round(stake * 0.5)
        await eco_repo.add_balance(db, user_id, mora=refund, source="contrabanda_refund", note="провал, возврат 50%")
        text = (
            f"😞 <b>Контрабанда провалилась.</b>\n\n"
            f"├ Потеряно: <code>{format_currency(stake - refund)} 🪙</code>\n"
            f"├ Возвращено: <code>{format_currency(refund)} 🪙</code>\n"
            f"└ Следующая попытка: через {DARK_MORA_CONTRABANDA_COOLDOWN_DAYS} дней"
        )
    else:
        # CAUGHT: lose all, 14-day ban
        cooldown_until = now + timedelta(days=DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS)
        await set_cooldown(db, user_id, "contrabanda", cooldown_until)
        text = (
            f"🚨 <b>Поймали!</b>\n\n"
            f"├ Потеряно: <code>{format_currency(stake)} 🪙</code> (конфисковано)\n"
            f"└ Контрабанда заблокирована на <b>{DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS} дней</b>"
        )

    await message.answer(text, parse_mode="HTML")


# ── Культ Бездны ─────────────────────────────────────────────────────────────

@router.message(TextCmd(["ритуал", "культ бездны"]))
async def cmd_ritual(message: types.Message, db):
    user_id = message.from_user.id

    # Check time window: 23:00–01:00 UTC
    hour_utc = _now_utc().hour
    in_window = (hour_utc >= DARK_MORA_CULT_HOUR_START or hour_utc < DARK_MORA_CULT_HOUR_END)
    if not in_window:
        return await message.answer(
            f"🌑 <b>Культ Бездны</b>\n\n"
            f"⏳ Ритуал доступен только в промежутке <b>23:00–01:00 UTC</b>.\n"
            f"<i>Сейчас {hour_utc:02d}:xx UTC — вернись в нужное время.</i>",
            parse_mode="HTML",
        )

    # Check monthly cooldown
    cd = await get_cooldown(db, user_id, "ritual")
    now = _now_utc()
    if cd:
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=timezone.utc)
        if cd > now:
            return await message.answer(
                f"🌑 <b>Культ Бездны</b>\n\n"
                f"⏳ Ритуал уже проводился. Следующий через: <code>{_format_cooldown(cd)}</code>",
                parse_mode="HTML",
            )

    # Check streak (max across all chats)
    async with db.execute(
        "SELECT MAX(streak) FROM daily_login WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    max_streak = int(row[0]) if row and row[0] else 0

    if max_streak < DARK_MORA_CULT_STREAK_MIN:
        return await message.answer(
            f"🌑 <b>Культ Бездны</b>\n\n"
            f"❌ Нужен стрик <b>{DARK_MORA_CULT_STREAK_MIN}+ дней</b>.\n"
            f"Твой текущий максимум: <code>{max_streak} дн.</code>",
            parse_mode="HTML",
        )

    # Check level (max across all chats)
    async with db.execute(
        "SELECT MAX(user_level) FROM user_chat_stats WHERE user_tg_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    max_level = int(row[0]) if row and row[0] else 1

    if max_level < DARK_MORA_CULT_LEVEL_MIN:
        return await message.answer(
            f"🌑 <b>Культ Бездны</b>\n\n"
            f"❌ Нужен уровень <b>{DARK_MORA_CULT_LEVEL_MIN}+</b>.\n"
            f"Твой текущий максимум: <code>Ур. {max_level}</code>",
            parse_mode="HTML",
        )

    # Check pets count (non-storage pets owned by user)
    async with db.execute(
        "SELECT COUNT(*) FROM pets WHERE owner_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    pet_count = int(row[0]) if row and row[0] else 0

    if pet_count < DARK_MORA_CULT_PETS_MIN:
        return await message.answer(
            f"🌑 <b>Культ Бездны</b>\n\n"
            f"❌ Нужно минимум <b>{DARK_MORA_CULT_PETS_MIN} питомца</b>.\n"
            f"У тебя сейчас: <code>{pet_count}</code>",
            parse_mode="HTML",
        )

    # All conditions met — set cooldown FIRST, then reward
    reward = random.randint(DARK_MORA_CULT_REWARD_MIN, DARK_MORA_CULT_REWARD_MAX)
    cooldown_until = now + timedelta(days=DARK_MORA_CULT_COOLDOWN_DAYS)
    await set_cooldown(db, user_id, "ritual", cooldown_until)
    await add_dark_mora(db, user_id, reward, source="cult_ritual", note="Культ Бездны")

    new_balance = await get_dark_mora_balance(db, user_id)

    await message.answer(
        f"🌑 <b>РИТУАЛ ЗАВЕРШЁН</b>\n\n"
        f"Тьма признала тебя своим...\n\n"
        f"├ Получено: <code>+{reward} 🌑</code>\n"
        f"├ Баланс: <code>{new_balance:.0f} 🌑</code>\n"
        f"└ Следующий ритуал через <b>{DARK_MORA_CULT_COOLDOWN_DAYS} дней</b>",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════════════════
# БЛОК 13.X/24.A: Теневой Торговец — «бот слово» + Теневые реликвии
# ═══════════════════════════════════════════════════════════════════════════

from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.constants import (
    DARK_MORA_SHADOW_MERCHANT_WINNERS,
    DARK_MORA_SHADOW_MERCHANT_REWARD_MIN, DARK_MORA_SHADOW_MERCHANT_REWARD_MAX,
)
from core.registry import SHADOW_RELICS
from infrastructure.repositories import shadow_merchant as sm_repo
from services import shadow_merchant as sm_svc

# Награда 🌑 по месту: 1-е — MAX, 3-е — MIN, 2-е — середина.
_SM_REWARDS: dict[int, int] = {
    1: DARK_MORA_SHADOW_MERCHANT_REWARD_MAX,
    2: (DARK_MORA_SHADOW_MERCHANT_REWARD_MIN + DARK_MORA_SHADOW_MERCHANT_REWARD_MAX) // 2,
    3: DARK_MORA_SHADOW_MERCHANT_REWARD_MIN,
}
_SM_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


@router.message(TextCmd(["слово"]))
async def cmd_shadow_word(message: types.Message, db, text_args: str = None):
    """«бот слово, догадка» — ответ на пророчество Теневого Торговца."""
    if message.chat.type == "private":
        return await message.answer("🕴 Торговец является только в группах.")
    guess = (text_args or "").strip()
    if not guess:
        return await message.answer(
            "Формат: <code>бот слово, [догадка]</code>", parse_mode="HTML")

    event = await sm_repo.get_active_event(db, message.chat.id)
    if not event:
        return await message.answer(
            "🕴 <i>Торговца сейчас нет в этом чате. Пророчество появляется само —"
            " следите за чатом.</i>", parse_mode="HTML")

    if not sm_svc.keywords_match(guess, event["keyword"]):
        return await message.answer("❌ <i>Не то слово…</i>", parse_mode="HTML")

    result = await sm_repo.add_winner(
        db, event["id"], message.from_user.id,
        DARK_MORA_SHADOW_MERCHANT_WINNERS, _SM_REWARDS,
    )
    if result is None:
        return await message.answer(
            "⏳ Места победителей уже заняты (или вы уже угадали).", parse_mode="HTML")

    position, reward = result
    if reward > 0:
        await add_dark_mora(db, message.from_user.id, reward,
                            source="shadow_merchant", note=f"place_{position}")
    await db.commit()

    medal = _SM_MEDALS.get(position, "🏅")
    name = message.from_user.first_name or "Игрок"
    text = (
        f"{medal} <b>{name}</b> разгадал пророчество! (место {position})\n"
        f"🌑 Награда: <b>+{reward:.0f}</b> Тёмной Моры\n"
        f"🗝 Получено <b>право купить Теневую реликвию</b>: "
        f"<code>бот теневые реликвии</code>"
    )
    if position >= DARK_MORA_SHADOW_MERCHANT_WINNERS:
        text += "\n\n🕴 <i>Все места заняты — Торговец растворяется во мгле…</i>"
    await message.answer(text, parse_mode="HTML")


class SRelicBuyCB(CallbackData, prefix="srelic"):
    relic_id: str


@router.message(TextCmd(["теневые реликвии", "теневая лавка", "теневая реликвия"]))
async def cmd_shadow_relics(message: types.Message, db):
    """Каталог Теневых реликвий: владение, ваучеры, покупка."""
    uid = message.from_user.id
    owned = set(await sm_repo.owned_shadow_relics(db, uid))
    vouchers = await sm_repo.voucher_count(db, uid)
    bal = await get_dark_mora_balance(db, uid)

    lines = ["🕴 <b>ТЕНЕВАЯ ЛАВКА</b>", ""]
    for rid, r in SHADOW_RELICS.items():
        mark = "✅" if rid in owned else f"{r['price_dark']:.0f} 🌑"
        lines.append(f"{r['name']} — {mark}")
        lines.append(f"   <i>{r['desc']}</i> (+{r['gates_dark_pct'] * 100:.0f}% 🌑 из Врат)")
    lines += [
        "",
        f"🗝 Ваших прав покупки (побед): <b>{vouchers}</b>",
        f"🌑 Баланс: <b>{format_currency(bal)}</b>",
        "",
        "<i>Право покупки даёт только победа в ивенте «Теневой Торговец».</i>",
    ]

    kb = InlineKeyboardBuilder()
    if vouchers > 0:
        for rid, r in SHADOW_RELICS.items():
            if rid not in owned:
                kb.button(text=f"Купить {r['name']}",
                          callback_data=SRelicBuyCB(relic_id=rid))
        kb.adjust(1)
    await message.answer("\n".join(lines), parse_mode="HTML",
                         reply_markup=kb.as_markup() if vouchers > 0 else None)


@router.callback_query(SRelicBuyCB.filter())
async def cb_shadow_relic_buy(query: types.CallbackQuery, callback_data: SRelicBuyCB, db):
    ok, msg = await sm_repo.buy_shadow_relic(db, query.from_user.id, callback_data.relic_id)
    await db.commit()
    if ok:
        await query.answer("🗝 Куплено!", show_alert=False)
        await query.message.answer(f"🕴 {msg}", parse_mode="HTML")
    else:
        await query.answer(msg, show_alert=True)
