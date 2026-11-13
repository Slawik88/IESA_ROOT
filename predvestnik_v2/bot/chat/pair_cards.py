"""Карточка игры вдвоём в личной переписке (S29a): отрисовка, кнопки ходов, итог.

Карточку отправляет бот от имени игрока; нажимать её кнопки могут оба участника переписки. Кто может нажать что и деньги —
services/pair_games.py; здесь только вид и разбор нажатий. Нажатия приходят по номеру партии в кнопке (p2:<id>:<действие>),
карточка правится по сохранённым id связи, переписки и сообщения.
"""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton
from loguru import logger

from bot.chat import business as chat
from core import pair_games as rules
from services import business as service
from services import pair_games

router = Router(name="chat_pair_cards")

DICE_FACES = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _stake_line(game: dict) -> str:
    if not game["stake"]:
        return "Просто так, без ставки."
    return f"Ставка: {game['stake']} {rules.FUND_TITLES[game['funds']]} с каждого — победитель забирает обе."


def _move_text(kind: str, value) -> str:
    return rules.RPS.get(value, "?") if kind == "rps" else f"{DICE_FACES.get(int(value), value)} {value}"


def render(game: dict) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """Текст и кнопки карточки (без нижних «Не предлагать мне» и «Предвестник» — их добавляет chat.footer)."""
    kind, gid, state = game["kind"], game["id"], game["state"]
    names = {side: html.escape(game["names"].get(side) or ("Игрок" if side == "owner" else "Собеседник")) for side in rules.SIDES}
    title = f"<b>{rules.KINDS[kind]}</b>"
    status = game["status"]
    if status == "invited":
        return (f"{title}\n{names['owner']} зовёт {names['partner']} сыграть.\n{_stake_line(game)}",
                [[_btn("✅ Принять", f"p2:{gid}:acc"), _btn("✖️ Не сейчас", f"p2:{gid}:dec")]])
    if status == "declined":
        return f"{title}\n{names['partner']} пока не хочет играть.", []
    if status in ("cancelled", "expired"):
        back = " Жетоны вернулись." if game["held"] else ""
        why = "сутки не было ходов." if status == "expired" else "игру отменили."
        return f"{title}\n⌛ Игра закрыта: {why}{back}", []
    lines = [title]
    if kind in ("rps", "dice"):
        last = state.get("last")
        if status == "playing":
            if last:
                lines.append(f"Ничья: {_move_text(kind, last['owner'])} и {_move_text(kind, last['partner'])} — ещё раз!")
            lines.append("Выбирайте втайне — я покажу оба хода сразу." if kind == "rps" else "Каждый бросает один раз — у кого больше, тот победил.")
            for side in rules.SIDES:
                lines.append(f"{names[side]}: {'✅ готов' if side in state.get('moves', {}) else '⏳ думает'}")
            buttons = ([[_btn(label, f"p2:{gid}:m:{key}") for key, label in rules.RPS.items()]] if kind == "rps"
                       else [[_btn("🎲 Бросить", f"p2:{gid}:m:roll")]])
            lines.append(_stake_line(game))
            return "\n".join(lines), buttons
        lines += [f"{names[side]}: {_move_text(kind, last[side])}" for side in rules.SIDES]
    else:   # крестики-нолики
        lines.append(f"{rules.MARKS['owner']} {names['owner']} · {rules.MARKS['partner']} {names['partner']}")
        board = state["board"]
        if status == "playing":
            lines.append(f"Ходит: {rules.MARKS[state['turn']]} {names[state['turn']]}")
            lines.append(_stake_line(game))
        grid = [[_btn(rules.MARKS[board[i]] if board[i] else "·", f"p2:{gid}:m:{i}") for i in range(r, r + 3)] for r in (0, 3, 6)]
        if status == "playing":
            return "\n".join(lines), grid
        lines.append("\n".join("".join(rules.MARKS[c] if c else "▫️" for c in board[r:r + 3]) for r in (0, 3, 6)))
    winner = game["winner"]
    if game["state"].get("forfeit"):
        lines.append(f"⌛ {names[rules.other(winner)]} сутки не ходил — партия засчитана сопернику.")
    if winner == "draw":
        lines.append("🤝 Ничья." + (" Ставки вернулись." if game["stake"] else ""))
    else:
        prize = f" +{2 * game['stake']} {rules.FUND_TITLES[game['funds']]}" if game["stake"] else ""
        lines.append(f"🏆 Победил {names[winner]}!{prize}")
    return "\n".join(lines), []


async def post(bot, db, connection: dict, game: dict) -> bool:
    """Отправить карточку приглашения в переписку. False — Telegram не принял (игроку уже объяснено в личке)."""
    text, rows = render(game)
    markup = await chat.footer(db, connection, game["chat_id"], rows, offer_owner=connection["user_id"])
    sent = await chat.in_chat(bot, connection, game["chat_id"],
                              lambda **kw: bot.send_message(text=text, parse_mode="HTML", reply_markup=markup, **kw))
    if sent is None:
        return False
    await pair_games.attach_message(db, game["id"], sent.message_id)
    return True


async def refresh(bot, db, game: dict) -> bool:
    """Перерисовать карточку по итогу нажатия. False — карточку не обновить (связь отключили, право отвечать забрали)."""
    if not game.get("message_id"):
        return False
    connection = await service.owner_of(db, game["connection_id"])
    if connection is None:
        return False
    text, rows = render(game)
    offer = game["owner_id"] if game["status"] in ("invited", "declined", "cancelled") else None   # «Не предлагать мне» остаётся у отказавшегося
    markup = await chat.footer(db, connection, game["chat_id"], rows, offer_owner=offer)
    try:
        await bot.edit_message_text(text=text, chat_id=game["chat_id"], message_id=game["message_id"],
                                    business_connection_id=connection["id"], parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            logger.info(f"pair game {game['id']} card not updated: {exc}")
            return False
    except TelegramAPIError as exc:
        logger.info(f"pair game {game['id']} card not updated: {exc}")
        return False
    return True


@router.callback_query(F.data.startswith("p2:"))
async def on_pair_button(call: CallbackQuery, bot, db) -> None:
    parts = (call.data or "").split(":")
    if len(parts) < 3 or not parts[1].isdigit():
        await call.answer()
        return
    game_id, action = int(parts[1]), parts[2]
    if await service.switched_off(db):
        await call.answer("Игры в переписках сейчас выключены.", show_alert=True)
        return
    try:
        if action == "acc":
            refusal = await _accept_refusal(db, game_id)
            if refusal:
                closed = await pair_games.cancel(db, game_id, "cancelled")
                if closed:
                    await refresh(bot, db, closed)
                await call.answer(refusal, show_alert=True)
                return
            from bot.chat import settings
            game = await pair_games.accept(db, game_id, call.from_user.id, mora_transferable="mora" in await settings.transferable(db))
            if not await refresh(bot, db, game):   # карточку не обновить — ходить будет негде: сразу вернуть ставки
                await pair_games.cancel(db, game_id, "cancelled")
                await call.answer("Карточку не обновить: бота отключили в этой переписке. Ставки вернулись.", show_alert=True)
                return
            await call.answer("Поехали!")
            return
        elif action == "dec":
            game = await pair_games.decline(db, game_id, call.from_user.id)
            note = "Хорошо."
        elif action == "m" and len(parts) == 4:
            game, result = await pair_games.play(db, game_id, call.from_user.id, parts[3])
            note = _move_note(game, call.from_user.id, parts[3], result)
        else:
            await call.answer()
            return
    except pair_games.MoveError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await refresh(bot, db, game)
    await call.answer(note)


async def _accept_refusal(db, game_id: int) -> str | None:
    """Что изменилось с момента приглашения так, что играть больше нельзя: выключили игры или ставки (игрок в настройках
    переписки или администрация), бота отключили, один из игроков заблокирован или удаляет аккаунт."""
    game = await pair_games.get(db, game_id)
    if game is None or game["status"] != "invited":
        return None   # дальше ответит сам сервис («игра уже началась или закрыта»)
    connection = await service.owner_of(db, game["connection_id"])
    if connection is None:
        return "Бота отключили в этой переписке — игра отменена."
    if not await service.feature_on(db, connection, game["chat_id"], "games") or (
            game["stake"] and not await service.feature_on(db, connection, game["chat_id"], "bets")):
        return "Эти игры здесь выключили — игра отменена."
    for uid in (game["owner_id"], game["partner_id"]):
        if not await service.owner_may_act(db, uid):
            return "С этим игроком сейчас играть нельзя — игра отменена."
    return None


def _move_note(game: dict, user_id: int, value: str, result: str | None) -> str:
    side = pair_games.side_of(game, user_id)
    if result is not None:
        return "Ничья!" if result == "draw" else ("Победа! 🏆" if result == side else "В этот раз не повезло.")
    if game["kind"] == "rps":
        return f"Ты выбрал: {rules.RPS[value]}. Ждём соперника."
    if game["kind"] == "dice":
        return "Бросок сделан. Ждём соперника."
    return "Ход сделан."


async def expire(bot, db) -> int:
    """Обслуживание: закрыть партии без ходов дольше суток, вернуть ставки, обновить карточки."""
    closed = await pair_games.expire_due(db)
    await db.release_if_idle()   # дальше только Telegram: слот пула не держим
    for game in closed:
        await refresh(bot, db, game)
    return len(closed)
