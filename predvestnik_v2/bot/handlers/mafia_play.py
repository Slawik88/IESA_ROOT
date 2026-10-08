"""In-game callbacks of chat Mafia: night moves, votes, «Моя роль», stop/skip/resume, rematch."""
from __future__ import annotations

from aiogram import Bot, Router, types
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from loguru import logger

from bot.handlers import mafia_dm as dm
from bot.handlers.mafia_card_views import night_keyboard, stop_confirm_keyboard, vote_dm_keyboard
from bot.handlers.mafia_cards import post_lobby, publish_phase
from bot.handlers.mafia_cb import MafiaActionCB, MafiaControlCB
from bot.handlers.mafia_delivery import deliver_for_match, group_say
from bot.handlers.mafia_filters import answer, bot_can_moderate, is_chat_admin, topic_of
from core import mafia_copy as copy
from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from infrastructure.repositories import system_flags
from services import mafia_private as private
from services import mafia_v1 as mafia
from services.mafia_common import enabled_roles

router = Router(name="mafia_play_router")
_OFF = "Мафия пока выключена разработчиком."
CHOSEN_MARK = "\n\n✅ Выбрано"


async def resume_flow(bot: Bot, db, view: dict) -> bool:
    """After a pause: re-send night buttons nobody received, then refresh the card."""
    try:
        if view["phase"] == "night":
            failed = await dm.send_night_prompts(bot, db, view)
            if failed:
                names = ", ".join(p["display_name"] for p in view["players"] if int(p["user_id"]) in failed)
                await mafia.pause_match(db, match_id=view["match_id"], reason="private_action_delivery_failed", detail=names[:300])
                await publish_phase(bot, db, await mafia.current_view(db, match_id=view["match_id"]) or view, gap=0)
                return False
    except dm.RetryLater as exc:
        logger.warning(f"Mafia resume postponed: {exc}")
        return False
    await publish_phase(bot, db, view, gap=0)
    return True


async def stop_flow(bot: Bot, db, *, chat_id: int, topic_id: int | None, actor_id: int, text: str,
                    force_admin: bool = False) -> str:
    """Cancel via the service, announce it and deliver the stored cleanup.  Returns an error text or ''."""
    try:
        view = await mafia.cancel_match(db, chat_id=chat_id, topic_id=topic_id, actor_id=actor_id,
                                        is_admin=force_admin or await is_chat_admin(bot, chat_id, actor_id))
    except mafia.MafiaError as exc:
        return str(exc)
    await group_say(bot, view, text)
    await deliver_for_match(bot, db, view["match_id"])
    return ""


async def _edit_chosen(query: types.CallbackQuery, db, data: MafiaActionCB, target: int) -> None:
    """Show the player what they picked and keep the buttons for changing their mind (DM only)."""
    me = await private.private_view(db, match_id=data.match_id, user_id=int(query.from_user.id))
    if not me or not isinstance(query.message, types.Message):
        return
    if data.action == "vote":
        label = "никого не выгонять" if target == 0 else next(
            (private.target_label(p) for p in me["players"] if int(p["user_id"]) == target), "")
        markup = vote_dm_keyboard(match_id=data.match_id, phase_number=data.phase_number, players=me["players"], chosen=target)
    else:
        label = next((private.target_label(p) for p in me["players"] if int(p["user_id"]) == target), "")
        markup = night_keyboard(match_id=data.match_id, phase_number=data.phase_number, role=me["role"],
                                players=me["players"], actor_id=int(query.from_user.id), chosen=target)
    if not label:
        return
    base = (query.message.html_text or "").split(CHOSEN_MARK)[0]
    try:
        await query.message.edit_text(f"{base}\n\n{copy.night_chosen(label)}", reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        logger.debug(f"Mafia DM confirmation not shown: {exc}")


def _toast(data: MafiaActionCB, result: dict, target: int | None) -> str:
    if data.action == "vote":
        text = "Принято: никого не выгонять." if target is None else "Голос принят."
        text += " Можно изменить до конца времени."
    else:
        text = "Выбор принят. Можно изменить до рассвета."
    if result.get("closes_in") is not None:
        text += f" Все готовы — этап закончится через {result['closes_in']} с."
    return text


@router.callback_query(MafiaActionCB.filter())
async def cb_mafia_action(query: types.CallbackQuery, callback_data: MafiaActionCB, db, bot: Bot):
    message = query.message
    if not message:
        return await answer(query, "Сообщение с ходом недоступно.", alert=True)
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await answer(query, _OFF, alert=True)
    match = await repo.get_match(db, match_id=callback_data.match_id)
    if not match:
        return await answer(query, "Эта партия уже закончилась.", alert=True)
    is_vote, in_dm = callback_data.action == "vote", message.chat.type == "private"
    if not is_vote and not in_dm:
        return await answer(query, "Ночной ход делается в личке с ботом, а не в группе.", alert=True)
    if is_vote and not in_dm and int(message.chat.id) != int(match["chat_id"]):
        return await answer(query, "Голосовать можно только в игровой группе или в личке с ботом.", alert=True)
    target = callback_data.target_user_id or None
    try:
        result = await mafia.submit_action(
            db, match_id=callback_data.match_id, chat_id=int(match["chat_id"]), user_id=int(query.from_user.id),
            phase_number=callback_data.phase_number, action_type=callback_data.action, target_user_id=target,
            source_message_id=int(message.message_id) if is_vote and not in_dm else None)
    except mafia.MafiaError as exc:
        return await answer(query, str(exc), alert=True)
    if is_vote:
        view = await mafia.current_view(db, match_id=callback_data.match_id)
        if view:
            await publish_phase(bot, db, view, gap=rules.CARD_EVENT_GAP_SECONDS)
    if in_dm:
        await _edit_chosen(query, db, callback_data, int(target or 0))
    if not is_vote:
        if callback_data.action == "mafia_target":
            await dm.refresh_team_board(bot, db, match_id=callback_data.match_id, phase_number=callback_data.phase_number)
    await answer(query, _toast(callback_data, result, target))


async def _role_popup(query, db, data: MafiaControlCB) -> None:
    me = await private.private_view(db, match_id=data.match_id, user_id=int(query.from_user.id))
    if not me:
        return await answer(query, "Ты не участвуешь в этой партии. Подожди следующую или войди в новое лобби.", alert=True)
    text = copy.role_alert(me["role"], [name for name, _ in me["teammates"]])
    await answer(query, text + ("" if me["alive"] else " (Ты выбыл.)"), alert=True)


async def _control_context(query, bot: Bot) -> tuple[int, int | None, int, bool]:
    chat_id, user_id = int(query.message.chat.id), int(query.from_user.id)
    return chat_id, topic_of(query.message), user_id, await is_chat_admin(bot, chat_id, user_id)


async def _skip(query, db, bot: Bot) -> None:
    chat_id, topic, user_id, is_admin = await _control_context(query, bot)
    try:
        view = await mafia.skip_discussion(db, chat_id=chat_id, topic_id=topic, actor_id=user_id, is_admin=is_admin)
        await mafia.advance_due_match(db, match_id=view["match_id"])
    except mafia.MafiaError as exc:
        return await answer(query, str(exc), alert=True)
    await deliver_for_match(bot, db, view["match_id"])
    await answer(query, "Переходим к голосованию.")


async def _stop_ask(query, db, bot: Bot, data: MafiaControlCB) -> None:
    chat_id, topic, user_id, is_admin = await _control_context(query, bot)
    row = await repo.active_match(db, chat_id=chat_id, topic_id=topic)
    if not row or not mafia.may_control(row, user_id, is_admin):
        return await answer(query, "Остановить игру может хозяин или админ чата.", alert=True)
    await bot.send_message(chat_id, "⏹ <b>Остановить игру?</b>\nПартия закончится без победителя, начать заново можно командой «бот мафия».",
                           reply_markup=stop_confirm_keyboard(data.match_id), parse_mode="HTML", message_thread_id=topic)
    await answer(query, "Подтверди кнопкой ниже.")


async def _stop_confirm(query, db, bot: Bot, yes: bool) -> None:
    chat_id, topic, user_id, _ = await _control_context(query, bot)
    error = ""
    if yes:
        error = await stop_flow(bot, db, chat_id=chat_id, topic_id=topic, actor_id=user_id,
                                text="🛑 <b>Игра остановлена.</b> Чтобы сыграть снова, напишите «бот мафия».")
    if error:
        return await answer(query, error, alert=True)
    try:
        await query.message.delete()
    except TelegramAPIError:
        pass
    await answer(query, "Игра остановлена." if yes else "Играем дальше.")


async def _resume(query, db, bot: Bot) -> None:
    chat_id, topic, user_id, is_admin = await _control_context(query, bot)
    try:
        if not await bot_can_moderate(bot, chat_id):
            raise mafia.MafiaConflict("Боту снова нужны права на удаление сообщений, прежде чем продолжать игру.")
        view = await mafia.resume_match(db, chat_id=chat_id, topic_id=topic, actor_id=user_id, is_admin=is_admin)
    except mafia.MafiaError as exc:
        return await answer(query, str(exc), alert=True)
    ok = await resume_flow(bot, db, view)
    await answer(query, "Партия продолжена." if ok else "Не все получили кнопки в личке — смотри карточку.", alert=not ok)


async def _again(query, db, bot: Bot, data: MafiaControlCB) -> None:
    old = await repo.get_match(db, match_id=data.match_id)
    if not old or old["phase"] not in ("finished", "cancelled"):
        return await answer(query, "Эта партия ещё идёт.", alert=True)
    chat_id, user = int(query.message.chat.id), query.from_user
    try:
        view = await mafia.create_lobby(
            db, chat_id=chat_id, topic_id=topic_of(query.message), initiator_id=int(user.id), username=user.username,
            display_name=user.full_name, max_players=int(old["max_players"]), enabled_roles=enabled_roles(old),
            vote_mode=old["vote_mode"], tempo=old.get("tempo") or rules.DEFAULT_TEMPO)
    except mafia.MafiaError as exc:
        return await answer(query, str(exc), alert=True)
    await post_lobby(bot, db, view, topic_of(query.message))
    await answer(query, "Новое лобби собрано — жми «Войти».")


@router.callback_query(MafiaControlCB.filter())
async def cb_mafia_control(query: types.CallbackQuery, callback_data: MafiaControlCB, db, bot: Bot):
    message = query.message
    if not isinstance(message, types.Message):
        return await answer(query, "Эта карточка слишком старая. Напиши «бот мафия статус», чтобы открыть актуальную.", alert=True)
    if message.chat.type == "private":
        return await answer(query, "Эта кнопка работает только в игровой группе.", alert=True)
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await answer(query, _OFF, alert=True)
    action = callback_data.action
    if action == "role":
        return await _role_popup(query, db, callback_data)
    if action == "skip":
        return await _skip(query, db, bot)
    if action == "stop_ask":
        return await _stop_ask(query, db, bot, callback_data)
    if action in ("stop_yes", "stop_no"):
        return await _stop_confirm(query, db, bot, action == "stop_yes")
    if action == "resume":
        return await _resume(query, db, bot)
    if action == "cancel":
        chat_id, topic, user_id, _ = await _control_context(query, bot)
        error = await stop_flow(bot, db, chat_id=chat_id, topic_id=topic, actor_id=user_id, text="🛑 <b>Партия завершена.</b>")
        return await answer(query, error or "Партия завершена.", alert=bool(error))
    if action == "again":
        return await _again(query, db, bot, callback_data)
    await answer(query, "Неизвестное действие.", alert=True)
