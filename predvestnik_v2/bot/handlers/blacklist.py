"""
bot/handlers/blacklist.py
C1-A: Per-chat blacklist commands.
  бот чс                          → список ЧС
  бот чс добавить, @юзер [причина] → добавить
  бот чс убрать, @юзер             → убрать
"""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories.blacklist import get_chat_blacklist
from services import moderation as mod_service
from services.utils import safe_html, resolve_target
from bot.keyboards.cta import answer_group_only

router = Router(name="blacklist_router")


class BlacklistCB(CallbackData, prefix="bl"):
    action: str   # "add_confirm" | "remove_confirm"
    user_id: int
    reason: str = ""


async def _check_rank(db, chat_id: int, user_id: int, developer_id: int) -> bool:
    if developer_id and user_id == developer_id:
        return True
    settings = await mod_db.get_chat_settings(db, chat_id)
    required = settings.get("rank_ban", 5)
    stats = await mod_db.get_user_stats(db, chat_id, user_id)
    rank = stats.get("local_rank", 0) if stats else 0
    return rank >= required


# ── бот чс — показать список ──────────────────────────────────────────────────

@router.message(TextCmd(["чс", "blacklist", "чёрный список", "черный список"]))
async def cmd_blacklist_list(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return await answer_group_only(message)

    chat_id = message.chat.id
    entries = await get_chat_blacklist(db, chat_id)

    if not entries:
        return await message.answer(
            "🚫 <b>ЧЁРНЫЙ СПИСОК</b>\n\n<i>Список пуст.</i>",
            parse_mode="HTML",
        )

    lines = [f"🚫 <b>ЧЁРНЫЙ СПИСОК</b> ({len(entries)} чел.)\n"]
    for i, e in enumerate(entries[:20]):
        prefix = "└" if i == len(entries[:20]) - 1 else "├"
        reason = f" — {safe_html(e['reason'])}" if e.get("reason") else ""
        lines.append(f"{prefix} <code>{e['user_id']}</code>{reason}")

    if len(entries) > 20:
        lines.append(f"\n<i>...и ещё {len(entries) - 20} записей</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── бот чс добавить, @юзер [причина] ─────────────────────────────────────────

@router.message(TextCmd(["чс добавить", "чс add", "добавить в чс"]))
async def cmd_blacklist_add(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return await answer_group_only(message)

    if not await _check_rank(db, message.chat.id, message.from_user.id, developer_id):
        return await message.answer("❌ <b>Отказ:</b> Недостаточно прав.", parse_mode="HTML")

    if not text_args:
        return await message.answer(
            "ℹ️ <code>бот чс добавить, @юзер [причина]</code>", parse_mode="HTML"
        )

    target_id, target_name, extra = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer("❌ Пользователь не найден.", parse_mode="HTML")

    reason = extra.strip() if extra else None
    await mod_service.blacklist_user(
        db, message.chat.id, target_id, message.from_user.id, reason)

    reason_str = f"\n└ Причина: {safe_html(reason)}" if reason else ""
    await message.answer(
        f"✅ <b>{safe_html(target_name)}</b> добавлен(а) в ЧС чата.{reason_str}\n"
        f"<i>При следующем входе будет автоматически исключён(а).</i>",
        parse_mode="HTML",
    )


# ── бот чс убрать, @юзер ─────────────────────────────────────────────────────

@router.message(TextCmd(["чс убрать", "чс remove", "убрать из чс"]))
async def cmd_blacklist_remove(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return await answer_group_only(message)

    if not await _check_rank(db, message.chat.id, message.from_user.id, developer_id):
        return await message.answer("❌ <b>Отказ:</b> Недостаточно прав.", parse_mode="HTML")

    if not text_args:
        return await message.answer(
            "ℹ️ <code>бот чс убрать, @юзер</code>", parse_mode="HTML"
        )

    target_id, target_name, _ = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer("❌ Пользователь не найден.", parse_mode="HTML")

    removed = await mod_service.unblacklist_user(
        db, message.chat.id, target_id, message.from_user.id)

    if removed:
        await message.answer(
            f"✅ <b>{safe_html(target_name)}</b> удалён(а) из ЧС чата.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"ℹ️ <b>{safe_html(target_name)}</b> не был(а) в ЧС этого чата.",
            parse_mode="HTML",
        )


# ── Callback: добавить в ЧС при уходе (C1-B кнопка) ─────────────────────────

@router.callback_query(BlacklistCB.filter())
async def cb_blacklist_action(
    query: types.CallbackQuery,
    callback_data: BlacklistCB,
    db,
    developer_id: int = 0,
):
    chat_id = query.message.chat.id
    actor_id = query.from_user.id

    if callback_data.action == "close":
        await query.message.delete()
        return await query.answer()

    if callback_data.action == "add_confirm":
        # Check rank
        if not await _check_rank(db, chat_id, actor_id, developer_id):
            return await query.answer("❌ Недостаточно прав.", show_alert=True)

        user_id = callback_data.user_id
        reason = callback_data.reason or None
        await mod_service.blacklist_user(db, chat_id, user_id, actor_id, reason)

        admin_name = safe_html(query.from_user.first_name)
        await query.message.edit_text(
            query.message.text + f"\n\n🚫 <b>Добавлен(а) в ЧС</b> администратором {admin_name}.",
            parse_mode="HTML",
            reply_markup=None,
        )
        await query.answer("✅ Добавлен(а) в ЧС!")
