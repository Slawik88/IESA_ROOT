# services/membership.py — кто сейчас в чате: user_chat_stats.is_left.
#
# Telegram сообщает об уходе тремя путями, и ни один не надёжен в одиночку:
#  - событие chat_member (bot/chat/members.py) приходит, только если бот — администратор чата;
#  - служебное сообщение «X покинул группу» (observe_service) приходит и обычному боту,
#    но его нет, если в чате скрыты сообщения о входе и выходе;
#  - прямой вопрос getChatMember (services/member_tags.py: фоновый обход и проверка перед показом списка).
# Раньше служебное «покинул группу» учитывалось как обычное сообщение ушедшего и снова ставило
# is_left = FALSE, а обход, узнав «в чате нет», пометку не ставил. Так ушедшие оставались в топах и неактивах.
import os

from services import chat_bots

RECHECK_HOURS = 24   # кто молчит дольше суток, того фоновый обход переспрашивает у Telegram раз в сутки

# Строка daily_user_stats d принадлежит человеку, который всё ещё в этом чате (для топов и мест в рейтинге).
PRESENT_DAILY = ("EXISTS (SELECT 1 FROM user_chat_stats p WHERE p.user_tg_id = d.user_id "
                 "AND p.chat_tg_id = d.chat_id AND NOT COALESCE(p.is_left, FALSE))")
# Человек d.user_id ещё состоит хотя бы в одной группе (для общего топа всех игроков).
PRESENT_ANYWHERE_DAILY = ("EXISTS (SELECT 1 FROM user_chat_stats p WHERE p.user_tg_id = d.user_id "
                          "AND p.chat_tg_id < 0 AND NOT COALESCE(p.is_left, FALSE))")


def bot_tg_id() -> int | None:
    """Собственный Telegram ID бота — вычисляется из BOT_TOKEN (формат <id>:<secret>,
    так же его получает aiogram в Bot.id). Бот физически является строкой в
    user_chat_stats/users (Telegram видит его как обычного участника чата), поэтому
    места, что строят списки «кто в чате» (чистка, топы), должны сами исключать
    этот ID — push/middleware-фильтры ловят только НОВЫЕ события, а не старые строки,
    заведённые до них."""
    token = os.getenv("BOT_TOKEN", "")
    if not token or ":" not in token:
        return None
    try:
        return int(token.split(":", 1)[0])
    except ValueError:
        return None


async def mark_present(db, chat_id: int, user_id: int) -> None:
    """Вошёл в чат (или вернулся). Без commit: вызывающий коммитит вместе со своими записями."""
    await db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, is_left) VALUES (?, ?, FALSE) "
        "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET is_left = FALSE, "
        "rejoined_at = CASE WHEN COALESCE(user_chat_stats.is_left, FALSE) THEN NOW() "
        "ELSE user_chat_stats.rejoined_at END",
        (user_id, chat_id))


async def mark_left(db, chat_id: int, user_id: int) -> None:
    """Ушёл из чата. Строка и вся статистика остаются: вернётся — продолжит с того же места. Без commit."""
    await db.execute(
        "UPDATE user_chat_stats SET is_left = TRUE, membership_checked_at = NOW() "
        "WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, user_id))


def is_service(message) -> bool:
    """Служебное «вошёл» / «покинул группу». Это не сообщение игрока: в счётчики и топы оно не идёт."""
    return getattr(message, "left_chat_member", None) is not None or bool(getattr(message, "new_chat_members", None))


async def observe_service(db, message) -> bool:
    """Отметить вход или уход по служебному сообщению. True — это было оно.

    Отправитель служебного сообщения — сам ушедший или администратор, который его удалил. Поэтому участник
    берётся из поля сообщения, а не из from_user."""
    chat = getattr(message, "chat", None)
    if getattr(chat, "type", None) not in ("group", "supergroup") or not is_service(message):
        return False
    gone = getattr(message, "left_chat_member", None)
    joined = getattr(message, "new_chat_members", None) or []
    if gone is not None and not chat_bots.is_bot(gone):
        await mark_left(db, chat.id, gone.id)
    for user in joined:
        if not chat_bots.is_bot(user):
            await mark_present(db, chat.id, user.id)
    await db.commit()
    return True
