"""
bot/handlers/events_info.py
Команда «бот ивент» — показывает статус и расписание ближайших ивентов.
Dev-команды для принудительного запуска.
"""
from datetime import datetime, timedelta, timezone

from aiogram import Router, types, Bot
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import (
    CHEST_DURATION_SECONDS,
    CHEST_SPAWN_MIN_HOURS, CHEST_SPAWN_MAX_HOURS, CHEST_MAX_CLAIMANTS,
    CHEST_REWARDS_BY_POSITION,
    EXCHANGE_RATE_MORA_PER_DIAMOND, EXCHANGE_RATE_MORA_PER_DIAMOND_SELL,
    EXCHANGE_DAILY_CAP_DIAMONDS,
    DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS,
    DARK_MORA_CONTRABANDA_COOLDOWN_DAYS,
    DARK_MORA_CULT_COOLDOWN_DAYS,
)
from infrastructure.repositories.chest_events import create_chest
from infrastructure.repositories.exchange import (
    get_active_event as _get_active_exchange,
    create_event as _create_exchange_event,
    activate_event as _activate_exchange_event,
)

router = Router(name="events_info_router")


def _fmt_dt(dt_str: str | None, tz_offset: int = 0) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS' UTC string to local time display."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.strptime(str(dt_str)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt + timedelta(hours=tz_offset)
        sign = "+" if tz_offset >= 0 else ""
        tz_label = f"UTC{sign}{tz_offset}"
        return local.strftime(f"%d.%m %H:%M ({tz_label})")
    except Exception:
        return str(dt_str)[:16]


def _time_until(dt_str: str | None) -> str:
    """Returns '2 ч. 15 мин.' until dt_str (UTC)."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.strptime(str(dt_str)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        diff = dt - datetime.now(timezone.utc)
        if diff.total_seconds() < 0:
            return "уже идёт"
        total_min = int(diff.total_seconds() // 60)
        h, m = divmod(total_min, 60)
        if h > 24:
            days = h // 24
            return f"~{days} дн."
        if h:
            return f"{h} ч. {m} мин."
        return f"{m} мин."
    except Exception:
        return "—"


@router.message(TextCmd(["ивент", "событие", "ивенты", "события"]))
async def cmd_events_info(message: types.Message, db):
    if message.chat.type == "private":
        return

    # ── Currency exchanger (постоянный, БЛОК 2.2) ─────────────────────────────
    ex_status = (
        f"✅ <b>ДОСТУПЕН ВСЕГДА</b>\n"
        f"   ├ 🛒 Покупка: <code>{int(EXCHANGE_RATE_MORA_PER_DIAMOND)} 🪙 = 1 💎</code>\n"
        f"   ├ 💸 Продажа: <code>1 💎 = {int(EXCHANGE_RATE_MORA_PER_DIAMOND_SELL)} 🪙</code>\n"
        f"   ├ Лимит: <code>{int(EXCHANGE_DAILY_CAP_DIAMONDS)} 💎/день</code> в каждую сторону\n"
        f"   └ Команда: <code>бот обмен</code> или клик на 🪙/💎 в профиле"
    )

    # ── Chest event ───────────────────────────────────────────────────────────
    top3_reward = CHEST_REWARDS_BY_POSITION.get(1, 300)
    chest_status = (
        f"🎲 Появляются случайно каждые {CHEST_SPAWN_MIN_HOURS}–{CHEST_SPAWN_MAX_HOURS} ч.\n"
        f"   ├ 🥇 1 место: <b>{int(top3_reward)} 🪙</b> + 🎟 Жетон\n"
        f"   ├ 🥈 2 место: <b>{int(CHEST_REWARDS_BY_POSITION.get(2, 260))} 🪙</b> + 🎟 Жетон\n"
        f"   ├ 🥉 3 место: <b>{int(CHEST_REWARDS_BY_POSITION.get(3, 220))} 🪙</b> + 🎟 Жетон\n"
        f"   └ 4–15 место: <b>{int(CHEST_REWARDS_BY_POSITION.get(15, 30))}–"
        f"{int(CHEST_REWARDS_BY_POSITION.get(4, 190))} 🪙</b>"
    )

    # ── Dark Mora events ──────────────────────────────────────────────────────
    dark_status = (
        f"🕵️ Теневой Торговец — раз в {DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS} дня\n"
        f"   └ Пророчество в чате → <code>бот слово, [догадка]</code> → 🌑 + реликвия\n"
        f"🎲 Контрабанда — КД {DARK_MORA_CONTRABANDA_COOLDOWN_DAYS} дней\n"
        f"   └ <code>бот контрабанда, [сумма]</code>\n"
        f"🌑 Культ Бездны — раз в {DARK_MORA_CULT_COOLDOWN_DAYS} дней (23:00–01:00 UTC)\n"
        f"   └ <code>бот ритуал</code>"
    )

    text = (
        "🗓 <b>ИВЕНТЫ ПРЕДВЕСТНИКА</b>\n\n"
        "💱 <b>ОБМЕННИК ВАЛЮТ</b>\n"
        f"{ex_status}\n\n"
        "📦 <b>СУНДУКИ</b>\n"
        f"{chest_status}\n\n"
        "🌑 <b>ТЁМНАЯ МОРА</b>\n"
        f"{dark_status}\n\n"
        "<i>Совет: подпишитесь на анонсы — бот пишет в чат при старте ивента.</i>"
    )

    await message.answer(text, parse_mode="HTML")


# ── Developer force-commands ──────────────────────────────────────────────────

class _ChestCB(CallbackData, prefix="chest"):
    chest_id: int


@router.message(TextCmd(["форс сундук", "форс_сундук", "force chest"]))
async def cmd_force_chest(message: types.Message, db, bot: Bot, developer_id: int = 0):
    """Dev-only: force-spawn a chest in the current chat."""
    if not developer_id or message.from_user.id != developer_id:
        return
    if message.chat.type == "private":
        return await message.answer("❌ Только в группах.")

    expires = datetime.now(timezone.utc) + timedelta(seconds=CHEST_DURATION_SECONDS)
    expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")
    chest_id = await create_chest(db, message.chat.id, expires_str)
    await db.commit()

    b = InlineKeyboardBuilder()
    b.button(
        text=f"👋 Забрать! (0/{CHEST_MAX_CLAIMANTS})",
        callback_data=_ChestCB(chest_id=chest_id),
    )

    r = CHEST_REWARDS_BY_POSITION
    await bot.send_message(
        message.chat.id,
        f"💰 <b>НАЙДЕН СУНДУК ПРЕДВЕСТНИКА!</b>\n\n"
        f"🥇 1 место: <b>{int(r.get(1, 300))} 🪙</b> + 🎟 Жетон\n"
        f"🥈 2 место: <b>{int(r.get(2, 260))} 🪙</b> + 🎟 Жетон\n"
        f"🥉 3 место: <b>{int(r.get(3, 220))} 🪙</b> + 🎟 Жетон\n"
        f"4–15 место: <b>{int(r.get(15, 30))}–{int(r.get(4, 190))} 🪙</b>\n\n"
        "Нажми быстрее — чем раньше, тем больше! ⏳ 90 сек.",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )
    await message.delete()


@router.message(TextCmd(["форс обмен", "форс_обмен", "force exchange"]))
async def cmd_force_exchange(message: types.Message, db, developer_id: int = 0):
    """Dev-only: force-create an exchange event starting now."""
    if not developer_id or message.from_user.id != developer_id:
        return

    active = await _get_active_exchange(db)
    if active:
        return await message.answer("⚠️ Ивент обмена уже активен.")

    now = datetime.now(timezone.utc)
    starts = now.strftime("%Y-%m-%d %H:%M:%S")
    ends = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    eid = await _create_exchange_event(db, starts, ends)
    await _activate_exchange_event(db, eid)
    await db.commit()
    await message.answer(
        f"✅ <b>Ивент обмена запущен!</b>\n"
        f"Конец: <code>{ends} UTC</code>",
        parse_mode="HTML",
    )
