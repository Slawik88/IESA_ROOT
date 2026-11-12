"""«Табло» — живая сводка игрока в личке с ботом: Я · День · Задания · Пропуск · Питомцы (S30b).

Экран — список строк, их рисует один общий шаблон (core/widgets/html/hub.html). Строка:
    i значок (`@m`/`@p`/`@w` — значок образа для сообщений, прогресса, кошелька, как в его рамках в чате) · t заголовок · s пояснение · p [сделано, всего] — полоска · w [начало, конец] (мс) — полоска с отсчётом
    a [[надпись, действие], …] — кнопки, или одной строкой "действие" — главная кнопка «Забрать» («Поймать» у
    звездопада). Залитая кнопка — действие, спокойная — переход (`v:…`, ссылка) · g [[значок, число], …] — плашки ·
    m «0–4»×63 — активность за 9 недель · c "ok" (сделано: галочка у заголовка)
Состояние вместе с подписью образа обязано влезть в 1024 байта (предел Telegram), поэтому ключи однобуквенные,
а тексты короткие; если строк всё же слишком много, core.widgets.fit уберёт пояснения и хвост.
Действие — `v:<экран>` (перейти), ссылка `https://t.me/…` (раздел приложения) или глагол ниже; виджет дописывает
к глаголу текущий экран последним аргументом, ответ рисует этот экран заново с итогом в `o`.

Данные и награды — те же сервисы и те же проверки, что у кнопок «План дня» (bot/chat/notify.py), команд «бот
звездопад», «бот питомцы» и мини-приложения: повторное нажатие не выдаёт награду дважды. Готовые проверки доступа
из чата (питомцы, звёздная пыль) берутся как есть, чтобы выключатель в админке закрывал и виджет.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from loguru import logger

from core import widgets as rules
from services import dm_plan
from services.widgets import Refused, Reply

VIEWS = rules.REGISTRY["hub"].views
QUEST_KIND = {"daily": "дня", "weekly": "недели", "combined": "дня и недели вместе"}
QUEST_CODE = {"d": "daily", "w": "weekly", "c": "combined"}
PATH_CODE = {"c": "careful", "s": "steady", "b": "bold"}

SAMPLE = {
    "v": "day", "b": {"q": 2, "pass": 1, "pets": 1},
    "l": [
        {"i": "@p", "t": "Серия: 128 дней", "s": "Напиши в группе с ботом до полуночи", "w": [1762819200000, 1762905600000]},
        {"i": "📜", "t": "Задания дня: 3 из 4", "s": "22 Моры, 1 ключ, 2 Эссенции", "p": [3, 4], "a": "q:d"},
        {"i": "🎁", "t": "Награда недели", "s": "110 Моры, 2 ключа, 6 Эссенции", "a": "q:w"},
        {"i": "🎫", "t": "Пропуск: 39 из 40", "s": "Награды ждут", "p": [260, 300], "a": "p"},
        {"i": "🐾", "t": "Питомцы вернулись: 3", "s": "Добыча ждёт", "a": [["Открыть", "v:pets"]]},
        {"i": "🌠", "t": "Звездопад", "s": "Пыль раз в день", "a": "d"},
        {"i": "🎁", "t": "Подарок Фортуны", "s": "1000 фишек в день", "a": "g"},
    ],
}


def _ms(value) -> int:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _utc_day(now: datetime) -> tuple[int, int]:
    start = datetime.combine(now.date(), datetime.min.time(), timezone.utc)
    return _ms(start), _ms(start + timedelta(days=1))


def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def _reward_text(item: dict) -> str:
    parts = [f"{int(item.get('amount_mora', 0))} Моры"]
    if int(item.get("amount_keys", 0)):
        keys = int(item["amount_keys"])
        parts.append(f"{keys} {_plural(keys, 'ключ', 'ключа', 'ключей')}")
    if int(item.get("amount_essence", 0)):
        parts.append(f"{int(item['amount_essence'])} Эссенции")
    return ", ".join(parts)


def _private(user_id: int) -> SimpleNamespace:
    """Личка игрока в форме, которую ждут проверки доступа из чата (тип и номер чата)."""
    return SimpleNamespace(type="private", id=int(user_id))


async def _app(section: str) -> str:
    from core.miniapp_links import miniapp_url
    url = miniapp_url(section)
    return url if url.startswith("https://t.me/") and len(url) <= 256 else ""


def _link(label: str, url: str) -> list[list[str]]:
    return [[label, url]] if url else []


# ── День ───────────────────────────────────────────────────────────────────

async def _streak_row(db, user_id: int) -> dict:
    from bot.chat.streak import streak_of
    from bot.chat.tracking import local_now, tz_delta
    today = local_now().date()
    current, best, done = await streak_of(db, user_id, today)
    row: dict = {"i": "@p", "t": f"Серия: {current} {_plural(current, 'день', 'дня', 'дней')}"}
    if done:
        row.update(s="Сегодня засчитано", c="ok")
    elif current:
        midnight = datetime.combine(today + timedelta(days=1), datetime.min.time()) - tz_delta()
        row.update(s="Напиши в группе с ботом до полуночи",
                   w=[_ms(midnight - timedelta(days=1)), _ms(midnight)])
    else:
        row["s"] = "Напиши в группе с ботом — начнётся новая"
    return row


async def _quest_rows(db, user_id: int, badges: dict) -> list[dict]:
    view = await dm_plan.quests_state(db, user_id)
    if view is None or not view["daily"]["quests"]:
        return []
    daily = view["daily"]["quests"]
    done = sum(1 for q in daily if q["completed"])
    items = view["rewards"]["items"]
    ready = [kind for kind, item in items.items() if item.get("claimable")]
    badges["q"] = len(ready)
    row: dict = {"i": "📜", "t": f"Задания дня: {done} из {len(daily)}", "p": [done, len(daily)]}
    day = items.get("daily", {})
    if "daily" in ready:
        row.update(s=_reward_text(day), a="q:d")
    elif day.get("claimed"):
        row.update(s="Награда получена", c="ok", a=[["Список", "v:q"]])
    else:
        row.update(s="За все: " + _reward_text(day) if day else "Выполни все задания дня", a=[["Список", "v:q"]])
    rows = [row]
    for kind in ("weekly", "combined"):
        if kind in ready:
            rows.append({"i": "🎁", "t": f"Награда {QUEST_KIND[kind]}", "s": _reward_text(items[kind]), "a": f"q:{kind[0]}"})
    return rows


async def _pass_season(db, user_id: int) -> tuple[dict, dict] | None:
    from services import league_pass
    view = await league_pass.status(db, user_id=user_id)
    if not view.get("active") or not view.get("seasons"):
        return None
    season = next((s for s in view["seasons"] if s.get("current")), view["seasons"][0])
    return view, season


def _pass_ready(view: dict) -> bool:
    if not view.get("account", {}).get("eligible", True):
        return False
    return any(r[t]["state"] == "ready" for s in view["seasons"] for r in s.get("track", []) for t in ("free", "vip")) \
        or any(s.get("repeat", {}).get("ready") for s in view["seasons"])


def _level_row(season: dict) -> dict:
    per, level, levels = int(season["xp_per_level"]), int(season["level"]), int(season["levels"])
    into = per - int(season["xp_to_next"]) if level < levels else per
    return {"t": f"Уровень {level} из {levels}", "p": [max(0, into), per],
            "s": f"До следующего уровня — {int(season['xp_to_next'])} опыта" if level < levels else "Все уровни пройдены"}


async def _pass_row(db, user_id: int, badges: dict) -> list[dict]:
    found = await _pass_season(db, user_id)
    if found is None:
        return []
    view, season = found
    ready = _pass_ready(view)
    badges["pass"] = int(ready)
    row = {**_level_row(season), "i": "🎫"}
    row["t"] = f"Пропуск: {season['level']} из {season['levels']}"
    if ready:
        row.update(s="Награды ждут", a="p")
    else:
        row["a"] = [["Подробнее", "v:pass"]]
    return [row]


async def _pets_row(db, user_id: int, badges: dict) -> list[dict]:
    counts = await dm_plan.pets_state(db, user_id)
    if counts is None or not any(counts):
        return []
    back, away = counts
    badges["pets"] = int(back > 0)
    if back:
        return [{"i": "🐾", "t": f"Питомцы вернулись: {back}", "s": "Добыча ждёт", "a": [["Открыть", "v:pets"]]}]
    nearest = await dm_plan.next_pet_return(db, user_id)
    row: dict = {"i": "🐾", "t": f"Питомцы в пути: {away}", "a": [["Открыть", "v:pets"]]}
    if nearest:
        start, end = nearest
        row.update(s="Ближайший вернётся", w=[_ms(start), _ms(end)])
    return [row]


async def _dust_row(db, user_id: int, now: datetime) -> list[dict]:
    from bot.chat import star_dust as dust_chat
    from services import star_dust
    if not await dust_chat.available(db, user_id, _private(user_id), "звездопад"):
        return []
    view = await star_dust.overview(db, user_id)
    if view["chat_ready"]:
        return [{"i": "🌠", "t": "Звездопад", "s": "Пыль раз в день", "a": "d"}]
    return [{"i": "🌠", "t": f"Звёздная пыль: {int(view['balance'])}", "s": "Новый звездопад",
             "w": [_utc_day(now)[0], _ms(view["next_chat_at"])]}]


async def _gift_row(db, user_id: int) -> list[dict]:
    if not await _gift_open(db):
        return []
    from core.casino_v1 import DAILY_GIFT
    from infrastructure.repositories import casino_v1 as casino_repo
    wallet = await casino_repo.wallet(db, user_id)
    if wallet and wallet.get("gift_day") == wallet.get("today"):
        return []
    return [{"i": "🎁", "t": "Подарок Фортуны", "s": f"{DAILY_GIFT} фишек в день", "a": "g"}]


async def _gift_open(db) -> bool:
    from infrastructure.repositories import system_flags
    from services import feature_switches
    return (await system_flags.is_enabled(db, "game_casino_v1")
            and await feature_switches.disabled(db, ["all", "section:games", "cmd:подарок фортуны"], None) is None)


async def _day(db, user_id: int) -> dict:
    badges: dict = {}
    rows = [await _streak_row(db, user_id)]
    for part in (_quest_rows(db, user_id, badges), _pass_row(db, user_id, badges), _pets_row(db, user_id, badges),
                 _dust_row(db, user_id, datetime.now(timezone.utc)), _gift_row(db, user_id)):
        rows += await _safely(part)
    return {"l": rows, "b": badges}


async def _safely(part) -> list[dict]:
    """Один раздел недоступен (выключен, нет таблицы) — остальная сводка всё равно рисуется."""
    try:
        return await part
    except Refused:
        raise
    except Exception as exc:
        logger.warning(f"hub: section unavailable: {type(exc).__name__}: {str(exc)[:160]}")
        return []


# ── Я ─────────────────────────────────────────────────────────────────────

def _heat(counts: dict[date, int], today: date) -> str:
    """Активность за 9 недель по столбцам-неделям (понедельник сверху), как «бот стрик»: уровни 0–4."""
    from bot.chat.streak import WEEKS, level
    first = today - timedelta(days=today.weekday()) - timedelta(weeks=WEEKS - 1)
    peak = max(counts.values(), default=0)
    return "".join("0" if (d := first + timedelta(weeks=w, days=wd)) > today else str(level(counts.get(d, 0), peak))
                   for w in range(WEEKS) for wd in range(7))


async def _me(db, user_id: int) -> dict:
    from bot.chat.profile import SHOWN_CURRENCIES, fmt_num, wallet_values
    from bot.chat.settings import CURRENCY_VIEW
    from bot.chat.streak import WEEKS, activity, streak_of
    from bot.chat.tracking import local_now
    from infrastructure.repositories import chests_v1 as chests_repo
    from services.skins_v3 import own_look
    values = await wallet_values(db, user_id)
    chips = [[CURRENCY_VIEW[c].icon, fmt_num(values[c], CURRENCY_VIEW[c].display_decimals)] for c in SHOWN_CURRENCIES]
    chips.append(["🗝", str(await chests_repo.get_balance(db, user_id))])
    rows = [{"i": "@w", "t": "Кошелёк", "g": chips}]
    today = local_now().date()
    current, best, _ = await streak_of(db, user_id, today)
    counts = await activity(db, user_id, today - timedelta(weeks=WEEKS), today)
    rows.append({"i": "@p", "t": f"Серия: {current} {_plural(current, 'день', 'дня', 'дней')}"
                 + (f" · лучшая {best}" if best > current else ""), "s": "Сообщения за 9 недель", "m": _heat(counts, today)})
    look = await own_look(db, user_id)
    looks = _link("Образы", await _app("looks"))
    if look:
        rows.append({"i": "🎨", "t": f"Образ «{look['name']}» · уровень {look['tier']}",
                     "s": "Уровни — от D до SSS: чем выше, тем ярче табло и ответы бота", "a": looks})
    else:
        rows.append({"i": "🎨", "t": "Образ не выбран", "s": "Образ красит это табло, карточку «бот я» и ответы бота",
                     "a": looks})
    return {"l": rows}


# ── Задания ───────────────────────────────────────────────────────────────

async def _quests(db, user_id: int, weekly: bool) -> dict:
    view = await dm_plan.quests_state(db, user_id)
    if view is None:
        return {"l": [{"i": "📜", "t": "Задания сейчас недоступны", "s": "Загляни чуть позже"}]}
    now = datetime.now(timezone.utc)
    period = "weekly" if weekly else "daily"
    if weekly:
        monday = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time(), timezone.utc)
        window = [_ms(monday), _ms(monday + timedelta(days=7))]
    else:
        window = list(_utc_day(now))
    nav = [["‹ Задания дня", "v:q"]] if weekly else [["Неделя ›", "v:qw"]]
    rows = [{"i": "⏳", "t": "Задания недели" if weekly else "Задания дня", "s": "Новые", "w": window, "a": nav}]
    for quest in view[period]["quests"]:
        if quest["completed"]:
            rows.append({"i": "✅", "t": str(quest["title"])[:60]})
        else:
            done, target = int(quest["progress"]), int(quest["target"])
            rows.append({"i": "🔸", "t": f"{str(quest['title'])[:60]} · {done}/{target}", "p": [done, target]})
    items = view["rewards"]["items"]
    for kind in ((period, "combined") if weekly else (period,)):
        item = items.get(kind)
        if not item or (kind == "combined" and not item.get("claimable")):   # «всё вместе» — только когда готово
            continue
        row: dict = {"i": "🎁", "t": f"Награда {QUEST_KIND[kind]}: {_reward_text(item)}"}
        if item.get("claimable"):
            row["a"] = f"q:{kind[0]}"
        elif item.get("claimed"):
            row.update(c="ok", s="Получена")
        else:
            row["s"] = "Выполни все задания"
        rows.append(row)
    rerolls = view["rerolls"]
    rows.append({"i": "🔁", "t": f"Замены на неделе: {int(rerolls['remaining'])} из {int(rerolls['limit'])}",
                 "s": "Заменить задание — в приложении"})
    return {"l": rows, "b": {"q": sum(1 for item in items.values() if item.get("claimable"))}}


# ── Пропуск ───────────────────────────────────────────────────────────────

async def _pass(db, user_id: int) -> dict:
    from core.seasons import season_bounds
    found = await _pass_season(db, user_id)
    if found is None:
        return {"l": [{"i": "🎫", "t": "Пропуск ещё не открыт", "s": "Он откроется с новым сезоном"}], "b": {"pass": 0}}
    view, season = found
    ready = _pass_ready(view)
    rows = [{**_level_row(season), "i": "🎫"}]
    count = sum(1 for s in view["seasons"] for r in s.get("track", []) for t in ("free", "vip") if r[t]["state"] == "ready")
    account = view.get("account", {})
    if not account.get("eligible", True):
        rows.append({"i": "🔒", "t": f"Награды — когда аккаунту будет {int(account.get('min_days', 14))} дней",
                     "s": "Опыт копится уже сейчас и не пропадёт"})
    elif ready:
        rows.append({"i": "🎁", "t": f"Готово наград: {count}" if count else "Готова награда за опыт сверх 40 уровня",
                     "a": "p"})
    else:
        upcoming = next((r for r in season.get("track", []) if int(r["level"]) > int(season["level"])), None)
        if upcoming:
            rows.append({"i": "🎁", "t": f"Уровень {upcoming['level']}: {upcoming['free']['text']}"[:80],
                         "s": "Следующая награда"})
        repeat = season.get("repeat") or {}
        if repeat.get("next_claim_at") and not repeat.get("ready"):
            rows.append({"i": "🗝", "t": "Ключ за опыт сверх 40 уровня", "s": "Следующий ключ",
                         "w": [_ms(datetime.now(timezone.utc)), _ms(repeat["next_claim_at"])]})
    casual, pets = view.get("casual") or {}, view.get("pets") or {}
    if casual.get("cap"):
        rows.append({"i": "🎮", "t": f"Опыт за игры сегодня: {int(casual['today'])} из {int(casual['cap'])}",
                     "p": [int(casual["today"]), int(casual["cap"])]})
    if pets.get("cap"):
        rows.append({"i": "🐾", "t": f"Опыт за питомцев сегодня: {int(pets['today'])} из {int(pets['cap'])}",
                     "p": [int(pets["today"]), int(pets["cap"])]})
    race = view.get("race") or {}
    if race.get("running"):
        rows.append({"i": "🏁", "t": f"Гонка: первым {race['places']}, кто дойдёт до 40 уровня, — по {race['prize_stars']} ⭐",
                     "s": f"Осталось мест: {race['left']}" if race.get("left") else "Все места заняты"})
    start, end = season_bounds(int(season["season"]))
    rows.append({"i": "⏳", "t": f"Сезон {season['season']}", "s": "До конца сезона", "w": [_ms(start), _ms(end)]})
    return {"l": rows, "b": {"pass": int(ready)}}


# ── Питомцы ───────────────────────────────────────────────────────────────

async def _pets_open(db, user_id: int) -> bool:
    from bot.chat import pets as pets_chat
    return await pets_chat.available(db, user_id, _private(user_id), {"screen": "claim"})


def _hint(hint: dict) -> str:
    if "chance" in hint:
        return f"{hint['chance']:g}%"
    if "range" in hint:
        return "–".join(f"{v:g}" for v in hint["range"]) + "%"
    return str(hint.get("sign", ""))


def _claim_buttons(run: dict) -> list[list[str]]:
    from bot.chat.pet_menu import PATHS
    if run["kind"] != "expedition":
        return [["Забрать", f"r:{run['id']}"]]
    decision = run.get("decision") or {}
    hints, best = decision.get("paths", {}), decision.get("best")
    out = []
    for code, path in PATH_CODE.items():
        label = PATHS[path] + (" ★" if path == best else "")
        hint = _hint(hints.get(path, {}))
        out.append([f"{label} · {hint}" if hint else label, f"r:{run['id']}:{code}"])
    return out


def _fits(verb: str) -> bool:
    return len(f"hub:{verb}:pets".encode()) <= rules.MAX_QUERY_BYTES


async def _pets(db, user_id: int) -> dict:
    from bot.chat.pet_menu import KINDS, name
    from core import pets_v2 as pet_rules
    from services import pets_v2
    if not await _pets_open(db, user_id):
        return {"l": [{"i": "🐾", "t": "Питомцы сейчас недоступны", "s": "Загляни чуть позже"}], "b": {"pets": 0}}
    view = await pets_v2.overview(db, user_id)
    pets_app = _link("Открыть", await _app("pets"))
    if not view["pets"]:
        return {"l": [{"i": "🐾", "t": "Пока нет питомцев", "s": "Первого можно найти в сундуке", "a": pets_app}]}
    by_id = {p["id"]: p for p in view["pets"]}
    rows, ready = [], 0
    for run in sorted(view["activities"], key=lambda r: (not r["ready"], r["ends_at"])):
        pet = by_id.get(run["pet_id"])
        if pet is None:
            continue
        head = {"i": pet.get("icon", "🐾"), "t": f"{name(pet)} · {KINDS.get(run['kind'], 'В пути')} {run['hours']} ч"[:60]}
        if run["ready"]:
            ready += 1
            buttons = [b for b in _claim_buttons(run) if _fits(b[1])]
            note = "Развилка: выбери путь, ★ — совет" if run["kind"] == "expedition" else "Вернулся с добычей"
            rows.append({**head, "s": note, "a": buttons or pets_app})
        else:
            end = _ms(run["ends_at"])
            rows.append({**head, "s": "Вернётся", "w": [end - int(run["hours"]) * 3_600_000, end]})
    busy = sum(1 for p in view["pets"] if p.get("run_id") or p.get("outing"))
    free = max(0, min(pet_rules.SLOTS, len(view["pets"])) - busy)
    rows.append({"i": "🧭", "t": f"Можно отправить ещё: {free}" if free else "Все питомцы заняты",
                 "s": "Поход, экспедиция и дозор — в приложении или «бот отправить питомца»", "a": pets_app})
    return {"l": rows, "b": {"pets": int(ready > 0)}}


def _pet_result(result: dict) -> str:
    names = {"mora": "Мора", "diamond": "Алмазы", "essence": "Эссенция", "treat": "Лакомства", "talisman": "Талисманы"}
    parts = [f"{names.get(k, k)} +{v}" for k, v in (result.get("finds") or {}).items() if v]
    if result.get("key"):
        parts.append(f"ключи +{result['key']}")
    dust = (result.get("star_dust") or {}).get("amount", 0)
    if dust:
        parts.append(f"звёздная пыль +{dust}")
    if result.get("level_after", 0) > result.get("level_before", 0):
        parts.append(f"новый уровень {result['level_after']}")
    return "🎒 Питомец вернулся" + (": " + ", ".join(parts) if parts else "") + "."


# ── вход ─────────────────────────────────────────────────────────────────

BUILDERS = {
    "day": _day, "me": _me, "pass": _pass, "pets": _pets,
    "q": lambda db, uid: _quests(db, uid, weekly=False), "qw": lambda db, uid: _quests(db, uid, weekly=True),
}


async def state(db, user_id: int, view: str | None) -> dict:
    shown = rules.view_of(rules.REGISTRY["hub"], view) or VIEWS[0]
    return {"v": shown, **await BUILDERS[shown](db, user_id)}


async def act(db, user_id: int, verb: str, args: list[str], *, action_id: str) -> Reply:
    """`action_id` запроса здесь не нужен: награды заданий и Пропуска идут по квитанции периода, а у питомцев
    квитанция — сам выбор (_claim_pet), чтобы повтор того же нажатия из нового запроса не дал второй итог."""
    if verb == "v" and len(args) == 1 and args[0] in VIEWS:
        return Reply(await state(db, user_id, args[0]), persist=True)
    if not args or args[-1] not in VIEWS:
        raise Refused("Это табло устарело. Напиши «табло», чтобы получить новое.")
    view, extra = args[-1], args[:-1]
    outcome = await _do(db, user_id, verb, extra)
    return Reply({**await state(db, user_id, view), "o": outcome}, persist=True)


async def _do(db, user_id: int, verb: str, extra: list[str]) -> str:
    """Одно действие игрока теми же сервисами, что у кнопок в чате. Понятные отказы сервисов — текстом в виджет."""
    from services import casino_v1, league_pass, pets_v2, quests_v1
    from core.pets_v2 import PetV2PolicyError
    from core.star_dust import DustError
    try:
        if verb == "q" and len(extra) == 1 and extra[0] in QUEST_CODE:
            return await dm_plan.claim_quest(db, user_id, QUEST_CODE[extra[0]])
        if verb == "p" and not extra:
            return await dm_plan.claim_pass(db, user_id)
        if verb == "d" and not extra:
            return await _catch_dust(db, user_id)
        if verb == "g" and not extra:
            if not await _gift_open(db):
                raise Refused("Зал Фортуны сейчас закрыт.")
            from infrastructure.repositories import casino_v1 as casino_repo
            return await dm_plan.claim_casino_gift(db, user_id, await casino_repo.today(db))
        if verb == "r" and len(extra) in (1, 2) and (len(extra) == 1 or extra[1] in PATH_CODE):
            return await _claim_pet(db, user_id, extra[0], PATH_CODE.get(extra[1]) if len(extra) == 2 else None)
    except (quests_v1.QuestError, league_pass.PassError, casino_v1.CasinoError, DustError,
            pets_v2.PetV2Conflict, PetV2PolicyError) as exc:
        raise Refused(str(exc)[:200]) from exc
    raise Refused("Это табло устарело. Напиши «табло», чтобы получить новое.")


async def _catch_dust(db, user_id: int) -> str:
    from bot.chat import star_dust as dust_chat
    from services import star_dust
    if not await dust_chat.available(db, user_id, _private(user_id), "звездопад"):
        raise Refused("Звёздная пыль сейчас недоступна.")
    result = await star_dust.search(db, user_id=user_id)
    if result["already_claimed"]:
        return f"Сегодня ты уже поймал {result['amount']} пыли. Новый звездопад — завтра."
    luck = result["luck"]
    stars = "★" * int(luck["stars"]) + "☆" * (5 - int(luck["stars"]))
    return f"🌠 {stars} {luck['title']}: +{result['amount']} звёздной пыли." if result["amount"] else f"🌠 {luck['text']}"


async def _claim_pet(db, user_id: int, run_id: str, path: str | None) -> str:
    from services import pets_v2
    if not await _pets_open(db, user_id):
        raise Refused("Питомцы сейчас недоступны.")
    # Один и тот же выбор — одна квитанция: повтор после обрыва связи вернёт тот же итог, а не второй.
    result = await pets_v2.claim_run(db, user_id=user_id, run_id=run_id, path=path,
                                     action_id=f"widget:pet:{run_id}:{path or '-'}")
    return _pet_result(result)
