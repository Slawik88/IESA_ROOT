"""Player marks. Players see them as «Регалии» (the word «метки» stays between us: code, console, docs).

A mark is a short badge shown in a profile hero and, for the heaviest one, next to a name in lists. Three kinds, and the kind decides who may give it
(nobody can award themselves anything):

* staff    : who runs the bot (developer, senior helper, helper). Given by hand through the console (permission `marks_manage`), never automatically:
             the rank in the bot and the badge in the profile are separate decisions.
* granted  : special marks (founder, partner, champion…), also by hand, with a reason and a log entry; can be taken back.
* earned   : given by the server the first time the player's own data satisfies the rule (a streak, years with the project, a collection, a season
             skin) and kept for good: «retroactive» (the best streak ever counts, not only the current one) and sticky (a streak that breaks later
             takes nothing away). The player never has to farm the same thing twice.
* live     : dynamic: computed on every view and never stored (messages in the last 30 or 60 days). It is worn while the pace holds and disappears when
             it drops, so it says what the player does now, not what they once did.

Display: weight decides the order (staff first), a hero shows the two heaviest as chips and all the rest as small icons, a list row shows one glyph.
Everything here is pure; storage is infrastructure/repositories/marks_v1.py, composition is services/marks_v1.py.
"""
from __future__ import annotations

from typing import Final

KINDS: Final = ("staff", "granted", "earned", "live")
PLAYER_NAME: Final = "Регалии"
# CSS tone of the chip (marks-v3.css); staff tones are fixed colours so that staff are recognisable on any skin
TONES: Final = ("dev", "staff", "gold", "green", "pink", "orange", "violet", "acc")

# id: (title, glyph, kind, tone, weight, what it means, how it is obtained)
_ROWS: Final = {
    # staff: by hand
    "developer":     ("Разработчик", "🌌", "staff", "dev", 1000, "Создаёт и ведёт Предвестника.", "Выдают разработчики."),
    "senior_helper": ("Старший хелпер", "⚔️", "staff", "staff", 900, "Следит за порядком во всех чатах бота.", "Выдают разработчики."),
    "helper":        ("Хелпер", "🛡", "staff", "staff", 800, "Помогает игрокам и следит за порядком.", "Выдают разработчики."),
    # granted by hand
    "founder":  ("Первопроходец", "🧭", "granted", "gold", 700, "С Предвестником с самых первых дней.", "Выдают разработчики тем, кто был с проектом с самого начала."),
    "partner":  ("Партнёр", "🤝", "granted", "pink", 650, "Ведёт сообщество или делает контент вместе с проектом.", "Выдают разработчики."),
    "patron":   ("Меценат", "💎", "granted", "orange", 640, "Поддержал проект сверх обычного.", "Выдают разработчики."),
    "champion": ("Чемпион", "🏆", "granted", "gold", 620, "Победил в турнире или событии Предвестника.", "Выдают разработчики после события."),
    "tester":   ("Тестер", "🧪", "granted", "green", 600, "Внёс большой вклад в тестирование Предвестника.", "Выдают разработчики за большой вклад в тестирование."),
    # earned
    "tier_master": ("Мастер тиров", "⭐", "earned", "violet", 360, "Три образа доведены до своего потолка.", "Прокачайте три образа до максимума."),
    "collector":   ("Коллекционер", "🗂", "earned", "violet", 340, "Собрано десять постоянных образов.", "Соберите десять постоянных образов."),
    "streak30":    ("Серия 30", "🔥", "earned", "orange", 320, "Тридцать дней подряд с проектом.", "Заходите тридцать дней подряд."),
    "veteran":     ("Ветеран", "🎖", "earned", "acc", 300, "С проектом больше года.", "Оставайтесь с проектом год."),
    # live: not stored, see LIVE_RULES
    "personal_life": ("Личная жизнь?", "🛋", "live", "pink", 290, "Пятьдесят тысяч сообщений и больше за последние два месяца.", "Пишите от 50 000 сообщений за 60 дней: пока темп держится, регалия с вами, упал — пропадает."),
    "chatter":     ("Душа чата", "💬", "live", "acc", 280, "Десять тысяч сообщений и больше за последние 30 дней.", "Пишите от 10 000 сообщений за 30 дней: регалия держится, пока темп не упал."),
    "halloween":   ("Ночь Тыкв", "🎃", "earned", "orange", 200, "Взял образ из сезона «Ночь Тыкв».", "Купите образ из сезона «Ночь Тыкв»."),
    "new_year":    ("Новогодняя Ночь", "🎄", "earned", "green", 190, "Взял образ из сезона «Новогодняя Ночь».", "Купите образ из сезона «Новогодняя Ночь»."),
}
MARKS: Final = {key: {"id": key, "title": r[0], "glyph": r[1], "kind": r[2], "tone": r[3], "weight": r[4], "desc": r[5], "how": r[6]} for key, r in _ROWS.items()}

# earned rule: id -> (fact, need). `seasons` is a set of season ids the player owns a skin from.
EARNED_RULES: Final = {
    "tier_master": ("maxed", 3), "collector": ("owned_permanent", 10), "streak30": ("streak", 30), "veteran": ("joined_days", 365),
    "halloween": ("season:halloween", 1), "new_year": ("season:new_year", 1),
}
# live rule: id -> (fact, need). The window is the last N days including today, in the bot's time zone (infrastructure/repositories/marks_v1.py).
LIVE_WINDOWS: Final = (30, 60)
LIVE_RULES: Final = {"chatter": ("messages_30d", 10_000), "personal_life": ("messages_60d", 50_000)}
# what the console may give and take back: staff and special marks only (earned and dynamic ones are the server's)
GRANTABLE: Final = tuple(k for k, m in MARKS.items() if m["kind"] in ("staff", "granted"))


def staff_hint(global_rank: int) -> str | None:
    """The staff mark that matches a bot rank. Only a hint for the console («this helper has no badge yet»): it never shows anything by itself."""
    return {3: "developer", 2: "senior_helper", 1: "helper"}.get(min(3, max(0, int(global_rank or 0))))


def _have(facts: dict, fact: str) -> int:
    if fact.startswith("season:"):
        return 1 if fact.split(":", 1)[1] in (facts.get("seasons") or ()) else 0
    return max(0, int(facts.get(fact) or 0))


def _states(rules: dict, facts: dict) -> list[dict]:
    out = []
    for mark_id, (fact, need) in rules.items():
        have = _have(facts, fact)
        out.append({"id": mark_id, "done": have >= need, "have": min(have, need), "need": need})
    return out


def earned_state(facts: dict) -> list[dict]:
    """Every earned mark with its progress: {id, done, have, need}. Progress never exceeds the need."""
    return _states(EARNED_RULES, facts)


def live_state(facts: dict) -> list[dict]:
    """The same for dynamic marks: `done` is true only right now."""
    return _states(LIVE_RULES, facts)


def public(mark_id: str) -> dict:
    """What a client may see of a mark (no weight, no internal fields)."""
    m = MARKS[mark_id]
    return {"id": m["id"], "title": m["title"], "glyph": m["glyph"], "kind": m["kind"], "tone": m["tone"], "desc": m["desc"]}


def ordered(ids) -> list[dict]:
    """Unique mark ids, heaviest first, as public dicts. Unknown ids (a mark retired from the catalog) are skipped."""
    seen = dict.fromkeys(i for i in ids if i in MARKS)
    return [public(i) for i in sorted(seen, key=lambda i: -MARKS[i]["weight"])]


def stored(ids) -> list[str]:
    """Stored ids a player may wear: dynamic marks are never read from storage (an old row must not keep one alive after the pace drops)."""
    return [i for i in ids if i in MARKS and MARKS[i]["kind"] != "live"]


def compose(*, held_ids, facts: dict) -> list[dict]:
    """What a player wears: every stored mark, every earned rule already met (the server stores those on sight, see services/marks_v1.py)
    and every dynamic rule met right now."""
    ids = stored(held_ids)
    ids.extend(s["id"] for s in earned_state(facts) if s["done"])
    ids.extend(s["id"] for s in live_state(facts) if s["done"])
    return ordered(ids)
