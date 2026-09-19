"""Telegram adapter for the approved group-chat Mafia v1 lobby."""
from __future__ import annotations

from aiogram import Bot, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import answer_group_only
from bot.middlewares.module_check_mw import module_disabled_reason
from core import mafia_v1 as rules
from services import mafia_v1 as mafia
from services.utils import feature_guard, safe_html


router = Router(name="mafia_v1_router")


class MafiaLobbyCB(CallbackData, prefix="mf"):
    match_id: int
    action: str


class MafiaSettingsCB(CallbackData, prefix="mfs"):
    match_id: int
    action: str


class MafiaControlCB(CallbackData, prefix="mfc"):
    match_id: int
    action: str


LOBBY_SIZE_OPTIONS = (4, 6, 8, 10, 12, 16, 20)


class MafiaReadyCB(CallbackData, prefix="mfr"):
    action: str


class MafiaActionCB(CallbackData, prefix="mfa"):
    match_id: int
    phase_number: int
    action: str
    target_user_id: int


def _topic(message: types.Message) -> int | None:
    return getattr(message, "message_thread_id", None)


def _lobby_text(view: dict) -> str:
    players = view["players"]
    roles = set(view["enabled_roles"])
    role_label = " · ".join(["Мирные", "Мафия"] + [rules.public_role_name(role) for role in rules.OPTIONAL_ROLES if role in roles])
    members = "\n".join(
        f"{index}. {safe_html(player['display_name'])}" for index, player in enumerate(players, start=1)
    ) or "Пока никто не вошёл."
    vote = "открытое" if view["vote_mode"] == "open" else "скрытое"
    return (
        "🕵️ <b>МАФИЯ — ЛОББИ</b>\n"
        f"Места: <b>{len(players)}/{view['max_players']}</b> · голосование: <b>{vote}</b>\n"
        f"Роли: <i>{role_label}</i>\n\n"
        f"{members}\n\n"
        "<b>Что делать:</b> 1) нажми «Войти»; 2) открой личку с ботом и нажми «Я готов»; 3) создатель начнёт партию."
    )


def _lobby_keyboard(view: dict) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Войти", callback_data=MafiaLobbyCB(match_id=view["match_id"], action="join"))
    builder.button(text="↩️ Выйти", callback_data=MafiaLobbyCB(match_id=view["match_id"], action="leave"))
    builder.button(text="⚙️ Настройки", callback_data=MafiaLobbyCB(match_id=view["match_id"], action="settings"))
    builder.button(text="▶️ Начать", callback_data=MafiaLobbyCB(match_id=view["match_id"], action="start"))
    builder.button(text="✖️ Отменить лобби", callback_data=MafiaLobbyCB(match_id=view["match_id"], action="cancel"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def _settings_text(view: dict, section: str | None = None) -> str:
    roles = set(view["enabled_roles"])
    role_label = ", ".join(rules.public_role_name(role) for role in rules.OPTIONAL_ROLES if role in roles) or "только базовые"
    vote = "открытое" if view["vote_mode"] == "open" else "скрытое"
    if section == "players":
        return (
            "👥 <b>Размер лобби</b>\n\n"
            f"Сейчас: <b>{view['max_players']} игроков</b>.\n"
            "Нажми ‹ или ›, чтобы изменить максимум. Старт — от 4 игроков."
        )
    if section == "roles":
        return "🎭 <b>Дополнительные роли</b>\n\nНажми роль, чтобы включить или выключить её. Мирный житель и Мафия есть всегда."
    if section == "vote":
        return "🗳 <b>Как голосуем?</b>\n\nПри скрытом голосовании выборы не видны до конца фазы. При открытом — видны сразу."
    return (
        "⚙️ <b>Настройка партии</b>\n\n"
        f"👥 <b>Игроков:</b> {view['max_players']}\n"
        f"🎭 <b>Доп. роли:</b> {role_label}\n"
        f"🗳 <b>Голосование:</b> {vote}\n\n"
        "Нажми строку, чтобы изменить параметр. Изменения сохраняются сразу."
    )


def _settings_keyboard(view: dict, section: str | None = None) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if section is None:
        role_count = len(view["enabled_roles"])
        vote = "Открыто" if view["vote_mode"] == "open" else "Скрыто"
        role_summary = "Базовые" if role_count == 0 else f"+{role_count}"
        builder.button(text=f"👥 Игроки · {view['max_players']}", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="open_players"))
        builder.button(text=f"🎭 Роли · {role_summary}", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="open_roles"))
        builder.button(text=f"🗳 Голосование · {vote}", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="open_vote"))
        builder.button(text="✓ Готово — к лобби", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="back"))
        builder.adjust(1, 1, 1, 1)
        return builder.as_markup()
    if section == "players":
        seats = int(view["max_players"])
        index = LOBBY_SIZE_OPTIONS.index(seats)
        previous = LOBBY_SIZE_OPTIONS[max(0, index - 1)]
        following = LOBBY_SIZE_OPTIONS[min(len(LOBBY_SIZE_OPTIONS) - 1, index + 1)]
        builder.button(text=f"‹ {previous}", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="slots_prev"))
        builder.button(text=f"✓ {seats} игроков", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="slots_current"))
        builder.button(text=f"{following} ›", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="slots_next"))
        builder.button(text="← Назад", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="menu"))
        builder.adjust(3, 1)
        return builder.as_markup()
    if section == "roles":
        selected_roles = set(view["enabled_roles"])
        for role in rules.OPTIONAL_ROLES:
            builder.button(
                text=("✓ " if role in selected_roles else "") + rules.public_role_name(role),
                callback_data=MafiaSettingsCB(match_id=view["match_id"], action=f"role_{role}"),
            )
        builder.button(text="← Назад", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="menu"))
        builder.adjust(1, 1, 1, 1)
        return builder.as_markup()
    if section == "vote":
        for vote_mode, label in (("secret", "Скрытое"), ("open", "Открытое")):
            builder.button(text=("✓ " if view["vote_mode"] == vote_mode else "") + label,
                           callback_data=MafiaSettingsCB(match_id=view["match_id"], action=f"vote_{vote_mode}"))
        builder.button(text="← Назад", callback_data=MafiaSettingsCB(match_id=view["match_id"], action="menu"))
        builder.adjust(2, 1)
        return builder.as_markup()
    return builder.as_markup()


def _phase_text(view: dict) -> str:
    phase = view["phase"]
    labels = {"night": "🌙 НОЧЬ", "discussion": "☀️ ОБСУЖДЕНИЕ", "voting": "🗳 ГОЛОСОВАНИЕ", "paused": "⏸ ПАРТИЯ НА ПАУЗЕ", "finished": "🏁 ПАРТИЯ ЗАВЕРШЕНА"}
    if phase == "finished":
        winner = "Мирные" if view["winner"] == "town" else "Мафия" if view["winner"] == "mafia" else "Ничья"
        return f"🕵️ <b>{labels[phase]}</b>\nПобеда: <b>{winner}</b>."
    if phase == "paused":
        return (
            f"🕵️ <b>{labels[phase]}</b>\n"
            "Игра остановлена, чтобы не мешать настройкам группы. После устранения причины создатель нажмёт «Продолжить»."
        )
    deadline = view.get("phase_deadline")
    seconds = max(0, int((deadline - view["server_time"]).total_seconds())) if deadline and view.get("server_time") else 0
    if phase == "night":
        detail = "Проверь личку с ботом: там придёт ночное действие или сообщение, что можно ждать утра. В группу сейчас не пиши."
    elif phase == "discussion":
        detail = "Обсуждайте подозрения прямо в этом чате. Писать могут живые участники партии; затем начнётся голосование."
    else:
        detail = "Выбери игрока кнопкой ниже. До конца времени голос можно изменить; обычный чат для участников на этой фазе закрыт."
        if view["vote_mode"] == "open":
            votes = view.get("open_votes", [])
            tally = "\n".join(
                f"• {safe_html(item['target_name'])}: {', '.join(safe_html(name) for name in item['voters'])}"
                for item in votes
            ) or "Пока никто не проголосовал."
            detail += f"\n\n<b>Открытые голоса:</b>\n{tally}"
    return f"🕵️ <b>{labels.get(phase, phase.upper())}</b>\n⏳ Осталось: <b>{seconds // 60}:{seconds % 60:02d}</b>\n{detail}"


def _phase_keyboard(view: dict) -> types.InlineKeyboardMarkup | None:
    if view["phase"] == "paused":
        builder = InlineKeyboardBuilder()
        builder.button(text="▶️ Продолжить", callback_data=MafiaControlCB(match_id=view["match_id"], action="resume"))
        builder.button(text="✖️ Завершить партию", callback_data=MafiaControlCB(match_id=view["match_id"], action="cancel"))
        builder.adjust(1, 1)
        return builder.as_markup()
    if view["phase"] != "voting":
        return None
    builder = InlineKeyboardBuilder()
    for player in view["players"]:
        if player["alive"]:
            builder.button(
                text=f"Голос за #{player['join_order']}: {player['display_name'][:22]}",
                callback_data=MafiaActionCB(match_id=view["match_id"], phase_number=view["phase_number"], action="vote", target_user_id=player["user_id"]),
            )
    builder.adjust(1)
    return builder.as_markup()


def _night_keyboard(*, match_id: int, phase_number: int, role: str, players: list[dict], actor_id: int) -> types.InlineKeyboardMarkup | None:
    action = {"mafia": "mafia_target", "don": "mafia_target", "doctor": "doctor_save", "detective": "detective_check"}.get(role)
    if not action:
        return None
    builder = InlineKeyboardBuilder()
    for player in players:
        if (not player["alive"] or (action == "detective_check" and int(player["user_id"]) == int(actor_id))
                or (action == "mafia_target" and player.get("role") in {"mafia", "don"})):
            continue
        builder.button(
            text=f"#{player['join_order']}: {safe_html(player['display_name'])[:24]}",
            callback_data=MafiaActionCB(match_id=match_id, phase_number=phase_number, action=action, target_user_id=player["user_id"]),
        )
    builder.adjust(1)
    return builder.as_markup()


async def _send_night_prompts(bot: Bot, *, match_id: int, phase_number: int, roles_by_user: dict[int, str],
                              players: list[dict], include_role: bool = False) -> list[int]:
    failed: list[int] = []
    for user_id, role in roles_by_user.items():
        keyboard = _night_keyboard(match_id=match_id, phase_number=phase_number, role=role, players=players, actor_id=user_id)
        # At game start every player must receive their role, including a
        # citizen who has no night action.  On later nights only actionable
        # roles receive a prompt.
        if keyboard is None and not include_role:
            continue
        night_text = {
            "mafia": "🌙 Ночь. Выбери цель мафии.", "don": "🌙 Ночь. Выбери цель мафии.",
            "doctor": "🌙 Ночь. Выбери, кого защитить.", "detective": "🌙 Ночь. Выбери, кого проверить.",
        }.get(role, "Ночью у твоей роли нет действия.")
        text = night_text
        if include_role:
            text = f"🕵️ <b>Мафия началась.</b> Твоя роль: <b>{rules.public_role_name(role)}</b>.\n\n{text}\nНе раскрывай роль в группе."
        try:
            await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            failed.append(int(user_id))
    return failed


async def publish_phase(bot: Bot, db, view: dict) -> None:
    """Update one phase card; recreate it only after explicit edit failure."""
    from infrastructure.repositories import mafia_v1 as repo
    text, keyboard = _phase_text(view), _phase_keyboard(view)
    message_id = view.get("phase_message_id")
    try:
        if message_id:
            await bot.edit_message_text(text, chat_id=view["chat_id"], message_id=message_id,
                                        reply_markup=keyboard, parse_mode="HTML")
            return
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
    except Exception:
        pass
    sent = await bot.send_message(view["chat_id"], text, reply_markup=keyboard, parse_mode="HTML",
                                  message_thread_id=view.get("topic_id"))
    await repo.bind_phase_message(db, match_id=view["match_id"], message_id=int(sent.message_id))


async def notify_phase_transition(bot: Bot, db, event: dict) -> None:
    view = event["view"]
    # One concise result line means players never have to infer whether a
    # night/vote removed someone from a silent timer-card change.
    if event.get("previous_phase") in {"night", "voting"}:
        eliminated_id = event.get("eliminated_user_id")
        eliminated = next((player for player in view["players"] if int(player["user_id"]) == int(eliminated_id or 0)), None)
        name = safe_html(eliminated["display_name"]) if eliminated else None
        if event["previous_phase"] == "night":
            result = f"☀️ <b>Рассвет.</b> Из игры выбыл: <b>{name}</b>." if name else "☀️ <b>Рассвет.</b> Ночь прошла спокойно."
        else:
            result = f"🗳 <b>Итог голосования.</b> Из игры выбыл: <b>{name}</b>." if name else "🗳 <b>Итог голосования.</b> Голоса разделились — никто не выбыл."
        try:
            await bot.send_message(view["chat_id"], result, parse_mode="HTML", message_thread_id=view.get("topic_id"))
        except Exception:
            # The durable state and phase card remain authoritative; a failed
            # cosmetic announcement must not repeat/rewind the phase.
            pass
    for check in event.get("private_checks", []):
        result = "с мафией" if check["is_mafia"] else "не с мафией"
        try:
            await bot.send_message(check["user_id"], f"🔎 Проверка завершена: выбранный игрок <b>{result}</b>.", parse_mode="HTML")
        except Exception:
            pass
    if view["phase"] == "night":
        # Roles are intentionally loaded only for private delivery, never put
        # into the public view that reaches the group card.
        from infrastructure.repositories import mafia_v1 as repo
        internal = await repo.players(db, match_id=view["match_id"])
        missed = await _send_night_prompts(bot, match_id=view["match_id"], phase_number=view["phase_number"],
                                           roles_by_user={int(p["user_id"]): p["role"] for p in internal if p["alive"]}, players=internal)
        if missed:
            await mafia.pause_match(db, match_id=view["match_id"], reason="private_action_delivery_failed")
            view = await mafia.current_view(db, match_id=view["match_id"]) or view
    await publish_phase(bot, db, view)


def _parse_create_args(raw: str) -> tuple[int, tuple[str, ...], str]:
    parts = [part for part in (raw or "").lower().replace(",", " ").split() if part]
    seats = 8
    roles: set[str] = set()
    vote = "secret"
    for part in parts:
        if part.isdigit():
            seats = int(part)
        elif part in {"дон", "don"}:
            roles.add("don")
        elif part in {"доктор", "doctor"}:
            roles.add("doctor")
        elif part in {"детектив", "комиссар", "detective"}:
            roles.add("detective")
        elif part in {"открытое", "open"}:
            vote = "open"
        elif part in {"скрытое", "secret"}:
            vote = "secret"
        else:
            raise mafia.MafiaError("Формат: <code>бот мафия, 8 доктор детектив открытое</code>.")
    return seats, tuple(sorted(roles)), vote


async def _bot_can_moderate(bot: Bot, chat_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
    except Exception:
        return False
    return member.status in {"administrator", "creator"} and bool(getattr(member, "can_delete_messages", False))


async def _can_all_players_write(bot: Bot, db, *, chat_id: int, match_id: int) -> tuple[bool, str]:
    """Fresh Telegram membership check; cached chat statistics are insufficient."""
    from infrastructure.repositories import mafia_v1 as repo
    unavailable: list[str] = []
    for player in await repo.players(db, match_id=match_id):
        try:
            member = await bot.get_chat_member(chat_id, int(player["user_id"]))
            active = member.status in {"member", "administrator", "creator", "restricted"}
            can_write = member.status != "restricted" or bool(getattr(member, "can_send_messages", False))
            if not active or not can_write:
                unavailable.append(player["display_name"])
        except Exception:
            unavailable.append(player["display_name"])
    return (not unavailable, ", ".join(safe_html(name) for name in unavailable[:3]))


@router.message(TextCmd(["мафия", "mafia"]))
async def cmd_mafia(message: types.Message, db, bot: Bot, text_args: str = ""):
    if not await feature_guard(message, db, "game_mafia_v1", "Мафия"):
        return
    if message.chat.type == "private":
        if (text_args or "").strip().lower() in {"готов", "ready"}:
            await mafia.confirm_dm_ready(db, user_id=int(message.from_user.id))
            return await message.answer("✅ Готово. Теперь можно вступать в лобби Мафии в группе.")
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Я готов получать роль", callback_data=MafiaReadyCB(action="ready"))
        return await message.answer(
            "🕵️ <b>Мафия проходит в группе.</b>\n\n"
            "Перед вступлением в лобби нажми кнопку ниже. Так бот сможет прислать тебе личную роль и ночные действия.",
            reply_markup=keyboard.as_markup(), parse_mode="HTML",
        )
    if (text_args or "").strip().lower() in {"продолжить", "resume"}:
        if not await _bot_can_moderate(bot, int(message.chat.id)):
            return await message.answer("❌ Для продолжения Мафии боту всё ещё нужны права на удаление сообщений.")
        try:
            view = await mafia.resume_match(
                db, chat_id=int(message.chat.id), topic_id=_topic(message), actor_id=int(message.from_user.id),
            )
            await publish_phase(bot, db, view)
        except mafia.MafiaError as exc:
            return await message.answer(f"❌ {exc}")
        return await message.answer("▶️ Партия продолжена. Таймер восстановлен с оставшимся временем.")
    if (text_args or "").strip().lower() in {"стоп", "stop", "отмена", "cancel"}:
        try:
            await mafia.cancel_match(
                db, chat_id=int(message.chat.id), topic_id=_topic(message), actor_id=int(message.from_user.id),
            )
        except mafia.MafiaError as exc:
            return await message.answer(f"❌ {exc}")
        return await message.answer("🛑 Партия Мафии остановлена. Настройки чата не менялись.")
    if not await _bot_can_moderate(bot, int(message.chat.id)):
        return await message.answer("❌ Для Мафии боту нужны права администратора на удаление сообщений.")
    disabled_reason = await module_disabled_reason(db, int(message.chat.id), "module_mafia")
    if disabled_reason:
        return await message.answer(f"🔧 {safe_html(disabled_reason)}", parse_mode="HTML")
    try:
        seats, enabled, vote_mode = _parse_create_args(text_args)
        view = await mafia.create_lobby(
            db, chat_id=int(message.chat.id), topic_id=_topic(message), initiator_id=int(message.from_user.id),
            username=message.from_user.username, display_name=message.from_user.full_name,
            max_players=seats, enabled_roles=enabled, vote_mode=vote_mode,
        )
    except mafia.MafiaError as exc:
        return await message.answer(f"❌ {exc}", parse_mode="HTML")
    sent = await message.answer(_lobby_text(view), reply_markup=_lobby_keyboard(view), parse_mode="HTML")
    # A card can be deleted by a group admin. Stored state remains valid; a
    # later lobby repost deliberately binds a new bottom-most card.
    from infrastructure.repositories import mafia_v1 as repo
    await repo.bind_lobby_message(db, match_id=view["match_id"], message_id=int(sent.message_id))


@router.callback_query(MafiaLobbyCB.filter())
async def cb_mafia_lobby(query: types.CallbackQuery, callback_data: MafiaLobbyCB, db, bot: Bot):
    message = query.message
    if not message or message.chat.type == "private":
        return await query.answer("Эта кнопка работает только в игровой группе.", show_alert=True)
    from infrastructure.repositories import system_flags
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await query.answer("Мафия пока выключена разработчиком.", show_alert=True)
    action = callback_data.action
    chat_id, user_id = int(message.chat.id), int(query.from_user.id)
    try:
        if action == "join":
            view = await mafia.join_lobby(
                db, match_id=callback_data.match_id, chat_id=chat_id, topic_id=_topic(message), user_id=user_id,
                username=query.from_user.username, display_name=query.from_user.full_name,
            )
            notice = "Ты в лобби. Не забудь подтвердить личку с ботом."
        elif action == "leave":
            view = await mafia.leave_lobby(db, match_id=callback_data.match_id, chat_id=chat_id, user_id=user_id)
            notice = "Ты вышел из лобби."
        elif action == "cancel":
            view = await mafia.cancel_match(db, chat_id=chat_id, topic_id=_topic(message), actor_id=user_id)
            try:
                await message.edit_text("🛑 <b>Лобби Мафии отменено создателем.</b>", reply_markup=None, parse_mode="HTML")
            except Exception:
                pass
            return await query.answer("Лобби отменено.")
        elif action == "settings":
            view = await mafia.current_view(db, match_id=callback_data.match_id)
            if not view or int(view["chat_id"]) != chat_id or (view["topic_id"] or None) != (_topic(message) or None):
                return await query.answer("Это лобби больше не активно.", show_alert=True)
            if int(view["initiator_id"]) != user_id:
                return await query.answer("Настройки меняет только создатель лобби.", show_alert=True)
            await message.edit_text(_settings_text(view), reply_markup=_settings_keyboard(view), parse_mode="HTML")
            return await query.answer("Настрой лобби кнопками.")
        elif action == "start":
            ok, names = await _can_all_players_write(bot, db, chat_id=chat_id, match_id=callback_data.match_id)
            if not ok:
                return await query.answer(f"Перед стартом недоступны игроки: {names}", show_alert=True)
            view, roles_by_user = await mafia.start_match(db, match_id=callback_data.match_id, chat_id=chat_id, actor_id=user_id)
            from infrastructure.repositories import mafia_v1 as repo
            internal_players = await repo.players(db, match_id=view["match_id"])
            failed = await _send_night_prompts(
                bot, match_id=view["match_id"], phase_number=view["phase_number"], roles_by_user=roles_by_user,
                players=internal_players, include_role=True,
            )
            if failed:
                # Do not let a party continue when even one participant missed
                # their private role. A later relaunch produces a new deck.
                async with db.connection.transaction():
                    row = await repo.lock_match(db, match_id=callback_data.match_id)
                    if row and row["phase"] == "night":
                        await repo.update_match(db, match_id=callback_data.match_id, phase="cancelled", phase_number=int(row["phase_number"]), deadline=None,
                                                finished_reason="private_role_delivery_failed")
                return await query.answer("Не всем удалось доставить личную роль; партия отменена.", show_alert=True)
            await publish_phase(bot, db, view)
            notice = "Роли отправлены в личку. Начинается ночь."
        else:
            return await query.answer("Неизвестное действие.", show_alert=True)
    except mafia.MafiaError as exc:
        return await query.answer(str(exc), show_alert=True)
    try:
        if action == "start":
            await message.edit_text(
                "🕵️ <b>МАФИЯ НАЧАЛАСЬ</b>\n\nРоли отправлены в личные сообщения. Ночь уже идёт; участники не пишут в группу.",
                reply_markup=None, parse_mode="HTML",
            )
        else:
            await message.edit_text(_lobby_text(view), reply_markup=_lobby_keyboard(view), parse_mode="HTML")
    except Exception:
        pass
    await query.answer(notice)


@router.callback_query(MafiaReadyCB.filter())
async def cb_mafia_ready(query: types.CallbackQuery, callback_data: MafiaReadyCB, db):
    message = query.message
    if not message or message.chat.type != "private" or callback_data.action != "ready":
        return await query.answer("Эта кнопка работает только в личке с ботом.", show_alert=True)
    from infrastructure.repositories import system_flags
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await query.answer("Мафия пока выключена разработчиком.", show_alert=True)
    await mafia.confirm_dm_ready(db, user_id=int(query.from_user.id))
    try:
        await message.edit_text("✅ <b>Личка готова.</b> Теперь вернись в группу и нажми «Войти» в лобби.", parse_mode="HTML")
    except Exception:
        pass
    await query.answer("Готово.")


@router.callback_query(MafiaSettingsCB.filter())
async def cb_mafia_settings(query: types.CallbackQuery, callback_data: MafiaSettingsCB, db):
    """Small host-only settings flow, kept on the existing lobby card."""
    message = query.message
    if not message or message.chat.type == "private":
        return await query.answer("Настройки доступны только в игровой группе.", show_alert=True)
    from infrastructure.repositories import system_flags
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await query.answer("Мафия пока выключена разработчиком.", show_alert=True)
    chat_id, user_id = int(message.chat.id), int(query.from_user.id)
    view = await mafia.current_view(db, match_id=callback_data.match_id)
    if not view or int(view["chat_id"]) != chat_id or (view["topic_id"] or None) != (_topic(message) or None):
        return await query.answer("Это лобби больше не активно.", show_alert=True)
    if callback_data.action == "back":
        try:
            await message.edit_text(_lobby_text(view), reply_markup=_lobby_keyboard(view), parse_mode="HTML")
        except Exception:
            pass
        return await query.answer("Вернулись к лобби.")
    section = None
    if callback_data.action == "menu":
        try:
            await message.edit_text(_settings_text(view), reply_markup=_settings_keyboard(view), parse_mode="HTML")
        except Exception:
            pass
        return await query.answer("Выбери раздел.")
    if callback_data.action in {"open_players", "open_roles", "open_vote"}:
        section = callback_data.action.removeprefix("open_")
        try:
            await message.edit_text(_settings_text(view, section), reply_markup=_settings_keyboard(view, section), parse_mode="HTML")
        except Exception:
            pass
        return await query.answer("Выбери вариант.")
    try:
        seats, roles, vote_mode = int(view["max_players"]), set(view["enabled_roles"]), view["vote_mode"]
        if callback_data.action.startswith("slots"):
            current_index = LOBBY_SIZE_OPTIONS.index(seats)
            if callback_data.action == "slots_prev":
                seats = LOBBY_SIZE_OPTIONS[max(0, current_index - 1)]
            elif callback_data.action == "slots_next":
                seats = LOBBY_SIZE_OPTIONS[min(len(LOBBY_SIZE_OPTIONS) - 1, current_index + 1)]
            elif callback_data.action == "slots_current":
                return await query.answer(f"Сейчас максимум {seats} игроков.")
            else:
                seats = int(callback_data.action.removeprefix("slots"))
            section = "players"
        elif callback_data.action.startswith("role_"):
            role = callback_data.action.removeprefix("role_")
            if role not in rules.OPTIONAL_ROLES:
                raise mafia.MafiaConflict("Неизвестная роль.")
            roles.symmetric_difference_update({role})
            section = "roles"
        elif callback_data.action.startswith("vote_"):
            vote_mode = callback_data.action.removeprefix("vote_")
            section = "vote"
        else:
            raise mafia.MafiaConflict("Неизвестная настройка.")
        view = await mafia.change_settings(
            db, match_id=callback_data.match_id, chat_id=chat_id, topic_id=_topic(message), actor_id=user_id,
            max_players=seats, enabled_roles=tuple(sorted(roles)), vote_mode=vote_mode,
        )
    except (ValueError, mafia.MafiaError) as exc:
        return await query.answer(str(exc), show_alert=True)
    try:
        await message.edit_text(_settings_text(view, section), reply_markup=_settings_keyboard(view, section), parse_mode="HTML")
    except Exception:
        pass
    await query.answer("Настройка сохранена.")


@router.callback_query(MafiaControlCB.filter())
async def cb_mafia_control(query: types.CallbackQuery, callback_data: MafiaControlCB, db, bot: Bot):
    """Visible recovery controls for a paused match; no command memorisation."""
    message = query.message
    if not message or message.chat.type == "private":
        return await query.answer("Эта кнопка работает только в игровой группе.", show_alert=True)
    from infrastructure.repositories import system_flags
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await query.answer("Мафия пока выключена разработчиком.", show_alert=True)
    chat_id, user_id = int(message.chat.id), int(query.from_user.id)
    try:
        if callback_data.action == "resume":
            if not await _bot_can_moderate(bot, chat_id):
                raise mafia.MafiaConflict("Боту снова нужны права на удаление сообщений, прежде чем продолжать игру.")
            view = await mafia.resume_match(db, chat_id=chat_id, topic_id=_topic(message), actor_id=user_id)
            await publish_phase(bot, db, view)
            return await query.answer("Партия продолжена.")
        if callback_data.action == "cancel":
            await mafia.cancel_match(db, chat_id=chat_id, topic_id=_topic(message), actor_id=user_id)
            try:
                await message.edit_text("🛑 <b>Партия Мафии завершена создателем.</b>", reply_markup=None, parse_mode="HTML")
            except Exception:
                pass
            return await query.answer("Партия завершена.")
        raise mafia.MafiaConflict("Неизвестное действие.")
    except mafia.MafiaError as exc:
        return await query.answer(str(exc), show_alert=True)


@router.callback_query(MafiaActionCB.filter())
async def cb_mafia_action(query: types.CallbackQuery, callback_data: MafiaActionCB, db):
    message = query.message
    if not message:
        return await query.answer("Сообщение с ходом недоступно.", show_alert=True)
    from infrastructure.repositories import mafia_v1 as repo, system_flags
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return await query.answer("Мафия пока выключена разработчиком.", show_alert=True)
    match = await repo.get_match(db, match_id=callback_data.match_id)
    if not match:
        return await query.answer("Партия уже завершена.", show_alert=True)
    private_action = callback_data.action != "vote"
    if private_action and message.chat.type != "private":
        return await query.answer("Ночной ход принимается только в личке с ботом.", show_alert=True)
    if not private_action and int(message.chat.id) != int(match["chat_id"]):
        return await query.answer("Голосовать можно только в исходной группе.", show_alert=True)
    try:
        await mafia.submit_action(
            db, match_id=callback_data.match_id, chat_id=int(match["chat_id"]), user_id=int(query.from_user.id),
            phase_number=callback_data.phase_number, action_type=callback_data.action,
            target_user_id=callback_data.target_user_id,
            source_message_id=None if private_action else int(message.message_id),
        )
    except mafia.MafiaError as exc:
        return await query.answer(str(exc), show_alert=True)
    await query.answer("Ход принят. До конца фазы его можно изменить.")
