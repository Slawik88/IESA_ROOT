"""
bot/handlers/events_info.py
Команда «бот ивент» — показывает статус и расписание ближайших ивентов.
Dev-команды для принудительного запуска.
"""
from datetime import datetime, timedelta, timezone

from aiogram import Router, types

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import answer_group_only

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
        return await answer_group_only(message)
    del db
    await message.answer(
        "🗓 <b>СОБЫТИЯ ПРЕДВЕСТНИКА</b>\n\n"
        "Старые сундуки, валютные окна и события Тёмной Моры закрыты: они не меняют кошелёк.\n\n"
        "Сейчас доступен 🔔 <b>Разлом колокола</b> и походы во вкладке <b>Игра → Спутник</b>. "
        "Новые мировые события появятся только с заранее опубликованными условиями и наградами.",
        parse_mode="HTML",
    )


# ── Developer force-commands ──────────────────────────────────────────────────

@router.message(TextCmd(["форс сундук", "форс_сундук", "force chest",
                        "dev ивент сундук", "dev chest"]))
async def cmd_force_chest(message: types.Message, db, developer_id: int = 0):
    """Dev alias retained as an explicit retirement response."""
    if not developer_id or message.from_user.id != developer_id:
        return
    del db
    return await message.answer("Архивные сундуки отключены и больше не запускаются.")


@router.message(TextCmd(["форс обмен", "форс_обмен", "force exchange"]))
async def cmd_force_exchange(message: types.Message, db, developer_id: int = 0):
    """Dev-only: force-create an exchange event starting now."""
    if not developer_id or message.from_user.id != developer_id:
        return
    del db
    await message.answer("Старый обмен Моры и Алмазов отключён и не запускается.")
