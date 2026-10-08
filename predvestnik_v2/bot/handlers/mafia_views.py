"""Lobby, settings and rules screens of chat Mafia (text + keyboards, no I/O)."""
from __future__ import annotations

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.handlers.mafia_cb import MafiaLobbyCB, MafiaRulesCB, MafiaSettingsCB
from core import mafia_copy as copy
from core import mafia_v1 as rules
from services.formatting import safe_html

LOBBY_SIZE_OPTIONS = (4, 6, 8, 10, 12, 16, 20)
TEMPO_LABELS = {"fast": "⚡ Быстрый", "normal": "🕒 Обычный", "slow": "🐢 Неспешный"}  # emoji + TEMPO_NAMES
ROLE_HINTS = {
    "doctor": "лечит одного игрока за ночь", "detective": "проверяет, мафия ли игрок",
    "don": "главный в мафии, решает споры (от 8 игроков)",
}
# key -> (button label, fixed roles); «авто» picks roles from the number of players at start.
PRESETS = {"auto": ("Авто", ()), "simple": ("Простая", ()), "classic": ("Классика", ("detective", "doctor")),
           "full": ("Полная", ("detective", "doctor", "don"))}
TEMPO_NAMES = {"fast": "Быстрый", "normal": "Обычный", "slow": "Неспешный"}


def _clock(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds >= 60 else f"{seconds} с"


def tempo_line(tempo: str) -> str:
    night, talk, vote = rules.TEMPOS.get(tempo, rules.TEMPOS[rules.DEFAULT_TEMPO])
    return f"ночь {_clock(night)} · обсуждение {_clock(talk)} · голосование {_clock(vote)}"


def rules_url(username: str | None) -> str | None:
    return f"https://t.me/{username}?start=mrules" if username else None


def join_url(username: str | None, match_id: int) -> str | None:
    return f"https://t.me/{username}?start=mj{int(match_id)}" if username else None


def _roles_label(view: dict) -> str:
    if view.get("roles_auto", True):
        count = max(len(view["players"]), rules.MIN_PLAYERS)
        extra = [rules.public_role_name(r) for r in rules.OPTIONAL_ROLES if r in rules.auto_roles(count)]
        return f"авто — при {count} игроках: Мирные, Мафия" + (" + " + ", ".join(extra) if extra else "")
    extra = [rules.public_role_name(role) for role in rules.OPTIONAL_ROLES if role in set(view["enabled_roles"])]
    return "Мирные, Мафия" + (" + " + ", ".join(extra) if extra else "")


def lobby_text(view: dict) -> str:
    players, need = view["players"], max(0, rules.MIN_PLAYERS - len(view["players"]))
    members = "\n".join(
        f"{i}. {safe_html(p['display_name'])}{' 👑' if int(p['user_id']) == int(view['initiator_id']) else ''}"
        for i, p in enumerate(players, start=1)
    ) or "Пока никого."
    vote = "открытое (видно, кто за кого)" if view["vote_mode"] == "open" else "скрытое"
    go = (f"Нужно ещё <b>{need}</b> — позови друзей." if need
          else "Игроков хватает! Хозяин нажимает «▶️ Начать».")
    return (
        "🕵️ <b>МАФИЯ — набор игроков</b>\n"
        f"Хозяин: <b>{safe_html(view.get('host_name'))}</b> · места <b>{len(players)}/{view['max_players']}</b> · старт от {rules.MIN_PLAYERS}\n\n"
        f"<b>Игроки:</b>\n{members}\n\n"
        f"🎭 Роли: {_roles_label(view)}\n🗳 Голосование: {vote}\n⏱ Темп: {tempo_line(view.get('tempo', 'normal'))}\n\n"
        f"{copy.ACTION_MARK}\n"
        "• Хочешь играть — нажми «➕ Войти». Если бот попросит, открой его и нажми Start: так он пришлёт тебе роль в личку.\n"
        "• Не знаешь, что это за игра? Нажми «📖 Как играть» — объяснение на минуту.\n"
        f"• {go}"
    )


def lobby_keyboard(view: dict, username: str | None = None) -> types.InlineKeyboardMarkup:
    match_id, builder = view["match_id"], InlineKeyboardBuilder()
    builder.button(text="➕ Войти", callback_data=MafiaLobbyCB(match_id=match_id, action="join"))
    builder.button(text="↩️ Выйти", callback_data=MafiaLobbyCB(match_id=match_id, action="leave"))
    url = rules_url(username)
    if url:
        builder.button(text="📖 Как играть", url=url)
    else:
        builder.button(text="📖 Как играть", callback_data=MafiaRulesCB(page="intro"))
    builder.button(text="⚙️ Настройки", callback_data=MafiaLobbyCB(match_id=match_id, action="settings"))
    builder.button(text="▶️ Начать", callback_data=MafiaLobbyCB(match_id=match_id, action="start"))
    builder.button(text="✖️ Отменить лобби", callback_data=MafiaLobbyCB(match_id=match_id, action="cancel"))
    builder.adjust(2, 1, 2, 1)
    return builder.as_markup()


def settings_text(view: dict, section: str | None = None) -> str:
    roles = set(view["enabled_roles"])
    if section == "players":
        return (f"👥 <b>Сколько игроков?</b>\n\nСейчас максимум: <b>{view['max_players']}</b>. "
                "Играть можно уже с 4 — лишние места просто останутся пустыми.")
    if section == "roles":
        lines = "\n".join(f"{'✅' if r in roles else '▫️'} <b>{rules.public_role_name(r)}</b> — {ROLE_HINTS[r]}"
                          for r in rules.OPTIONAL_ROLES)
        return f"🎭 <b>Доп. роли</b>\n\nМирные жители и Мафия есть всегда. Нажми роль, чтобы включить или выключить:\n\n{lines}"
    if section == "vote":
        return ("🗳 <b>Как голосуем?</b>\n\n<b>Скрытое</b> — видно только число проголосовавших.\n"
                "<b>Открытое</b> — все видят, кто за кого. Для новичков проще скрытое.")
    if section == "tempo":
        lines = "\n".join(f"<b>{label}</b> — {tempo_line(key)}" for key, label in TEMPO_LABELS.items())
        return f"⏱ <b>Темп игры</b>\n\n{lines}\n\nЕсли все сделали выбор раньше — этап закончится досрочно."
    chosen = "авто" if view.get("roles_auto", True) else (
        ", ".join(rules.public_role_name(r) for r in rules.OPTIONAL_ROLES if r in roles) or "только базовые")
    return (
        "⚙️ <b>Настройка партии</b>\n\n"
        f"👥 Игроков: <b>{view['max_players']}</b>\n🎭 Доп. роли: <b>{chosen}</b>\n"
        f"🗳 Голосование: <b>{'открытое' if view['vote_mode'] == 'open' else 'скрытое'}</b>\n"
        f"⏱ Темп: <b>{TEMPO_LABELS.get(view.get('tempo'), '')}</b>\n\n"
        "💡 <b>Не знаешь, что выбрать?</b> Оставь «Авто»: бот сам добавит Доктора, Детектива и Дона, когда игроков хватит.\n"
        "Изменения сохраняются сразу."
    )


def settings_keyboard(view: dict, section: str | None = None) -> types.InlineKeyboardMarkup:
    mid, builder = view["match_id"], InlineKeyboardBuilder()
    cb = lambda action: MafiaSettingsCB(match_id=mid, action=action)  # noqa: E731
    if section is None:
        for key, (label, _) in PRESETS.items():
            mark = "✓ " if (key == "auto") == bool(view.get("roles_auto", True)) and key == "auto" else ""
            builder.button(text=f"🪄 {mark}{label}", callback_data=cb(f"preset_{key}"))
        roles = len(view["enabled_roles"])
        builder.button(text=f"👥 Игроки · {view['max_players']}", callback_data=cb("open_players"))
        builder.button(text=f"🎭 Роли · {'авто' if view.get('roles_auto', True) else 'базовые' if roles == 0 else f'+{roles}'}", callback_data=cb("open_roles"))
        builder.button(text=f"🗳 Голосование · {'открытое' if view['vote_mode'] == 'open' else 'скрытое'}", callback_data=cb("open_vote"))
        builder.button(text=f"⏱ Темп · {TEMPO_NAMES.get(view.get('tempo'), '')}", callback_data=cb("open_tempo"))
        builder.button(text="✓ Готово — к лобби", callback_data=cb("back"))
        builder.adjust(2, 2, 1, 1, 1, 1, 1)
        return builder.as_markup()
    if section == "players":
        for seats in LOBBY_SIZE_OPTIONS:
            builder.button(text=("✓ " if seats == view["max_players"] else "") + str(seats), callback_data=cb(f"slots_{seats}"))
        builder.adjust(4, 3)
    elif section == "roles":
        for role in rules.OPTIONAL_ROLES:
            on = role in set(view["enabled_roles"])
            builder.button(text=("✓ " if on else "") + rules.public_role_name(role), callback_data=cb(f"role_{role}"))
        builder.adjust(1)
    elif section == "vote":
        for mode, label in (("secret", "Скрытое"), ("open", "Открытое")):
            builder.button(text=("✓ " if view["vote_mode"] == mode else "") + label, callback_data=cb(f"vote_{mode}"))
        builder.adjust(2)
    elif section == "tempo":
        for key, label in TEMPO_LABELS.items():
            builder.button(text=("✓ " if view.get("tempo") == key else "") + label, callback_data=cb(f"tempo_{key}"))
        builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="← Назад", callback_data=cb("menu").pack()))
    return builder.as_markup()


def rules_keyboard(page: str) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, title in copy.RULES_TITLES:
        builder.button(text=("• " if key == page else "") + title, callback_data=MafiaRulesCB(page=key))
    builder.adjust(2, 2)
    return builder.as_markup()
