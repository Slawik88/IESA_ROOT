# services/moderation.py
# Platform-agnostic moderation permission checks + единые действия модерации.
# developer_id is passed as a parameter so this module has zero config imports.
import logging
from datetime import datetime, timedelta, timezone

import aiosqlite
from aiogram.types import ChatPermissions

from infrastructure.repositories.chat import get_chat_stats
from infrastructure.repositories.moderation import (
    log_moderation_action,
    remove_ban_log,
    set_immunity,
)
from infrastructure.repositories.blacklist import (
    add_to_chat_blacklist,
    remove_from_chat_blacklist,
)

logger = logging.getLogger(__name__)


async def check_mod_rights(
    db: aiosqlite.Connection,
    chat_id: int,
    admin_id: int,
    target_id: int,
    min_rank: int = 1,
    developer_id: int = 0,
    bot_id: int = 0,
) -> tuple[bool, str]:
    """Return (allowed, error_message). Empty string means allowed."""
    if admin_id == target_id:
        return False, "🤡 <b>Ошибка:</b> Нельзя применить это к самому себе."
    if developer_id and target_id == developer_id:
        return False, "🛡 <b>Ошибка:</b> На этого пользователя не действуют законы смертных."
    if bot_id and target_id == bot_id:
        return False, "🤖 <b>Ошибка:</b> Нельзя применять меры воздействия к боту."

    admin_stats = await get_chat_stats(db, admin_id, chat_id)
    target_stats = await get_chat_stats(db, target_id, chat_id)
    admin_rank = admin_stats.get("local_rank", 0)
    target_rank = target_stats.get("local_rank", 0)

    if not (developer_id and admin_id == developer_id):
        if admin_rank < min_rank:
            return False, "❌ <b>Ошибка:</b> Недостаточно прав для этого действия."
        if target_rank >= admin_rank:
            return False, "⚠️ <b>Ошибка:</b> Вы не можете наказать того, чей ранг равен вашему или выше."

    return True, ""


async def check_admin_rights(
    db: aiosqlite.Connection,
    chat_id: int,
    user_id: int,
    min_rank: int = 1,
    developer_id: int = 0,
    bot_id: int = 0,
) -> tuple[bool, str]:
    """Check that user has at least min_rank (no target comparison)."""
    if developer_id and user_id == developer_id:
        return True, ""
    user_stats = await get_chat_stats(db, user_id, chat_id)
    if user_stats.get("local_rank", 0) < min_rank:
        return False, "❌ <b>Ошибка:</b> У вас недостаточно прав для этого действия."
    return True, ""

async def chat_sanctions_map(db, chat_id: int, user_ids: list[int]) -> dict[int, dict]:
    """Статусы модерации участников чата ОДНИМ проходом — для списков участников
    в админке сайта и dev-консоли («Сайт == бот»: бот-команды бан/кик пишут те же
    moderation_logs, глобальный ЧС — global_sanctions).

    banned     — активный бан чата ИЛИ запись в ЧС чата (unban_user снимает оба);
    kicked     — кикали (история: после кика можно вернуться);
    global_ban — активный глобальный бан бота."""
    out: dict[int, dict] = {
        int(u): {"banned": False, "kicked": False, "global_ban": False}
        for u in user_ids
    }
    if not out:
        return out
    ids = list(out)
    ph = ",".join(["?"] * len(ids))
    async with db.execute(
        "SELECT user_id, action FROM moderation_logs "
        f"WHERE chat_id = ? AND action IN ('ban','kick') AND user_id IN ({ph})",
        [chat_id, *ids],
    ) as c:
        for r in await c.fetchall():
            key = "banned" if r["action"] == "ban" else "kicked"
            out[int(r["user_id"])][key] = True
    # ЧС чата = тот же бан с точки зрения админа (автокик при входе)
    async with db.execute(
        f"SELECT user_id FROM chat_blacklist WHERE chat_id = ? AND user_id IN ({ph})",
        [chat_id, *ids],
    ) as c:
        for r in await c.fetchall():
            out[int(r[0])]["banned"] = True
    async with db.execute(
        "SELECT DISTINCT target_id FROM global_sanctions "
        "WHERE target_type = 'user' AND sanction_type = 'ban' AND revoked_at IS NULL "
        f"AND (expires_at IS NULL OR expires_at > NOW()) AND target_id IN ({ph})",
        ids,
    ) as c:
        for r in await c.fetchall():
            out[int(r[0])]["global_ban"] = True
    return out


# ==========================================
# ЕДИНЫЕ ДЕЙСТВИЯ МОДЕРАЦИИ («сайт == бот»)
# ==========================================
# Бан живёт в трёх местах: TG-бан, moderation_logs (action='ban' — значок на
# сайте/списки бота) и chat_blacklist (автокик при входе). Любой вход — бот-команда,
# кнопка, сайт, dev-консоль — обязан идти через эти функции, чтобы все три
# состояния менялись вместе. Проверка прав остаётся на вызывающей стороне.
#
# `bot` — duck-typed объект с интерфейсом aiogram.Bot (ban_chat_member /
# unban_chat_member / restrict_chat_member); FastAPI передаёт HTTP-shim
# (см. _TgBotShim в FastAPI/routers/admin.py) — паттерн как _BotShim
# в global_admin.py. TG-вызов не удался → состояние в БД НЕ меняем.

# Полные наборы прав mute/unmute — раньше бот глушил только can_send_messages,
# а сайт всё; теперь одинаково везде.
MUTE_PERMS = ChatPermissions(
    can_send_messages=False, can_send_audios=False, can_send_documents=False,
    can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
    can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
)
UNMUTE_PERMS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True,
)

# Вечный мут: muted_until должен быть НЕ NULL, чтобы сайт видел статус.
MUTE_FOREVER_STR = "2099-01-01 00:00:00"


async def ban_user(db, bot, chat_id: int, target_id: int, admin_id: int,
                   reason: str | None = None) -> bool:
    try:
        await bot.ban_chat_member(chat_id, target_id)
    except Exception as e:
        logger.warning(f"ban_user: TG-бан {target_id} в {chat_id} не удался: {e}")
        return False
    await log_moderation_action(db, chat_id, target_id, admin_id, "ban", reason)
    return True


async def unban_user(db, bot, chat_id: int, target_id: int, admin_id: int,
                     reason: str | None = None) -> bool:
    """Полная амнистия: TG-разбан + удаление ban-записей журнала + выход из ЧС чата."""
    try:
        await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
    except Exception as e:
        logger.warning(f"unban_user: TG-разбан {target_id} в {chat_id} не удался: {e}")
        return False
    await remove_ban_log(db, chat_id, target_id)
    await remove_from_chat_blacklist(db, chat_id, target_id)
    await log_moderation_action(db, chat_id, target_id, admin_id, "unban", reason)
    return True


async def kick_user(db, bot, chat_id: int, target_id: int, admin_id: int,
                    reason: str | None = None) -> bool:
    try:
        await bot.ban_chat_member(chat_id, target_id)
        await bot.unban_chat_member(chat_id, target_id)
    except Exception as e:
        logger.warning(f"kick_user: TG-кик {target_id} из {chat_id} не удался: {e}")
        return False
    await log_moderation_action(db, chat_id, target_id, admin_id, "kick", reason)
    return True


async def mute_user(db, bot, chat_id: int, target_id: int, admin_id: int,
                    duration_minutes: int | None = None,
                    reason: str | None = None) -> bool:
    """duration_minutes=None — вечный мут (до ручного размута)."""
    if duration_minutes:
        until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        until_date, muted_until_str = int(until.timestamp()), until.strftime("%Y-%m-%d %H:%M:%S")
        action = f"mute_{duration_minutes}m"
    else:
        until_date, muted_until_str = None, MUTE_FOREVER_STR
        action = "mute_perm"
    try:
        await bot.restrict_chat_member(
            chat_id, target_id, permissions=MUTE_PERMS, until_date=until_date)
    except Exception as e:
        logger.warning(f"mute_user: TG-мут {target_id} в {chat_id} не удался: {e}")
        return False
    await db.execute(
        "UPDATE user_chat_stats SET muted_until = ? WHERE user_tg_id = ? AND chat_tg_id = ?",
        (muted_until_str, target_id, chat_id),
    )
    await log_moderation_action(db, chat_id, target_id, admin_id, action, reason)
    return True


async def unmute_user(db, bot, chat_id: int, target_id: int, admin_id: int,
                      reason: str | None = None) -> bool:
    try:
        await bot.restrict_chat_member(chat_id, target_id, permissions=UNMUTE_PERMS)
    except Exception as e:
        logger.warning(f"unmute_user: TG-размут {target_id} в {chat_id} не удался: {e}")
        return False
    await db.execute(
        "UPDATE user_chat_stats SET muted_until = NULL WHERE user_tg_id = ? AND chat_tg_id = ?",
        (target_id, chat_id),
    )
    await log_moderation_action(db, chat_id, target_id, admin_id, "unmute", reason)
    return True


async def blacklist_user(db, chat_id: int, target_id: int, admin_id: int,
                         reason: str | None = None) -> None:
    """ЧС чата (автокик при входе) + журнал. TG-вызова нет: цель обычно уже вне чата."""
    await add_to_chat_blacklist(db, chat_id, target_id, reason, admin_id)
    await log_moderation_action(db, chat_id, target_id, admin_id, "blacklist_add", reason)


async def unblacklist_user(db, chat_id: int, target_id: int, admin_id: int) -> bool:
    removed = await remove_from_chat_blacklist(db, chat_id, target_id)
    if removed:
        await log_moderation_action(db, chat_id, target_id, admin_id, "blacklist_remove")
    else:
        await db.commit()
    return removed


async def shield_user(db, chat_id: int, target_id: int, admin_id: int,
                      duration_minutes: int, reason: str | None = None) -> None:
    """Временный щит от чистки. Постоянный иммунитет (is_immune) сохраняется —
    раньше сайт затирал его нулём, бот сохранял; теперь одинаково везде."""
    stats = await get_chat_stats(db, target_id, chat_id)
    keep_immune = 1 if stats.get("is_immune") else 0
    until = (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
             ).strftime("%Y-%m-%d %H:%M:%S")
    await set_immunity(db, chat_id, target_id, keep_immune, until)
    await log_moderation_action(
        db, chat_id, target_id, admin_id, f"shield_{duration_minutes}m", reason)


async def unshield_user(db, chat_id: int, target_id: int, admin_id: int,
                        reason: str | None = None) -> None:
    """Снять временный щит; постоянный иммунитет не трогаем (у него своя команда)."""
    stats = await get_chat_stats(db, target_id, chat_id)
    keep_immune = 1 if stats.get("is_immune") else 0
    await set_immunity(db, chat_id, target_id, keep_immune, None)
    await log_moderation_action(db, chat_id, target_id, admin_id, "unshield", reason)


async def set_immune_user(db, chat_id: int, target_id: int, admin_id: int,
                          on: bool, reason: str | None = None) -> None:
    """Постоянный иммунитет вкл/выкл. Включение/снятие сбрасывает и временный щит."""
    await set_immunity(db, chat_id, target_id, 1 if on else 0, None)
    await log_moderation_action(
        db, chat_id, target_id, admin_id, "immune_on" if on else "immune_off", reason)


async def start_warn_court(db, chat_id: int, target_id: int, target_name: str,
                           warns_count: int, max_warns: int) -> None:
    """Суд Присяжных при достижении лимита варнов: сообщение с кнопками вердикта
    в привязанный админ-чат (или в сам чат). callback_data — в формате aiogram
    WarnAction (bot/handlers/moderation.py), токен один — вердикты с сайта и из
    чата обрабатывает один и тот же хендлер (как purge-досье)."""
    from infrastructure.repositories.routing import get_admin_chat
    from services.telegram_http import tg_call

    court_text = (
        f"⚖️ <b>СУД ПРИСЯЖНЫХ</b>\n\n"
        f"Пользователь {target_name} достиг лимита варнов (<b>{warns_count}/{max_warns}</b>).\n"
        f"Выберите меру пресечения:"
    )
    keyboard = {"inline_keyboard": [
        [{"text": "🔨 Бан", "callback_data": f"warn_act:ban:{target_id}:{chat_id}"},
         {"text": "👢 Кик", "callback_data": f"warn_act:kick:{target_id}:{chat_id}"}],
        [{"text": "🕊 Простить", "callback_data": f"warn_act:forgive:{target_id}:{chat_id}"}],
    ]}
    admin_chat = await get_admin_chat(db, chat_id)
    dest = admin_chat if admin_chat else chat_id
    r = await tg_call("sendMessage", chat_id=dest, text=court_text,
                      parse_mode="HTML", reply_markup=keyboard)
    if not r.get("ok"):
        logger.warning(f"start_warn_court: отправка в {dest} не удалась: {r}")
        if dest != chat_id:
            await tg_call("sendMessage", chat_id=chat_id, text=court_text,
                          parse_mode="HTML", reply_markup=keyboard)
