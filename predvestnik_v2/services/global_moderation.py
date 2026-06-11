# services/global_moderation.py
# Глобальная модерация экосистемы бота (Implementation Block 6.3).
# Без bot.* / FastAPI.* импортов — bot передаётся параметром (aiogram.Bot) для отправки уведомлений.

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from infrastructure.repositories import global_moderation as repo
from infrastructure.repositories import users as users_repo
from services.roles import can_issue_global_sanction

SANCTION_LABELS: dict[str, str] = {
    "warn": "предупреждение",
    "restrict": "ограничение",
    "ban": "бан",
}


async def is_user_banned(db, user_id: int) -> bool:
    restriction = await repo.get_active_restriction(db, "user", user_id)
    return bool(restriction and restriction["sanction_type"] == "ban")


async def is_chat_banned(db, chat_id: int) -> bool:
    restriction = await repo.get_active_restriction(db, "chat", chat_id)
    return bool(restriction and restriction["sanction_type"] == "ban")


async def get_user_restriction(db, user_id: int) -> dict | None:
    """Активная restrict для юзера (не ban — ban проверяется отдельно/раньше)."""
    restriction = await repo.get_active_restriction(db, "user", user_id)
    if restriction and restriction["sanction_type"] == "restrict":
        return restriction
    return None


async def get_chat_restriction(db, chat_id: int) -> dict | None:
    """Активная restrict для чата (не ban — ban проверяется отдельно/раньше)."""
    restriction = await repo.get_active_restriction(db, "chat", chat_id)
    if restriction and restriction["sanction_type"] == "restrict":
        return restriction
    return None


def restriction_message(restriction: dict) -> str:
    expires_at = restriction.get("expires_at")
    until = "навсегда" if not expires_at else f"до {expires_at:%d.%m.%Y}"
    reason = restriction.get("reason") or "без указания причины"
    return (
        f"🚫 Экономические команды недоступны ({reason}) — {until}.\n"
        f"Оспорить: «бот апелляция <текст>»"
    )


async def notify_sanction(db, bot, target_type: str, target_id: int, sanction_type: str,
                           reason: str | None, action: str) -> None:
    """action: 'issued' | 'revoked'."""
    label = SANCTION_LABELS.get(sanction_type, sanction_type)
    if action == "issued":
        reason_part = f"\nПричина: {reason}" if reason else ""
        if target_type == "user":
            text = f"⚠️ Глобальная модерация: вам выдана санкция «{label}».{reason_part}"
        else:
            text = f"⚠️ Глобальная модерация: этому чату выдана санкция «{label}».{reason_part}"
    else:
        if target_type == "user":
            text = f"✅ Глобальная модерация: с вас снята санкция «{label}»."
        else:
            text = f"✅ Глобальная модерация: с этого чата снята санкция «{label}»."

    if target_type == "user":
        for chat_id in await repo.get_user_chat_ids(db, target_id):
            try:
                await bot.send_message(chat_id, text)
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
    else:
        try:
            await bot.send_message(target_id, text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


async def issue_global_sanction(db, bot, actor_id: int, actor_rank: int, target_type: str, target_id: int,
                                 sanction_type: str, reason: str | None, expires_at=None,
                                 target_global_rank: int = 0) -> tuple[bool, str]:
    """can_issue_global_sanction → repo.issue_sanction → notify_sanction(action='issued')."""
    if not can_issue_global_sanction(actor_rank, target_type, sanction_type, target_global_rank):
        return False, "❌ Недостаточно прав для этой санкции."

    sanction_id = await repo.issue_sanction(db, target_type, target_id, sanction_type, reason, actor_id, expires_at)
    await notify_sanction(db, bot, target_type, target_id, sanction_type, reason, "issued")

    label = SANCTION_LABELS.get(sanction_type, sanction_type)
    return True, f"✅ Глобальная санкция «{label}» выдана (#{sanction_id})."


async def revoke_global_sanction(db, bot, actor_id: int, actor_rank: int, sanction_id: int) -> tuple[bool, str]:
    """проверка прав по sanction.sanction_type/target → repo.revoke_sanction → notify(action='revoked')."""
    sanction = await repo.get_sanction_by_id(db, sanction_id)
    if not sanction:
        return False, "❌ Санкция с таким ID не найдена."
    if sanction["revoked_at"] is not None:
        return False, "⚠️ Санкция уже снята."

    target_global_rank = 0
    if sanction["target_type"] == "user":
        target_global_rank = await users_repo.get_global_rank(db, sanction["target_id"])

    if not can_issue_global_sanction(actor_rank, sanction["target_type"], sanction["sanction_type"], target_global_rank):
        return False, "❌ Недостаточно прав для снятия этой санкции."

    if not await repo.revoke_sanction(db, sanction_id, actor_id):
        return False, "⚠️ Санкция уже снята."

    await notify_sanction(db, bot, sanction["target_type"], sanction["target_id"],
                           sanction["sanction_type"], sanction["reason"], "revoked")

    label = SANCTION_LABELS.get(sanction["sanction_type"], sanction["sanction_type"])
    return True, f"✅ Глобальная санкция «{label}» (#{sanction_id}) снята."
