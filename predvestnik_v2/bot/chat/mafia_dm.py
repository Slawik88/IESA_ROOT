"""Private (DM) side of chat Mafia: role cards, night buttons, mafia board, stale-button cleanup."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,
                                TelegramNetworkError, TelegramRetryAfter, TelegramServerError)
from loguru import logger

from bot.chat import mafia_flood as flood
from bot.chat.mafia_card_views import night_keyboard, vote_dm_keyboard
from core import mafia_copy as copy
from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from infrastructure.repositories import mafia_v1_ops as ops
from services import mafia_private as private


class RetryLater(Exception):
    """A transient Telegram failure: keep the stored event and try again next tick."""


_ART_DIR = Path(__file__).resolve().parents[2] / "FastAPI" / "static" / "mafia-art"
_PHOTO_IDS: dict[tuple[int, str], str] = {}


async def send_dm(bot: Bot, user_id: int, text: str, markup=None, *, art_role: str | None = None):
    """Message or None when the user cannot be reached; transient errors raise RetryLater."""
    try:
        # Only the initial PRIVATE role card gets an illustration. Normal night
        # prompts and public phase edits stay compact text with existing buttons.
        if art_role in rules.ALL_ROLES and len(text.encode('utf-16-le'))//2 <= 900 and hasattr(bot, "send_photo"):
            image = _ART_DIR / f"{art_role}.jpg"
            if image.is_file():
                key = (int(getattr(bot, "id", 0)), art_role)
                photo = _PHOTO_IDS.get(key) or FSInputFile(image)
                try:
                    sent = await bot.send_photo(int(user_id), photo=photo, caption=text, reply_markup=markup, parse_mode="HTML")
                    if key[0] and getattr(sent, "photo", None):
                        _PHOTO_IDS[key] = sent.photo[-1].file_id
                    return sent
                except TelegramBadRequest:
                    # Old cached file IDs or a rejected photo must not prevent
                    # the role and action buttons from reaching the player.
                    _PHOTO_IDS.pop(key, None)
        return await bot.send_message(int(user_id), text, reply_markup=markup, parse_mode="HTML")
    except TelegramForbiddenError:
        return None
    except (TelegramRetryAfter, TelegramNetworkError, TelegramServerError) as exc:
        flood.note(exc)
        raise RetryLater(str(exc)) from exc
    except TelegramBadRequest as exc:
        logger.warning(f"Mafia DM to {user_id} rejected: {exc}")
        return None


# Private messages go out side by side (Telegram allows ~30 per second across chats); the database
# work stays sequential in the caller, because one connection cannot run two queries at once.
FAN_OUT = 6


async def _fan_out(items: list, send: Callable[[Any], Awaitable[Any]]) -> list:
    """Results in input order; a transient failure comes back as a RetryLater instance."""
    gate = asyncio.Semaphore(FAN_OUT)

    async def one(item):
        async with gate:
            try:
                return await send(item)
            except RetryLater as exc:
                return exc
    return list(await asyncio.gather(*(one(item) for item in items)))


async def _remember(db, view: dict, user_id: int, kind: str, message) -> None:
    if message is not None:
        await ops.save_prompt(db, match_id=view["match_id"], phase_number=view["phase_number"],
                              user_id=user_id, kind=kind, message_id=int(message.message_id))


async def _send_board(bot: Bot, db, view: dict, user_id: int) -> None:
    """The coordination board only makes sense with at least two living mafia-side players."""
    rows, lead = await private.team_board(db, match_id=view["match_id"], phase_number=view["phase_number"])
    if len(rows) >= 2:
        await _remember(db, view, user_id, "team", await send_dm(bot, user_id, copy.team_board(rows, lead)))


async def send_role_cards(bot: Bot, db, view: dict, *, chat_title: str | None) -> list[int]:
    """First message of a game: role, goal, how to act (+ team for mafia).  Returns unreachable ids."""
    players, failed = await repo.players(db, match_id=view["match_id"]), []
    seconds = rules.phase_seconds(view["tempo"], "night")
    todo = [p for p in players if p.get("role_sent_at") is None]  # a retry never repeats a delivered card

    def card(me: dict):
        role = me["role"]
        mates = [(p["display_name"], p["role"]) for p in players
                 if role in ("mafia", "don") and p["role"] in ("mafia", "don") and p["user_id"] != me["user_id"]]
        text = copy.role_card(role, mates, chat_title=chat_title) + "\n\n" + copy.night_prompt(role, 1, seconds, first=True)
        markup = night_keyboard(match_id=view["match_id"], phase_number=view["phase_number"], role=role,
                                players=players, actor_id=int(me["user_id"]))
        return markup, send_dm(bot, int(me["user_id"]), text, markup, art_role=role)

    cards = {int(me["user_id"]): card(me) for me in todo}
    results = await _fan_out(todo, lambda me: cards[int(me["user_id"])][1])
    retry = None
    for me, sent in zip(todo, results):
        if isinstance(sent, RetryLater):
            retry = retry or sent
            continue
        if sent is None:
            failed.append(int(me["user_id"]))
            continue
        await _remember(db, view, int(me["user_id"]), "action", sent if cards[int(me["user_id"])][0] else None)
        await ops.mark_role_sent(db, match_id=view["match_id"], user_id=int(me["user_id"]))  # before the board: no second card
        if me["role"] in ("mafia", "don"):
            await _send_board(bot, db, view, int(me["user_id"]))
    if retry is not None:
        raise retry
    return failed


async def send_night_prompts(bot: Bot, db, view: dict) -> list[int]:
    """Night buttons for every living role with an action; already-prompted players are skipped."""
    players = await repo.players(db, match_id=view["match_id"])
    prompted = {p["user_id"] for p in await ops.prompts(db, match_id=view["match_id"], phase_number=view["phase_number"], kind="action")}
    seconds, failed = rules.phase_seconds(view["tempo"], "night"), []
    todo = [p for p in players if p["alive"] and rules.night_action_for(p["role"]) and int(p["user_id"]) not in prompted]
    markups = {}
    for me in todo:
        used = me["role"] == "doctor" and await private.self_save_used(
            db, match_id=view["match_id"], user_id=int(me["user_id"]), phase_number=view["phase_number"])
        markups[int(me["user_id"])] = night_keyboard(match_id=view["match_id"], phase_number=view["phase_number"], role=me["role"],
                                                     players=players, actor_id=int(me["user_id"]), self_save_used=used)
    results = await _fan_out(todo, lambda me: send_dm(bot, int(me["user_id"]), copy.night_prompt(me["role"], view["round_number"], seconds),
                                                      markups[int(me["user_id"])]))
    retry = None
    for me, sent in zip(todo, results):
        if isinstance(sent, RetryLater):
            retry = retry or sent
            continue
        if sent is None:
            failed.append(int(me["user_id"]))
            continue
        await _remember(db, view, int(me["user_id"]), "action", sent)
        if me["role"] in ("mafia", "don"):
            await _send_board(bot, db, view, int(me["user_id"]))
    if retry is not None:
        raise retry
    return failed


async def send_vote_prompts(bot: Bot, db, view: dict) -> None:
    """A ballot in every living player's DM.  Best effort: the group card still works if a DM is closed."""
    players = await repo.players(db, match_id=view["match_id"])
    prompted = {p["user_id"] for p in await ops.prompts(db, match_id=view["match_id"], phase_number=view["phase_number"], kind="action")}
    seconds = rules.phase_seconds(view["tempo"], "voting")
    markup = vote_dm_keyboard(match_id=view["match_id"], phase_number=view["phase_number"], players=players)
    todo = [p for p in players if p["alive"] and int(p["user_id"]) not in prompted]
    results = await _fan_out(todo, lambda me: send_dm(bot, int(me["user_id"]), copy.vote_prompt(seconds), markup))
    retry = None
    for me, sent in zip(todo, results):
        if isinstance(sent, RetryLater):
            retry = retry or sent
            continue
        await _remember(db, view, int(me["user_id"]), "action", sent)
    if retry is not None:
        raise retry


async def refresh_team_board(bot: Bot, db, *, match_id: int, phase_number: int) -> None:
    """Edit every living mafioso's board after someone changes a choice (best effort)."""
    rows, lead = await private.team_board(db, match_id=match_id, phase_number=phase_number)
    text = copy.team_board(rows, lead)
    for prompt in await ops.prompts(db, match_id=match_id, phase_number=phase_number, kind="team"):
        try:
            await bot.edit_message_text(text, chat_id=prompt["user_id"], message_id=prompt["message_id"], parse_mode="HTML")
        except TelegramAPIError as exc:
            logger.debug(f"Mafia board refresh skipped for {prompt['user_id']}: {exc}")


async def strip_old_prompts(bot: Bot, db, *, match_id: int, phase_number: int) -> None:
    """Remove buttons of finished phases so nobody taps a dead keyboard."""
    async def strip(prompt: dict) -> None:
        try:
            await bot.edit_message_reply_markup(chat_id=prompt["user_id"], message_id=prompt["message_id"], reply_markup=None)
        except TelegramAPIError as exc:
            logger.debug(f"Mafia stale keyboard cleanup skipped: {exc}")
    stale = [p for p in await ops.prompts_before(db, match_id=match_id, phase_number=phase_number) if p["kind"] == "action"]
    await _fan_out(stale, strip)
    await ops.delete_prompts_before(db, match_id=match_id, phase_number=phase_number)


async def send_checks(bot: Bot, db, view: dict, checks: list[dict]) -> None:
    names = {int(p["user_id"]): private.target_label(p) for p in view["players"]}
    for check in checks:
        label = names.get(int(check["target_user_id"]), "Игрок")
        await send_dm(bot, int(check["user_id"]), copy.check_result(label, bool(check["is_mafia"])))


async def notify_eliminated(bot: Bot, user_id: int | None) -> None:
    if user_id:
        await send_dm(bot, int(user_id), copy.eliminated_dm())
