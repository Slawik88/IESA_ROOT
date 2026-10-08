"""Player-facing Russian copy for chat Mafia, written for people who have never played.

Rules of this file: plain words (no "фракция", "тай-брейк"), every role says its goal
and what to press, every instruction starts with an obvious verb.  Functions return
Telegram-HTML (names are escaped here) except ``*_alert`` which return plain text
because callback alerts are limited to 200 characters and do not render HTML.
"""
from __future__ import annotations

from html import escape as _esc
from typing import Final, Sequence

ALERT_LIMIT: Final = 200
ACTION_MARK: Final = "👉 <b>Что делать:</b>"  # every group card carries this line

ROLE_EMOJI: Final = {"citizen": "🧑", "mafia": "🔫", "don": "🎩", "doctor": "💉", "detective": "🔎"}
ROLE_NAME: Final = {"citizen": "Мирный житель", "mafia": "Мафия", "don": "Дон мафии",
                    "doctor": "Доктор", "detective": "Детектив"}
ROLE_GOAL: Final = {
    "citizen": "Найти всю мафию и выгнать её голосованием.",
    "mafia": "Остаться незамеченным и убрать мирных: мафия побеждает, когда её не меньше, чем остальных.",
    "don": "То же, что у мафии: остаться незамеченным и убрать мирных.",
    "doctor": "Помочь мирным: спасай тех, кого мафия выбрала жертвой.",
    "detective": "Найти мафию и помочь мирным её выгнать.",
}
ROLE_HOW: Final = {
    "citizen": "Ночью ты спишь — ничего нажимать не нужно. Днём пиши в чат, кого подозреваешь, и голосуй кнопкой.",
    "mafia": "Каждую ночь выбери жертву кнопкой в личке. Днём делай вид, что ты мирный, и не выдавай своих.",
    "don": "Каждую ночь выбери жертву кнопкой. Если мафиози выбрали разных людей — решает Дон. Днём не выдавай себя.",
    "doctor": "Каждую ночь выбери, кого лечить (можно себя). Если мафия выберет его — он выживет. Днём не раскрывай роль.",
    "detective": "Каждую ночь выбери, кого проверить: бот скажет в личку, мафия это или нет. Днём подскажи это аккуратно.",
}
NIGHT_ASK: Final = {
    "mafia": "Выбери жертву мафии.", "don": "Выбери жертву мафии.",
    "doctor": "Выбери, кого вылечить этой ночью.", "detective": "Выбери, кого проверить этой ночью.",
}


def role_label(role: str) -> str:
    return f"{ROLE_EMOJI.get(role, '❔')} {ROLE_NAME.get(role, 'Неизвестная роль')}"


def _team_line(teammates: Sequence[tuple[str, str]]) -> str:
    names = ", ".join(f"{_esc(name)}{' (Дон)' if role == 'don' else ''}" for name, role in teammates)
    return f"\n👥 <b>Твоя команда:</b> {names}" if names else "\n👥 <i>Ты один в команде мафии.</i>"


def role_card(role: str, teammates: Sequence[tuple[str, str]] = (), *, chat_title: str | None = None) -> str:
    """Private message sent once at the start of a game."""
    where = f" в «{_esc(chat_title)}»" if chat_title else ""
    team = _team_line(teammates) if role in ("mafia", "don") else ""
    return (
        f"🕵️ <b>Партия Мафии{where} началась!</b>\n\n"
        f"🎭 Твоя роль: <b>{role_label(role)}</b>\n"
        f"🎯 <b>Цель:</b> {ROLE_GOAL.get(role, '')}\n"
        f"🧭 <b>Что делать:</b> {ROLE_HOW.get(role, '')}{team}\n\n"
        "🤫 <i>Никому не показывай это сообщение — иначе игра теряет смысл.</i>"
    )


def role_alert(role: str, teammates: Sequence[str] = ()) -> str:
    """Private popup for the «Моя роль» button (plain text, <= 200 chars)."""
    base = f"Ты — {ROLE_NAME.get(role, '?')}. {ROLE_GOAL.get(role, '')}"
    if role in ("mafia", "don") and teammates:
        base += f" Команда: {', '.join(teammates)}."
    return base if len(base) <= ALERT_LIMIT else base[: ALERT_LIMIT - 1] + "…"


def night_prompt(role: str, round_no: int, seconds: int, *, first: bool = False) -> str:
    ask = NIGHT_ASK.get(role)
    if not ask:
        return f"🌙 <b>Ночь {round_no}.</b> У твоей роли ночью нет действий — просто жди утра и следи за чатом."
    lead = "Это первая ночь. " if first else ""
    return (f"🌙 <b>Ночь {round_no}.</b> {lead}{ask}\n"
            f"⏳ Времени около {seconds} сек. Нажми на имя — выбор можно поменять до рассвета.")


def vote_prompt(seconds: int) -> str:
    return ("🗳 <b>Голосование.</b> Нажми на имя того, кого хочешь выгнать, или «Никого», если не уверен.\n"
            f"⏳ Времени около {seconds} сек. Выбор можно менять. Это то же самое, что голосовать в чате.")


def night_chosen(label: str, *, can_change: bool = True) -> str:
    tail = " Передумал? Нажми другое имя — до рассвета можно менять." if can_change else ""
    return f"✅ Выбрано: <b>{_esc(label)}</b>.{tail}"


def team_board(rows: Sequence[tuple[str, str, str | None]], leading: str | None) -> str:
    """Mafia-only status: (name, role, chosen target label or None)."""
    lines = []
    for name, role, choice in rows:
        who = _esc(name) + (" (Дон)" if role == "don" else "")
        lines.append(f"• {who}: {('<b>' + _esc(choice) + '</b>') if choice else 'ещё не выбрал(а)'}")
    verdict = f"\nСейчас выбрана жертва: <b>{_esc(leading)}</b>." if leading else "\nЖертва пока не выбрана."
    return ("👥 <b>Команда мафии</b>\n" + "\n".join(lines) + verdict +
            "\n<i>Решает большинство. При равенстве — выбор Дона, а без Дона — кто выбрал раньше.</i>")


def check_result(label: str, is_mafia: bool) -> str:
    verdict = "<b>МАФИЯ</b> 🔫" if is_mafia else "<b>не мафия</b> ✅"
    return f"🔎 <b>Результат проверки:</b> {_esc(label)} — {verdict}.\nИспользуй это знание днём осторожно."


def eliminated_dm() -> str:
    return ("💀 Ты выбыл(а) из игры. Смотреть можно, участвовать — нет: "
            "в обсуждении писать нельзя, голосовать тоже. Спасибо за игру!")


RULES_TITLES: Final = (("intro", "🎯 Что за игра"), ("roles", "🎭 Роли"), ("flow", "🔁 Как идёт партия"), ("tips", "💡 Подсказки"))
_RULES: Final = {
    "intro": (
        "🕵️ <b>Мафия — что это</b>\n\n"
        "Игра про обман и логику. Бот тайно раздаёт роли: большинство игроков — <b>мирные жители</b>, "
        "несколько — <b>мафия</b>. Свою роль знаешь только ты.\n\n"
        "🎯 <b>Мирные</b> хотят найти и выгнать всю мафию.\n"
        "🎯 <b>Мафия</b> хочет остаться незамеченной и убирать мирных.\n\n"
        "Играем прямо в групповом чате, а тайные ходы делаем кнопками в личке с ботом. "
        "Нужно от 4 игроков, партия занимает 10–20 минут."
    ),
    "roles": (
        "🎭 <b>Роли</b>\n\n"
        f"{role_label('citizen')} — ночью спит, днём ищет мафию и голосует.\n"
        f"{role_label('mafia')} — ночью вместе с командой выбирает, кого убрать.\n"
        f"{role_label('don')} — главный в мафии: при споре решает его выбор.\n"
        f"{role_label('doctor')} — ночью лечит одного игрока (можно себя).\n"
        f"{role_label('detective')} — ночью проверяет одного игрока: мафия или нет.\n\n"
        "Доктор, Детектив и Дон — необязательные роли: хозяин лобби включает их в настройках."
    ),
    "flow": (
        "🔁 <b>Как идёт партия</b>\n\n"
        "🌙 <b>Ночь</b> (около минуты). В чат писать нельзя. Мафия, Доктор и Детектив нажимают кнопки в личке с ботом.\n\n"
        "☀️ <b>Обсуждение</b> (около 3 минут). Бот объявляет, кто выбыл. Пишите в чат, спорьте, ищите мафию. "
        "Писать могут только живые игроки.\n\n"
        "🗳 <b>Голосование</b> (около минуты). Нажми на имя того, кого хочешь выгнать. "
        "Больше всех голосов — выбывает. Ничья — не выбывает никто.\n\n"
        "🏁 <b>Конец:</b> мирные побеждают, когда мафии не осталось; мафия — когда её не меньше, чем остальных."
    ),
    "tips": (
        "💡 <b>Подсказки</b>\n\n"
        "• Нажми «Войти». Если бот попросит — открой его и нажми Start: так он сможет прислать тебе роль.\n"
        "• Забыл роль? Нажми «🙋 Моя роль» под сообщением игры — ответ увидишь только ты.\n"
        "• Ночью и во время голосования писать в чат нельзя — сообщение пропадёт. Это не ошибка.\n"
        "• Ночной выбор и голос можно менять до конца времени.\n"
        "• Когда все сделали выбор, этап заканчивается раньше срока.\n"
        "• Если игра зависла, хозяин (или админ чата) нажимает «⏹ Остановить игру»."
    ),
}


def rules_page(key: str) -> str:
    return _RULES.get(key, _RULES["intro"])


def rules_alert() -> str:
    """Tiny popup for a quick tap in the group (plain text)."""
    return ("Мафия ночью убирает мирных, днём все ищут мафию голосованием. "
            "Роль придёт в личку. Подробные правила — по кнопке «Как играть».")
