"""Telegram adapter for chat Mafia: the «бот мафия» command, lobby and settings screens."""
from __future__ import annotations

from typing import NamedTuple

from aiogram import Bot, Router, types
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from bot.chat import mafia_dm as dm
from bot.chat.mafia_cards import bump_card, post_lobby, publish_phase
from bot.chat.mafia_cb import MafiaLobbyCB, MafiaReadyCB, MafiaRulesCB, MafiaSettingsCB
from bot.chat.mafia_delivery import deliver_for_match, group_say
from bot.chat.mafia_filters import (absent_players, answer, bot_can_moderate, bot_username, cannot_write, deletion_blocked, dm_reachable,
                                        is_anonymous_admin, is_chat_admin, posts_anonymously, topic_of, unreachable_players)
from bot.chat.mafia_play import resume_flow, router as play_router, stop_flow
from bot.chat.mafia_views import (LOBBY_SIZE_OPTIONS, PRESETS, join_url, lobby_keyboard, lobby_text, rules_keyboard,
                                      rules_url, settings_keyboard, settings_text)
from bot.chat.framework import Ctx, Parsed, parse as parse_chat_command, registry
from bot.chat.modules import feature_enabled, module_disabled_reason
from core import mafia_command, mafia_copy as copy
from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from infrastructure.repositories import mafia_v1_ops as ops
from infrastructure.repositories import system_flags
from services import mafia_v1 as mafia
from services.formatting import safe_html

router = Router(name="mafia_v1_router")
router.include_router(play_router)
_OFF = "Мафия пока выключена разработчиком."
_TOO_OLD = "Эта карточка слишком старая. Напиши «бот мафия», чтобы открыть актуальную."
_NEED_ADMIN = ("❌ <b>Боту нужны права администратора</b>\nЧтобы играть в Мафию, ему нужно право «Удалять сообщения» — "
               "иначе он не сможет убирать сообщения в ночные фазы.\n"
               "<blockquote>1) Откройте настройки группы → Администраторы → Бот.\n2) Включите «Удалять сообщения».\n3) Напишите «бот мафия» ещё раз.</blockquote>")
_WORDS = {"дон": "don", "don": "don", "доктор": "doctor", "doctor": "doctor", "детектив": "detective",
          "комиссар": "detective", "detective": "detective"}
_TEMPO_WORDS = {"быстро": "fast", "быстрый": "fast", "fast": "fast", "неспешно": "slow", "долго": "slow", "slow": "slow",
                "обычно": "normal", "normal": "normal"}


def parse_create_args(raw: str) -> tuple[int, tuple[str, ...], str, str]:
    """«8 доктор детектив открытое быстро» -> (seats, roles, vote mode, tempo)."""
    seats, roles, vote, tempo = rules.DEFAULT_SEATS, set(), "secret", rules.DEFAULT_TEMPO
    for part in raw.split():
        if part.isdecimal():
            seats = int(part)
        elif part in _WORDS:
            roles.add(_WORDS[part])
        elif part in {"открытое", "open"}:
            vote = "open"
        elif part in {"скрытое", "secret"}:
            vote = "secret"
        elif part in _TEMPO_WORDS:
            tempo = _TEMPO_WORDS[part]
        else:
            raise mafia.MafiaConflict(f"Не понял слово «{safe_html(part[:30])}».")
    return seats, tuple(sorted(roles)), vote, tempo


async def _send_lobby(bot: Bot, db, view: dict, topic: int | None) -> None:
    await post_lobby(bot, db, view, topic)


async def _create(message: types.Message, db, bot: Bot, args: str) -> None:
    chat_id, topic = int(message.chat.id), topic_of(message)
    if posts_anonymously(message):
        return await message.answer("Напиши «бот мафия» от своего имени, не анонимным админом: хозяину лобби нужно уметь нажимать кнопки.")
    if await repo.active_match(db, chat_id=chat_id, topic_id=topic):
        return await _status(message, db, bot)  # "бот мафия" while a game exists means "where is it?"
    if not await bot_can_moderate(bot, chat_id):
        return await message.answer(_NEED_ADMIN, parse_mode="HTML")
    reason = await module_disabled_reason(db, chat_id, "module_mafia")
    if reason:
        return await message.answer(f"🔧 {safe_html(reason)}", parse_mode="HTML")
    try:
        seats, roles, vote, tempo = parse_create_args(args)
        view = await mafia.create_lobby(db, chat_id=chat_id, topic_id=topic, initiator_id=int(message.from_user.id),
                                        username=message.from_user.username, display_name=message.from_user.full_name,
                                        max_players=seats, enabled_roles=roles, vote_mode=vote, tempo=tempo)
    except mafia.MafiaError as exc:
        return await message.answer(f"❌ {exc}\n\n{mafia_command.invite_hint()}", parse_mode="HTML")
    await _send_lobby(bot, db, view, topic)


async def _private_entry(message: types.Message, db, kind: str) -> None:
    if kind == "ready":
        await mafia.confirm_dm_ready(db, user_id=int(message.from_user.id))
        return await message.answer("✅ Готово. Теперь можно вступать в лобби Мафии в группе.")
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 Как играть", callback_data=MafiaRulesCB(page="intro"))
    builder.button(text="✅ Я готов получать роль", callback_data=MafiaReadyCB(action="ready"))
    builder.adjust(1)
    await message.answer(
        "🕵️ <b>Мафия играется в групповом чате.</b>\nДобавь меня в группу с друзьями и напиши там <code>бот мафия</code> — "
        "появится лобби. Роли и ночные ходы приходят сюда, в личку.\n<i>Не играл раньше? Нажми «Как играть».</i>",
        reply_markup=builder.as_markup(), parse_mode="HTML")


async def _status(message: types.Message, db, bot: Bot) -> None:
    """Show the chat's current game again (the lobby or the phase card), at most once per 30 s."""
    row = await repo.active_match(db, chat_id=int(message.chat.id), topic_id=topic_of(message))
    if not row:
        return await message.answer("Сейчас в этом чате нет игры в Мафию. Напишите «бот мафия», чтобы собрать лобби.")
    if not await ops.claim_bump(db, match_id=int(row["id"]), gap_seconds=30):
        return await message.answer("Игра уже идёт — её карточка чуть выше. Если не видно, повторите через полминуты.")
    view = await mafia.current_view(db, match_id=int(row["id"]))
    if view["phase"] == "lobby":
        return await post_lobby(bot, db, view, topic_of(message), retire_old=True)
    await publish_phase(bot, db, view, gap=0, repost=True)


async def _rules_in_group(message: types.Message, bot: Bot) -> None:
    builder = InlineKeyboardBuilder()
    url = rules_url(await bot_username(bot))
    if url:
        builder.button(text="📖 Открыть правила", url=url)
    await message.answer("📖 <b>Правила Мафии</b> — короткое объяснение в личке с ботом. Нажми кнопку ниже.",
                         reply_markup=builder.as_markup() if url else None, parse_mode="HTML")


async def _control_command(message: types.Message, db, bot: Bot, kind: str) -> None:
    chat_id, topic, user_id = int(message.chat.id), topic_of(message), int(message.from_user.id)
    if kind == "stop":
        error = await stop_flow(bot, db, chat_id=chat_id, topic_id=topic, actor_id=user_id, force_admin=is_anonymous_admin(message),
                                text="🛑 <b>Игра остановлена.</b> Чтобы сыграть снова, напишите «бот мафия».")
        return await message.answer(f"❌ {error}") if error else None
    if not await bot_can_moderate(bot, chat_id):
        return await message.answer("❌ Для продолжения Мафии боту всё ещё нужны права на удаление сообщений.")
    try:
        view = await mafia.resume_match(db, chat_id=chat_id, topic_id=topic, actor_id=user_id,
                                        is_admin=is_anonymous_admin(message) or await is_chat_admin(bot, chat_id, user_id))
    except mafia.MafiaError as exc:
        return await message.answer(f"❌ {exc}")
    await resume_flow(bot, db, view)
    await message.answer("▶️ Партия продолжена. Таймер восстановлен с оставшимся временем.")


@registry.command("мафия", aliases=("mafia",), usage="бот мафия [8 доктор детектив открытое]  ·  бот мафия стоп  ·  бот мафия правила",
                  section="games", summary="Лобби Мафии в группе: роли приходят в личку.", example="бот мафия")
async def cmd_mafia_chat(ctx: Ctx) -> None:
    command = mafia_command.parse(f"бот мафия {ctx.args or ''}")
    await cmd_mafia(ctx.message, ctx.db, ctx.bot, command)


async def cmd_mafia(message: types.Message, db, bot: Bot, mafia_cmd: mafia_command.MafiaCommand):
    if not await feature_enabled(db, "game_mafia_v1"):
        return await message.answer("🚧 «Мафия» временно отключена разработчиком. Попробуйте позже.")
    if message.chat.type == "private":
        return await _private_entry(message, db, mafia_cmd.kind)
    handlers = {"rules": lambda: _rules_in_group(message, bot), "status": lambda: _status(message, db, bot),
                "stop": lambda: _control_command(message, db, bot, "stop"),
                "resume": lambda: _control_command(message, db, bot, "resume")}
    if mafia_cmd.kind in handlers:
        return await handlers[mafia_cmd.kind]()
    if mafia_cmd.kind == "ready":
        return await message.answer("Эта команда нужна в личке с ботом. В группе просто нажми «➕ Войти» в лобби.")
    await _create(message, db, bot, mafia_cmd.args)


# ── lobby buttons ───────────────────────────────────────────────────────────
async def _join(query, db, bot: Bot, data: MafiaLobbyCB) -> dict | None:
    user = query.from_user
    if not await dm_reachable(bot, int(user.id)):
        await answer(query, "Чтобы получить роль, нужно открыть бота: нажми «Старт» — и я сам запишу тебя в лобби.",
                     url=join_url(await bot_username(bot), data.match_id))
        return None
    await mafia.confirm_dm_ready(db, user_id=int(user.id))
    return await mafia.join_lobby(db, match_id=data.match_id, chat_id=int(query.message.chat.id), topic_id=topic_of(query.message),
                                  user_id=int(user.id), username=user.username, display_name=user.full_name)


async def _preflight(bot: Bot, db, chat_id: int, match_id: int) -> str:
    """Names that would break the start, as a human sentence ('' when everyone is fine)."""
    players = await repo.players(db, match_id=match_id)
    blocked = set(await unreachable_players(bot, [int(p["user_id"]) for p in players]))
    no_dm = [p["display_name"] for p in players if int(p["user_id"]) in blocked]
    no_chat = await cannot_write(bot, chat_id, players)
    parts = []
    if no_dm:
        parts.append(f"не может получить роль в личке: {', '.join(no_dm[:3])} (нужно открыть бота и нажать «Старт»)")
    if no_chat:
        parts.append(f"не может писать в чат: {', '.join(no_chat[:3])}")
    return "Старт невозможен — " + "; ".join(parts) if parts else ""


async def _start(query, db, bot: Bot, data: MafiaLobbyCB) -> None:
    message, user_id = query.message, int(query.from_user.id)
    chat_id = int(message.chat.id)
    lobby = await repo.get_match(db, match_id=data.match_id)
    if lobby and int(lobby["chat_id"]) == chat_id and lobby["phase"] == "lobby" and int(lobby["initiator_id"]) != user_id:
        # Раньше любой участник запускал проверку всех игроков (десятки запросов к Telegram) и только потом слышал отказ
        return await answer(query, "Начать партию может только хозяин лобби.", alert=True)
    reason = await module_disabled_reason(db, chat_id, "module_mafia")
    if reason:
        return await answer(query, reason, alert=True)
    if not await bot_can_moderate(bot, chat_id):
        return await answer(query, "Боту больше нельзя удалять сообщения. Верни ему право «Удалять сообщения» и нажми «Начать» снова.", alert=True)
    players = await repo.players(db, match_id=data.match_id)
    gone = await absent_players(bot, chat_id, players)
    if gone:   # вышел из чата — значит, играть не будет: убираем его из лобби, а не держим старт
        for player in gone:
            try:
                await mafia.leave_lobby(db, match_id=data.match_id, chat_id=chat_id, user_id=int(player["user_id"]))
            except mafia.MafiaError:
                pass
        fresh = await mafia.current_view(db, match_id=data.match_id)
        if fresh and not await _redraw(message, lobby_text(fresh), lobby_keyboard(fresh, await bot_username(bot))):
            await post_lobby(bot, db, fresh, topic_of(message))
        names = ", ".join(p["display_name"] for p in gone[:3])
        return await answer(query, f"Вышли из чата и убраны из лобби: {names}. Нажми «Начать» ещё раз.", alert=True)
    problem = await _preflight(bot, db, chat_id, data.match_id)
    if problem:
        return await answer(query, problem, alert=True)
    try:
        view, _ = await mafia.start_match(db, match_id=data.match_id, chat_id=int(message.chat.id), actor_id=user_id)
    except mafia.MafiaError as exc:
        return await answer(query, str(exc), alert=True)
    # Roles, the retired lobby card and the first night card are one stored event: a Telegram
    # flood in the middle of 20 DMs resumes on the next scheduler pass instead of losing anyone.
    await deliver_for_match(bot, db, view["match_id"])
    now = await mafia.current_view(db, match_id=view["match_id"])
    if now and now["phase"] == "cancelled":
        return await answer(query, "Не всем удалось доставить роль — партия отменена.", alert=True)
    delayed = (await repo.get_match(db, match_id=view["match_id"]) or {}).get("pending_event_json") is not None
    await answer(query, "Роли рассылаются — через несколько секунд всё будет готово." if delayed
                 else "Роли отправлены в личку. Начинается ночь.")


@router.callback_query(MafiaLobbyCB.filter())
async def cb_mafia_lobby(query: types.CallbackQuery, callback_data: MafiaLobbyCB, db, bot: Bot):
    message = query.message
    if not isinstance(message, types.Message):
        return await answer(query, _TOO_OLD, alert=True)
    if message.chat.type == "private":
        return await answer(query, "Эта кнопка работает только в игровой группе.", alert=True)
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await answer(query, _OFF, alert=True)
    action, chat_id, user_id = callback_data.action, int(message.chat.id), int(query.from_user.id)
    try:
        if action == "start":
            return await _start(query, db, bot, callback_data)
        if action == "join":
            reason = await module_disabled_reason(db, chat_id, "module_mafia")
            if reason:
                return await answer(query, reason, alert=True)
            view, notice = await _join(query, db, bot, callback_data), "Ты в лобби! Жди старта — роль придёт в личку."
            if view is None:
                return
        elif action == "leave":
            view = await mafia.leave_lobby(db, match_id=callback_data.match_id, chat_id=chat_id, user_id=user_id)
            notice = "Ты вышел из лобби."
        elif action == "cancel":
            current = await repo.active_match(db, chat_id=chat_id, topic_id=topic_of(message))
            if current and int(current["id"]) != int(callback_data.match_id):   # кнопка с карточки старого лобби
                return await answer(query, "Это карточка прошлого лобби. Отмени текущее на его собственной карточке.", alert=True)
            await mafia.cancel_match(db, chat_id=chat_id, topic_id=topic_of(message), actor_id=user_id,
                                     is_admin=await is_chat_admin(bot, chat_id, user_id))
            await deliver_for_match(bot, db, callback_data.match_id)
            return await answer(query, "Лобби отменено.")
        elif action == "settings":
            return await _open_settings(query, db, callback_data, user_id)
        else:
            return await answer(query, "Неизвестное действие.", alert=True)
    except mafia.MafiaError as exc:
        return await answer(query, str(exc), alert=True)
    if not await _redraw(message, lobby_text(view), lobby_keyboard(view, await bot_username(bot))):
        await post_lobby(bot, db, view, topic_of(message))
    await answer(query, notice)


async def _open_settings(query, db, data: MafiaLobbyCB, user_id: int) -> None:
    view = await mafia.current_view(db, match_id=data.match_id)
    if not view or int(view["chat_id"]) != int(query.message.chat.id) or view["phase"] != "lobby":
        return await answer(query, "Это лобби больше не активно.", alert=True)
    if int(view["initiator_id"]) != user_id:
        return await answer(query, "Настройки меняет только хозяин лобби.", alert=True)
    await _redraw(query.message, settings_text(view), settings_keyboard(view))
    await answer(query, "Настрой лобби кнопками.")


async def _redraw(message: types.Message, text: str, markup) -> bool:
    """Edit the card.  False when the card is gone (deleted by an admin) and must be re-posted."""
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        lowered = str(exc).lower()
        if "not modified" in lowered:
            return True
        logger.debug(f"Mafia card redraw failed: {exc}")
        return not any(marker in lowered for marker in ("not found", "can't be edited", "message_id_invalid"))
    return True


# ── settings buttons ────────────────────────────────────────────────────────
class NewSettings(NamedTuple):
    seats: int
    roles: set
    vote: str
    tempo: str
    auto: bool
    section: str | None


def apply_setting(view: dict, action: str) -> NewSettings:
    """Pure: the settings after one button press (and which sub-screen to show next)."""
    seats, roles, vote, tempo = int(view["max_players"]), set(view["enabled_roles"]), view["vote_mode"], view.get("tempo", "normal")
    auto = bool(view.get("roles_auto", True))
    if action.startswith("preset_"):
        key = action.removeprefix("preset_")
        if key not in PRESETS:
            raise mafia.MafiaConflict("Неизвестная настройка.")
        roles = set(PRESETS[key][1])
        return NewSettings(max(seats, 8) if "don" in roles else seats, roles, vote, tempo, key == "auto", None)
    kind, _, value = action.partition("_")
    if kind == "slots" and value.isdecimal() and int(value) in LOBBY_SIZE_OPTIONS:
        return NewSettings(int(value), roles, vote, tempo, auto, "players")
    if kind == "role" and value in rules.OPTIONAL_ROLES:
        if auto:  # leaving «авто»: start from what auto would give for a full table
            roles = set(rules.auto_roles(max(len(view["players"]), rules.MIN_PLAYERS)))
        roles.symmetric_difference_update({value})
        return NewSettings(seats, roles, vote, tempo, False, "roles")
    if kind == "vote" and value in ("open", "secret"):
        return NewSettings(seats, roles, value, tempo, auto, "vote")
    if kind == "tempo" and value in rules.TEMPOS:
        return NewSettings(seats, roles, vote, value, auto, "tempo")
    raise mafia.MafiaConflict("Неизвестная настройка.")


@router.callback_query(MafiaSettingsCB.filter())
async def cb_mafia_settings(query: types.CallbackQuery, callback_data: MafiaSettingsCB, db, bot: Bot):
    """Host-only settings flow, kept on the lobby card."""
    message = query.message
    if not isinstance(message, types.Message):
        return await answer(query, _TOO_OLD, alert=True)
    if message.chat.type == "private":
        return await answer(query, "Настройки доступны только в игровой группе.", alert=True)
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await answer(query, _OFF, alert=True)
    view = await mafia.current_view(db, match_id=callback_data.match_id)
    if not view or int(view["chat_id"]) != int(message.chat.id) or view["phase"] != "lobby":
        return await answer(query, "Это лобби больше не активно.", alert=True)
    if int(view["initiator_id"]) != int(query.from_user.id):
        return await answer(query, "Настройки меняет только хозяин лобби.", alert=True)
    action = callback_data.action
    if action == "back":
        await _redraw(message, lobby_text(view), lobby_keyboard(view, await bot_username(bot)))
        return await answer(query, "Вернулись к лобби.")
    if action == "menu" or action.startswith("open_"):
        section = None if action == "menu" else action.removeprefix("open_")
        await _redraw(message, settings_text(view, section), settings_keyboard(view, section))
        return await answer(query)
    try:
        new = apply_setting(view, action)
        view = await mafia.change_settings(db, match_id=callback_data.match_id, chat_id=int(message.chat.id),
                                           topic_id=topic_of(message), actor_id=int(query.from_user.id), max_players=new.seats,
                                           enabled_roles=tuple(sorted(new.roles)), vote_mode=new.vote, tempo=new.tempo,
                                           roles_auto=new.auto)
    except mafia.MafiaError as exc:
        return await answer(query, str(exc), alert=True)
    await _redraw(message, settings_text(view, new.section), settings_keyboard(view, new.section))
    await answer(query, "Сохранено.")


# ── DM: «Я готов», rules, deep links ────────────────────────────────────────
@router.callback_query(MafiaReadyCB.filter())
async def cb_mafia_ready(query: types.CallbackQuery, callback_data: MafiaReadyCB, db):
    message = query.message
    if not message or message.chat.type != "private" or callback_data.action != "ready":
        return await answer(query, "Эта кнопка работает только в личке с ботом.", alert=True)
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await answer(query, _OFF, alert=True)
    await mafia.confirm_dm_ready(db, user_id=int(query.from_user.id))
    if isinstance(message, types.Message):   # у «недоступного» (старше 48 часов) сообщения править нечего
        await _redraw(message, "✅ <b>Личка готова.</b> Теперь вернись в группу и нажми «Войти» в лобби.", None)
    await answer(query, "Готово. Теперь вернись в группу и нажми «Войти» в лобби.")


@router.callback_query(MafiaRulesCB.filter())
async def cb_mafia_rules(query: types.CallbackQuery, callback_data: MafiaRulesCB, bot: Bot):
    message = query.message
    if not message:
        return await answer(query, copy.rules_alert(), alert=True)
    if message.chat.type == "private":
        if not isinstance(message, types.Message):   # карточка старше 48 часов: править нельзя, шлём правила заново
            await bot.send_message(message.chat.id, copy.rules_page(callback_data.page), parse_mode="HTML",
                                   reply_markup=rules_keyboard(callback_data.page))
        else:
            await _redraw(message, copy.rules_page(callback_data.page), rules_keyboard(callback_data.page))
        return await answer(query)
    url = rules_url(await bot_username(bot))
    await answer(query, copy.rules_alert(), alert=True, url=url)


async def send_rules(message: types.Message, page: str = "intro") -> None:
    await message.answer(copy.rules_page(page), reply_markup=rules_keyboard(page), parse_mode="HTML")


async def _deep_join(message: types.Message, db, bot: Bot, match_id: int) -> None:
    user = message.from_user
    view = await mafia.current_view(db, match_id=match_id)
    if not view or view["phase"] != "lobby":
        return await message.answer("Это лобби уже закрыто или игра началась. Попроси друзей собрать новое: «бот мафия» в группе.")
    try:
        member = await bot.get_chat_member(view["chat_id"], int(user.id))
    except TelegramAPIError:
        member = None
    if member is None or member.status not in {"member", "administrator", "creator", "restricted"}:
        return await message.answer("Сначала вступи в группу, где идёт игра, а потом нажми «Войти» там.")
    await mafia.confirm_dm_ready(db, user_id=int(user.id))
    try:
        view = await mafia.join_lobby_by_id(db, match_id=match_id, user_id=int(user.id), username=user.username,
                                            display_name=user.full_name)
    except mafia.MafiaError as exc:
        return await message.answer(f"❌ {exc}")
    if view.get("lobby_message_id"):
        try:
            await bot.edit_message_text(lobby_text(view), chat_id=view["chat_id"], message_id=view["lobby_message_id"],
                                        reply_markup=lobby_keyboard(view, await bot_username(bot)), parse_mode="HTML")
        except TelegramAPIError as exc:
            logger.debug(f"Mafia lobby card not refreshed after deep-link join: {exc}")
    await message.answer(
        "✅ <b>Ты в лобби Мафии!</b>\nВернись в групповой чат. Когда хозяин нажмёт «Начать», роль придёт сюда, в этот чат.\n"
        "<i>Не выключай уведомления от бота.</i>", parse_mode="HTML")


async def handle_start_payload(message: types.Message, payload: str, db, bot: Bot) -> bool:
    """Deep links from the group: ``mrules``, ``mr`` (ready), ``mj<id>`` (join).  True when handled."""
    if payload == "mrules":
        await send_rules(message)
    elif payload == "mr":
        await _private_entry(message, db, "ready")
    elif payload.startswith("mj") and payload[2:].isdecimal() and len(payload) <= 20:
        await _deep_join(message, db, bot, int(payload[2:]))
    else:
        return False
    return True


# ── Ворота сообщений, подъём карточки, пауза при чистке (зовёт bot.chat.on_message) ──

async def gate_message(db, bot: Bot, message: types.Message) -> bool:
    """Фаза партии решает, кому можно писать. True — сообщение обработано (удалено), дальше не идёт.

    Зрители не ограничены никогда; живые игроки молчат ночью, выбывшие — днём. Команды управления
    Мафией («стоп», «правила», «статус», «продолжить») проходят всегда."""
    if message.chat.type not in ("group", "supergroup") or not message.from_user or message.from_user.is_bot:
        return False
    if not await feature_enabled(db, "game_mafia_v1"):
        return False
    topic_id = topic_of(message)
    gate = await mafia.message_gate(db, chat_id=int(message.chat.id), topic_id=topic_id, user_id=int(message.from_user.id))
    if gate != "suppress":
        return False
    if await _is_control_command(bot, message):
        return False
    try:
        await message.delete()
        return True
    except Exception as error:  # noqa: BLE001 - classified below
        if not await deletion_blocked(bot, int(message.chat.id), error):
            logger.debug(f"Mafia gate: message not removed ({error}); rights are fine, game continues")
            return True
        active = await repo.active_match(db, chat_id=int(message.chat.id), topic_id=topic_id)
        if active:  # right really lost: pause instead of pretending the phase is protected
            await _pause_and_show(db, bot, int(active["id"]))
        return False


async def _is_control_command(bot: Bot, message: types.Message) -> bool:
    """Это та самая команда управления, которую диспетчер выполнит («бот мафия стоп», «bot mafia stop», «@бот мафия стоп»)?"""
    parsed = parse_chat_command(registry, message.text or message.caption or "", (await bot.me()).username)
    if not isinstance(parsed, Parsed) or parsed.command.name != "мафия":
        return False
    command = mafia_command.parse(f"бот мафия {parsed.args}")
    return bool(command and command.kind in mafia_command.GATE_BYPASS_KINDS)


async def pause_for_purge(db, bot: Bot, chat_id: int, topic_id: int | None) -> None:
    """Чистка и партия не могут управлять одними сообщениями: партия встаёт на паузу."""
    if not await feature_enabled(db, "game_mafia_v1"):
        return
    active = await repo.active_match(db, chat_id=chat_id, topic_id=topic_id)
    if active:
        await _pause_and_show(db, bot, int(active["id"]))


async def _pause_and_show(db, bot: Bot, match_id: int) -> None:
    await mafia.pause_for_moderation_intervention(db, match_id=match_id)
    try:
        view = await mafia.current_view(db, match_id=match_id)
        if view and view["phase"] == "paused":   # лобби на паузу не ставится: карточку «голосования» там показывать нельзя
            await publish_phase(bot, db, view, gap=0)
    except Exception as error:  # noqa: BLE001 - the stored pause is authoritative
        logger.debug(f"Mafia pause card update failed: {error}")


async def after_message(db, bot: Bot, message: types.Message) -> None:
    """Чат закопал карточку игры: вернуть её вниз (не чаще раза в 90 секунд, старая удаляется)."""
    if message.chat.type not in ("group", "supergroup") or not message.from_user or message.from_user.is_bot:
        return
    if not await feature_enabled(db, "game_mafia_v1"):
        return
    view = await mafia.note_chat_message(db, chat_id=int(message.chat.id), topic_id=topic_of(message))
    if view:
        await bump_card(bot, db, view)
