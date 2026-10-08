"""In-game screens of chat Mafia: phase card, results, night buttons (text + keyboards, no I/O)."""
from __future__ import annotations

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.handlers.mafia_cb import MafiaActionCB, MafiaControlCB
from bot.handlers.mafia_views import rules_url
from core import mafia_copy as copy
from core import mafia_v1 as rules
from services.formatting import safe_html

PAUSE_REASONS = {
    "moderation_intervention": "Боту пришлось остановить игру: ему нужны права удалять сообщения, либо в чате началась чистка.",
    "private_action_delivery_failed": "Боту не удалось написать в личку: {detail}. Им нужно открыть бота и нажать Start.",
}


def _timer(view: dict) -> str:
    deadline, now = view.get("phase_deadline"), view.get("server_time")
    seconds = max(0, int((deadline - now).total_seconds())) if deadline and now else 0
    return f"{seconds // 60}:{seconds % 60:02d}"


def alive_block(view: dict) -> str:
    alive = [p for p in view["players"] if p["alive"]]
    out = [p for p in view["players"] if not p["alive"]]
    text = f"<b>Живы ({len(alive)}):</b> " + " · ".join(f"{p['join_order']}. {safe_html(p['display_name'])}" for p in alive)
    if out:
        text += "\n<b>Выбыли:</b> " + " · ".join(f"{p['join_order']}. {safe_html(p['display_name'])}" for p in out)
    return text


def mentions_line(view: dict) -> str:
    """Ping the living players so seven of forty chatters notice that their phase started."""
    names = [f'<a href="tg://user?id={int(p["user_id"])}">{safe_html(p["display_name"])}</a>' for p in view["players"] if p["alive"]]
    return "🔔 " + ", ".join(names)


def _open_tally(view: dict) -> str:
    if view["vote_mode"] != "open":
        return ""
    rows = [f"• {safe_html(i['target_name'])}: {', '.join(safe_html(n) for n in i['voters'])}" for i in view.get("open_votes", [])]
    return "\n\n<b>Кто за кого:</b>\n" + ("\n".join(rows) or "Пока никто не проголосовал.")


def phase_text(view: dict) -> str:
    phase, mark = view["phase"], copy.ACTION_MARK
    if phase == "finished":
        return "🏁 <b>ИГРА ОКОНЧЕНА</b>\nИтоги и роли всех игроков — в сообщении ниже."
    if phase == "cancelled":
        return "🛑 <b>Игра остановлена.</b> Чтобы сыграть снова, напишите «бот мафия»."
    if phase == "paused":
        reason = PAUSE_REASONS.get(view.get("finished_reason") or "", "Игра приостановлена.")
        reason = reason.format(detail=safe_html(view.get("pause_detail") or "некоторым игрокам"))
        return (f"⏸ <b>ИГРА НА ПАУЗЕ</b>\n{reason}\n\n{mark} исправьте причину, затем хозяин игры "
                "(или админ чата) нажимает «▶️ Продолжить». Время этапа сохранено.")
    rnd = view.get("round_number") or 1
    if phase == "night":
        return (f"🌙 <b>НОЧЬ {rnd}</b> · ⏳ {_timer(view)}\nГород спит. Мафия, Доктор и Детектив делают ходы в личке с ботом.\n\n"
                f"{alive_block(view)}\n\n{mark} не пиши в чат до утра — сообщения исчезнут. Есть ночная роль? Открой личку с ботом: там кнопки.")
    if phase == "discussion":
        return (f"☀️ <b>ДЕНЬ {rnd} · ОБСУЖДЕНИЕ</b> · ⏳ {_timer(view)}\n\n{alive_block(view)}\n\n"
                f"{mark} пиши в чат: спорь, задавай вопросы, ищи мафию. Писать могут только живые игроки. "
                "Когда время выйдет, начнётся голосование.")
    cast = f" · проголосовали {view['votes_cast']} из {view['votes_needed']}" if "votes_cast" in view else ""
    return (f"🗳 <b>ГОЛОСОВАНИЕ</b> · ⏳ {_timer(view)}{cast}\n{mentions_line(view)}\n\n{mark} нажми на имя того, кого хочешь выгнать. "
            "Не уверен — нажми «🚫 Никого». Голос можно менять до конца времени."
            f"{_open_tally(view)}")


def _vote_rows(view: dict) -> list[list[types.InlineKeyboardButton]]:
    tally = {int(i["target_user_id"]): len(i["voters"]) for i in view.get("open_votes", [])}
    mid, num = view["match_id"], view["phase_number"]
    buttons = []
    for p in (p for p in view["players"] if p["alive"]):
        count = f" · {tally[int(p['user_id'])]}" if int(p["user_id"]) in tally else ""
        data = MafiaActionCB(match_id=mid, phase_number=num, action="vote", target_user_id=int(p["user_id"])).pack()
        buttons.append(types.InlineKeyboardButton(text=f"{p['join_order']}. {p['display_name'][:18]}{count}", callback_data=data))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    skip = MafiaActionCB(match_id=mid, phase_number=num, action="vote", target_user_id=0).pack()
    rows.append([types.InlineKeyboardButton(text="🚫 Никого не выгонять", callback_data=skip)])
    return rows


def phase_keyboard(view: dict, username: str | None = None) -> types.InlineKeyboardMarkup | None:
    phase, mid = view["phase"], view["match_id"]
    control = lambda text, action: types.InlineKeyboardButton(  # noqa: E731
        text=text, callback_data=MafiaControlCB(match_id=mid, action=action).pack())
    if phase == "paused":
        return types.InlineKeyboardMarkup(inline_keyboard=[[control("▶️ Продолжить", "resume")], [control("✖️ Завершить партию", "cancel")]])
    if phase == "finished":
        rows = [[control("🔁 Сыграть ещё", "again")]]
        if rules_url(username):
            rows.append([types.InlineKeyboardButton(text="📖 Как играть", url=rules_url(username))])
        return types.InlineKeyboardMarkup(inline_keyboard=rows)
    if phase not in ("night", "discussion", "voting"):
        return None
    rows = _vote_rows(view) if phase == "voting" else []
    rows.append([control("🙋 Моя роль", "role")])
    host = [control("⏹ Остановить игру", "stop_ask")]
    if phase == "discussion":
        host.insert(0, control("⏭ К голосованию", "skip"))
    rows.append(host)
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


def night_keyboard(*, match_id: int, phase_number: int, role: str, players: list[dict], actor_id: int,
                   chosen: int | None = None) -> types.InlineKeyboardMarkup | None:
    action = rules.night_action_for(role)
    if not action:
        return None
    builder = InlineKeyboardBuilder()
    for p in players:
        mafia_ally = action == "mafia_target" and p.get("role") in {"mafia", "don"}
        if not p["alive"] or mafia_ally or (action == "detective_check" and int(p["user_id"]) == int(actor_id)):
            continue
        mark = "✅ " if chosen is not None and int(p["user_id"]) == int(chosen) else ""
        data = MafiaActionCB(match_id=match_id, phase_number=phase_number, action=action, target_user_id=int(p["user_id"]))
        builder.button(text=f"{mark}#{p['join_order']} {p['display_name'][:24]}", callback_data=data)
    builder.adjust(1)
    return builder.as_markup()


def vote_dm_keyboard(*, match_id: int, phase_number: int, players: list[dict], chosen: int | None = None):
    """Voting buttons for the DM copy of the ballot (0 = «Никого»)."""
    builder = InlineKeyboardBuilder()
    for p in (p for p in players if p["alive"]):
        mark = "✅ " if chosen is not None and chosen == int(p["user_id"]) else ""
        data = MafiaActionCB(match_id=match_id, phase_number=phase_number, action="vote", target_user_id=int(p["user_id"]))
        builder.button(text=f"{mark}#{p['join_order']} {p['display_name'][:24]}", callback_data=data)
    skip = MafiaActionCB(match_id=match_id, phase_number=phase_number, action="vote", target_user_id=0)
    builder.button(text=("✅ " if chosen == 0 else "") + "🚫 Никого", callback_data=skip)
    builder.adjust(1)
    return builder.as_markup()


def dawn_text(view: dict, eliminated: dict | None) -> str:
    if eliminated:
        head = f"☀️ <b>Рассвет.</b> Этой ночью из игры выбыл: <b>{safe_html(eliminated['display_name'])}</b>."
    else:
        head = "☀️ <b>Рассвет.</b> Эта ночь прошла спокойно — никто не выбыл."
    if view["phase"] != "discussion":
        return head
    return f"{head}\n{mentions_line(view)}\nНачинается обсуждение — можно писать в чат."


def vote_result_text(eliminated: dict | None) -> str:
    if eliminated:
        return f"🗳 <b>Итог голосования.</b> Город выгнал: <b>{safe_html(eliminated['display_name'])}</b>."
    return "🗳 <b>Итог голосования.</b> Голоса разделились или все воздержались — никто не выбыл."


def abandoned_text() -> str:
    return ("💤 <b>Игра остановлена:</b> несколько этапов подряд никто не нажимал кнопки. "
            "Чтобы сыграть снова, напишите «бот мафия».")


def lobby_closed_text(reason: str) -> str:
    if reason == "lobby_expired":
        return "⌛ <b>Лобби закрыто:</b> 30 минут никто ничего не делал. Напишите «бот мафия», чтобы собрать новое."
    return "🛑 <b>Лобби отменено.</b> Чтобы собрать новое, напишите «бот мафия»."


def finished_text(view: dict) -> str:
    town = view["winner"] == "town"
    head = ("🏁 <b>Игра окончена — победили мирные жители!</b> 🎉" if town
            else "🏁 <b>Игра окончена — победила мафия!</b> 🔫" if view["winner"] == "mafia" else "🏁 <b>Игра окончена.</b>")
    rows = [f"{r['join_order']}. {safe_html(r['display_name'])} — {copy.role_label(r['role'])}"
            f"{'' if r['alive'] else ' (выбыл)'}" for r in view.get("roles_reveal", [])]
    return head + "\n\n<b>Кто кем был:</b>\n" + "\n".join(rows) + "\n\nСпасибо за игру! Хотите ещё партию?"


def stop_confirm_keyboard(match_id: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏹ Да, остановить", callback_data=MafiaControlCB(match_id=match_id, action="stop_yes"))
    builder.button(text="Нет, играем дальше", callback_data=MafiaControlCB(match_id=match_id, action="stop_no"))
    builder.adjust(1)
    return builder.as_markup()
