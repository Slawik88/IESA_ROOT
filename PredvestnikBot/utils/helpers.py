from aiogram.types import Message
import html
from database.db import get_user, get_user_by_username
from services.recent_users import get_recent_user, get_recent_user_by_username


async def resolve_target(message: Message, cmd_args: str) -> tuple:
    """
    Ищет целевого пользователя:
    1. По ответу (reply)
    2. По @username в аргументах
    3. По числовому ID в аргументах
    Возвращает (user_id, full_name, remaining_args) или (None, None, error_text)
    """
    if message.reply_to_message and message.reply_to_message.from_user:
        t = message.reply_to_message.from_user
        return t.id, t.full_name, cmd_args

    parts = cmd_args.split(maxsplit=1) if cmd_args else []
    if parts:
        arg = parts[0]
        remaining = parts[1] if len(parts) > 1 else ""
        if arg.startswith("@"):
            recent_user = get_recent_user_by_username(arg)
            if recent_user:
                return recent_user["user_id"], recent_user["full_name"], remaining
            user = await get_user_by_username(arg)
            if user:
                return user["user_id"], user["full_name"], remaining
        elif arg.isdigit():
            recent_user = get_recent_user(int(arg))
            if recent_user:
                return recent_user["user_id"], recent_user["full_name"], remaining
            user = await get_user(int(arg))
            if user:
                return user["user_id"], user["full_name"], remaining

    return None, "❌ Ответь на сообщение или укажи @username / ID пользователя.", ""


def parse_time(time_str: str) -> tuple[int, str]:
    """Парсит '10с', '10м', '2ч', '1д', '1г' (или s/m/h/d/y) → (секунды, описание).
    Примеры: 30с, 10м, 2ч, 7д, 1г. По умолчанию 5 мин."""
    mapping = {
        ("с", "s"):  (1,        "сек."),
        ("м", "m"):  (60,       "мин."),
        ("ч", "h"):  (3600,     "ч."),
        ("д", "d"):  (86400,    "дн."),
        ("г", "y"):  (31536000, "лет"),
    }
    if time_str:
        suffix = time_str[-1].lower()
        num_part = time_str[:-1]
        for keys, (mult, label) in mapping.items():
            if suffix in keys:
                try:
                    n = int(num_part)
                    return n * mult, f"{num_part} {label}"
                except ValueError:
                    pass
    return 300, "5 мин."


def user_mention(user_id: int, full_name: str) -> str:
    """Возвращает кликабельное упоминание пользователя (HTML)."""
    return f'<a href="tg://user?id={user_id}">{html.escape(full_name)}</a>'


def bot_today() -> str:
    """Возвращает 'сегодняшнюю' дату (YYYY-MM-DD) в часовом поясе бота (BOT_TIMEZONE из config)."""
    from datetime import datetime, timezone
    try:
        from zoneinfo import ZoneInfo
        from config import BOT_TIMEZONE
        tz = ZoneInfo(BOT_TIMEZONE)
        return datetime.now(tz).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def format_duration(iso_str: str) -> str:
    """Форматирует ISO-datetime строку как 'X дн. Y ч. Z мин.' относительно текущего UTC времени."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        total_seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
        days    = total_seconds // 86400
        hours   = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        parts = []
        if days:
            parts.append(f"{days} дн.")
        if hours:
            parts.append(f"{hours} ч.")
        if minutes or not parts:
            parts.append(f"{minutes} мин.")
        return " ".join(parts)
    except Exception:
        return "?"


async def notify_admins(bot, text: str, source_chat_id: int | None = None):
    """Send a system notification to all admin groups.
    Falls back to individual staff DMs if no admin groups are configured.
    """
    from database.db import get_admin_group_ids, get_staff_in_chat
    from utils.ranks import rank_level

    admin_groups = get_admin_group_ids()

    if admin_groups:
        for gid in admin_groups:
            try:
                await bot.send_message(gid, text, parse_mode="HTML", disable_web_page_preview=True)
            except Exception:
                pass
    elif source_chat_id:
        # Fallback: DM staff from the source chat
        from config import REPORT_NOTIFY_RANK
        staff = await get_staff_in_chat(source_chat_id)
        for s in staff:
            if rank_level(s["rank"]) >= rank_level(REPORT_NOTIFY_RANK):
                try:
                    await bot.send_message(s["user_id"], text, parse_mode="HTML",
                                           disable_web_page_preview=True)
                except Exception:
                    pass
