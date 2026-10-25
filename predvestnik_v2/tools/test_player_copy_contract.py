#!/usr/bin/env python3
"""Тексты для игрока (docs/PLAYER_COPY.md): Путеводитель собран по правилам, числа в нём совпадают с кодом, в видимых строках нет внутренних слов.

Run: PYTHONPATH=. python3 tools/test_player_copy_contract.py
"""
import json
import re
from pathlib import Path

from core import account_age, chests_v1, league_pass, league_v1, minesweeper_v2, pets_v2, quests_v1, registry, rhythm_v2, rhythm_weather, skins_v3
from core.rhythm_gifts import PERKS
from services import quests_v1 as quest_rewards

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI" / "static"
guide = json.loads((STATIC / "guide-v3.json").read_text(encoding="utf-8"))
app57 = (STATIC / "app.57.js").read_text(encoding="utf-8")
topics = {t["id"]: t for t in guide["topics"]}

# ── Слова, которых игрок видеть не должен (PLAYER_COPY, раздел 4) ──────────────────────────────────────────────────────
JARGON = [r"окн\w* (нажатия|шире|уже)", r"\bтакт(а|ов|ы|е)?\b", r"чанк", r"кулдаун", r"\bдроп", r"\bлут\b", r"\bбаф", r"дебаф", r"нерф", r"\bимба",
          r"апгрейд", r"прокачк", r"ачивк", r"\bкэш", r"\bAPI\b", r"эндпоинт", r"синхронизац", r"\bсервер", r"\bресурс", r"\bбуст",
          r"\bтемп(а|е|ом)?\b", r"\bлимит", r"\bЛиг[аиуе]\b", r"сезонный рейтинг", r"рун-дар"]
ALLOWED = ("Золотой такт", "Ступень (тир)")


def clean(text: str) -> str:
    for ok in ALLOWED:
        text = text.replace(ok, "")
    return text


PROBLEMS: list[str] = []   # текстовые замечания собираются все сразу: автору не нужно запускать тест по разу на каждое слово


def assert_plain(label: str, text: str) -> None:
    for pattern in JARGON:
        hit = re.search(pattern, clean(text), re.IGNORECASE)
        if hit:
            PROBLEMS.append(f"{label}: внутреннее слово «{hit.group(0)}» (таблица PLAYER_COPY.md, раздел 4): «{text[:90]}»")


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]


def assert_short(label: str, text: str, limit: int) -> None:
    if len(text) > limit:
        PROBLEMS.append(f"{label}: {len(text)} знаков, не больше {limit}: «{text[:70]}…»")
    for sentence in sentences(text):
        if len(sentence.split()) > 22:
            PROBLEMS.append(f"{label}: предложение длиннее 22 слов: «{sentence[:80]}…»")


def texts(topic: dict) -> list[str]:
    out = [topic["title"], topic["lead"]]
    for b in topic["blocks"]:
        out += [x for x in (b.get("h"), b.get("text")) if x]
        for i in b.get("items", []):
            out += [v for k, v in i.items() if isinstance(v, str) and k in ("h", "p", "w", "plus", "minus")]
        for side in ("a", "b"):
            if side in b:
                out += [b[side]["h"], *b[side]["items"]]
    if topic.get("where"):
        out += [topic["where"]["label"], topic["where"]["path"]]
    return out


# ── Структура ──────────────────────────────────────────────────────────────────────────────────────────────────────────
assert guide["version"] == 1 and len(guide["topics"]) >= 25 and len(guide["glossary"]) >= 30 and len(guide["faq"]) >= 20
listed = [tid for g in guide["groups"] for tid in g["topics"]]
assert sorted(listed) == sorted(topics) and len(listed) == len(set(listed)), "каждая тема лежит ровно в одной группе"
assert [t["id"] for t in guide["topics"]] == listed, "порядок тем = порядок групп: «Читать по порядку» идёт по группам"
go_keys = set(re.findall(r"(\w+): \(\) =>", app57[app57.index("const _GV_GO"):app57.index("const _gvRating")]))
for g in guide["groups"]:
    assert_short(f"группа {g['id']}", g["sub"], 120)
    assert len(g["title"]) <= 40
for t in guide["topics"]:
    tid = t["id"]
    assert re.fullmatch(r"[a-z]+(-[a-z]+)*", tid), f"{tid}: id для ссылки startapp — латиница и дефис"
    assert len(t["title"]) <= 40, f"{tid}: заголовок длиннее 40 знаков"
    assert_short(f"{tid}: lead", t["lead"], 120)
    kinds = [b["t"] for b in t["blocks"]]
    assert kinds[0] == "what", f"{tid}: тема начинается с блока «Что это»"
    assert {"steps", "gives", "list", "words", "gifts", "pair"} & set(kinds), f"{tid}: нужен хотя бы один блок «Шаги», «Что даёт» или «Слова»"
    assert len(kinds) <= 9, f"{tid}: тема слишком длинная — раздели её"
    assert t.get("where") and t["where"]["path"], f"{tid}: нужен блок «Где найти» с путём словами экрана"
    if t["where"].get("go"):
        assert t["where"]["go"] in go_keys and t["where"]["label"], f"{tid}: кнопка «Где найти» ведёт в никуда"
    for n in t.get("next", []):
        assert n in topics and n != tid, f"{tid}: ссылка «Читай дальше» на {n}"
    for b in t["blocks"]:
        where = f"{tid}/{b['t']}"
        if b["t"] in ("what", "tip", "warn"):
            assert_short(where, b["text"], 190)
        if b["t"] == "steps":
            assert 3 <= len(b["items"]) <= 5, f"{where}: шагов от 3 до 5"
            for i in b["items"]:
                assert_short(f"{where}: заголовок шага", i["h"], 60)
                assert_short(f"{where}: пояснение шага", i["p"], 200)
        if b["t"] in ("gives", "list"):
            assert 2 <= len(b["items"]) <= (6 if b["t"] == "gives" else 12), f"{where}: пунктов {len(b['items'])}"
            for i in b["items"]:
                assert_short(f"{where}: {i['h']}", i["p"], 200)
        if b["t"] == "words":
            assert 1 <= len(b["items"]) <= 6
            for i in b["items"]:
                assert_short(f"{where}: {i['w']}", i["p"], 200)
        if b["t"] == "pair":
            for side in ("a", "b"):
                assert 2 <= len(b[side]["items"]) <= 5
                for x in b[side]["items"]:
                    assert_short(f"{where}: {b[side]['h']}", x, 100)
    for line in texts(t):
        assert_plain(tid, line)
for term in guide["glossary"]:
    assert term["t"] in topics, term
    assert_short(f"словарь «{term['w']}»", term["p"], 120)
    assert_plain("словарь", term["w"] + " " + term["p"])
assert [x["w"].lower().replace("ё", "е") for x in guide["glossary"]] == sorted(x["w"].lower().replace("ё", "е") for x in guide["glossary"]), "словарь по алфавиту"
for item in guide["faq"]:
    assert item["t"] in topics and item["q"].endswith(("?",)) or item["q"].startswith("Приложение"), item
    assert_short(f"вопрос «{item['q']}»", item["a"], 190)
    assert_plain("вопросы", item["a"] + ("" if item["q"] == "Куда делась Лига?" else " " + item["q"]))
assert "Рейтинг" in {x["w"] for x in guide["glossary"]} and "Мора" in {x["w"] for x in guide["glossary"]}, "ключевые слова в словаре"

assert not PROBLEMS, "\n".join(PROBLEMS)

# ── Дары: Путеводитель показывает ровно то, что видит игрок в игре ──────────────────────────────────────────────────────
shown = next(b for b in topics["gifts"]["blocks"] if b["t"] == "gifts")["items"]
assert [(i["w"], i["k"], i["plus"], i["minus"]) for i in shown] == [(p.name, p.kind, p.bonus, p.cost) for p in PERKS if not p.filler] + [(p.name, p.kind, p.bonus, p.cost) for p in PERKS if p.filler], \
    "список даров в Путеводителе разошёлся с core/rhythm_gifts.py — пересобери guide-v3.json"
for p in PERKS:
    assert_plain(f"дар {p.id}", f"{p.name} {p.bonus} {p.cost}")
    assert len(p.bonus) <= 80 and len(p.cost) <= 80, f"дар {p.id}: строка длиннее 80 знаков не помещается в карточку"
for event in rhythm_weather.EVENTS.values():
    assert_plain("погода", event["effect"])

# ── Числа в текстах = числа в коде (PLAYER_COPY, раздел 6) ────────────────────────────────────────────────────────────
def body(tid: str) -> str:
    return " ".join(texts(topics[tid]))


def has(tid: str, *needles: object) -> None:
    text = body(tid)
    for n in needles:
        assert str(n) in text, f"тема «{tid}»: в тексте нет числа {n}, а в коде оно есть — обнови текст или данные"


has("xp", league_pass.XP_PER_LEVEL, league_pass.CASUAL_DAILY_CAP, league_pass.PET_DAILY_CAP, league_pass.RHYTHM_SCORE_PER_XP, league_pass.RHYTHM_MAX_XP,
    *league_pass.MINES_WIN_XP.values(), f"{league_v1.XP_BY_STARS[1]}, {league_v1.XP_BY_STARS[2]} или {league_v1.XP_BY_STARS[3]}")
pet_numbers = {str(v) for v in league_pass.PET_XP.values()}
assert {m for m in re.findall(r"(\d+) опыта", " ".join(i["p"] for b in topics["xp"]["blocks"] if b["t"] == "list" for i in b["items"]))} <= pet_numbers, "опыт за действия питомцев не из PET_XP"
has("pass", league_pass.LEVELS, league_pass.XP_PER_LEVEL, league_pass.CLAIM_GRACE.days, account_age.MIN_ACCOUNT_AGE.days, 30)
has("rating", int(league_v1.rhythm_level(1).star_pct[0]), int(league_v1.rhythm_level(1).star_pct[1]), league_v1.rhythm_level(1).hearts, "30–60", league_v1.XP_BY_STARS[1])
has("rhythm", rhythm_v2.BASE_HEALTH, rhythm_v2.CHUNK_SIZE)
has("gifts", rhythm_v2.RESUME_LEAD_MS // 1000)
has("keys", *[t for t in chests_v1.KEY_TIERS if t > 1], chests_v1.KEY_SOURCE_COUNTS["quest_daily_set_complete"], chests_v1.KEY_SOURCE_COUNTS["quest_weekly_set_complete"],
    chests_v1.KEY_SOURCE_COUNTS["pet_expedition_complete"])
has("quests", quests_v1.DAILY_COUNT, quests_v1.WEEKLY_COUNT, quests_v1.STANDARD_WEEKLY_REROLLS, quests_v1.VIP_WEEKLY_REROLLS, *quest_rewards.REWARD_MORA.values(),
    *skins_v3.ESSENCE_QUEST_REWARD.values(), chests_v1.KEY_SOURCE_COUNTS["quest_daily_set_complete"], chests_v1.KEY_SOURCE_COUNTS["quest_weekly_set_complete"])
has("trail", pets_v2.SLOTS, *pets_v2.RUN_HOURS, *pets_v2.WATCH_HOURS, pets_v2.PAIR_MIN_SPECIES)
has("pets", len(chests_v1.PET_SPECIES))
for d in minesweeper_v2.DIFFICULTIES.values():
    assert f"{d.size}×{d.size}, мин: {d.mines}" in body("mines"), f"Сапёр {d.key}: размер и число мин расходятся с кодом"
vip_line = " ".join(registry.VIP_PERKS_PITCH)
vip_text = body("vip")
for number in ("20", "100", "10%", "10 вопросов", "20 значков", "Пять замен"):
    assert number in vip_text and (number in vip_line or number == "10 вопросов" and "10 вопросов" in vip_line or number == "Пять замен" and "Пять замен" in vip_line), f"VIP: «{number}» расходится с registry.VIP_PERKS_PITCH"
assert "Telegram Stars" in body("zarniki")

# ── Приложение ──────────────────────────────────────────────────────────────────────────────────────────────────────────
index = (STATIC / "index.html").read_text(encoding="utf-8")
main = (ROOT / "FastAPI" / "main.py").read_text(encoding="utf-8")
assert '<div id="pg-help" class="page"></div>' in index and "guide-v3.css" in index, "страница Путеводителя рисуется скриптом"
assert "Как пользоваться" not in index and "Путеводитель<small>" in index, "в «Ещё» строка называется «Путеводитель»"
assert 57 in eval(re.search(r"for i in (\([\d, ]+\))\]", main).group(1)) and '"guide-v3.css"' in main and "guide_v3_router.router" in main
assert "help:()=>gvShow()" in (STATIC / "app.01.js").read_text(encoding="utf-8")
start = (STATIC / "app.02.js").read_text(encoding="utf-8")
assert "guide:()=>openGuide(" in start, "ссылка ?startapp=guide_<тема>"
assert "openGuide()" in (STATIC / "app.42.js").read_text(encoding="utf-8"), "«Что нового» открывает Путеводитель"
tiles = (STATIC / "app.47.js").read_text(encoding="utf-8")
for tile_topic in ("trail", "keys", "quests", "ach"):
    assert f"topic: '{tile_topic}'" in tiles and tile_topic in topics, f"подсказка ведёт в тему «{tile_topic}»"
assert "Подробнее в Путеводителе" in tiles
# Строки, которые видит игрок, в страницах и скриптах игр, подсказках и Путеводителе — без внутренних слов
def _skip_regex(src: str, i: int) -> int:
    in_class = False
    while i < len(src) and (src[i] != "/" or in_class):
        in_class = (src[i] == "[") or (in_class and src[i] != "]")
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _scan(src: str, i: int, out: list[str], nested: bool) -> int:
    depth, prev = 0, ""
    while i < len(src):
        c, nxt = src[i], src[i + 1] if i + 1 < len(src) else ""
        if c in "'\"":
            j, buf = i + 1, []
            while j < len(src) and src[j] != c and src[j] != "\n":
                buf.append(src[j + 1] if src[j] == "\\" else src[j])
                j += 2 if src[j] == "\\" else 1
            out.append("".join(buf))
            i, prev = j + 1, "a"
        elif c == "`":
            i, prev = _template(src, i + 1, out), "a"
        elif c == "/" and nxt == "/":
            i = src.find("\n", i) if "\n" in src[i:] else len(src)
        elif c == "/" and nxt == "*":
            i = src.index("*/", i) + 2
        elif c == "/" and (prev == "" or prev in "(,=:[!&|?{};"):
            i, prev = _skip_regex(src, i + 1), "a"
        else:
            if c == "{":
                depth += 1
            elif c == "}":
                if nested and depth == 0:
                    return i + 1
                depth -= 1
            if not c.isspace():
                prev = c
            i += 1
    return i


def _template(src: str, i: int, out: list[str]) -> int:
    buf: list[str] = []
    while i < len(src):
        c = src[i]
        if c == "\\":
            buf.append(src[i + 1])
            i += 2
        elif c == "`":
            out.append("".join(buf))
            return i + 1
        elif c == "$" and src[i + 1:i + 2] == "{":
            out.append("".join(buf))
            buf = []
            i = _scan(src, i + 2, out, True)
        else:
            buf.append(c)
            i += 1
    return i


def ui_strings(name: str) -> list[str]:
    source = (STATIC / name).read_text(encoding="utf-8")
    if name.endswith(".js"):
        out: list[str] = []
        _scan(source, 0, out, False)
        return [x for x in out if re.search(r"[А-Яа-яЁё]", x)]
    source = re.sub(r"<(script|style)\b.*?</\1>|<!--.*?-->", "", source, flags=re.S)
    attrs = re.findall(r'(?:aria-label|placeholder|title|alt)="([^"]*)"', source)
    return [x for x in re.findall(r">([^<>{}]+)<", source) + attrs if re.search(r"[А-Яа-яЁё]", x)]


for name in ("rhythm-v2.html", "minesweeper-v2.html", "rhythm-v2.js", "minesweeper-v2.js", "league-help.js", "league-ladder.js", "league-rhythm.js", "league-rhythm-fx.js",
             "league-result.js", "league-pass.js", "league-mines.js", "league-demo.js", "app.47.js", "app.57.js", "game-shell-v3.js", "game-shell-v3.html"):
    for line in ui_strings(name):
        assert_plain(name, line)
assert not PROBLEMS, "\n".join(PROBLEMS)

# league-help.js: числа в карточках «Как копить опыт» и «Как играть» = числа в коде
helper = (STATIC / "league-help.js").read_text(encoding="utf-8")
for needle in (f"каждые {league_pass.XP_PER_LEVEL} опыта", f"1 за {league_pass.RHYTHM_SCORE_PER_XP} очков", f"не больше {league_pass.RHYTHM_MAX_XP} за один забег",
               " · ".join(str(v) for v in league_pass.MINES_WIN_XP.values()), f"{league_pass.RHYTHM_SCORE_PER_XP * 10} очков даст 10 опыта",
               f"не меньше {league_v1.rhythm_level(1).star_pct[0]}%", f"не меньше {league_v1.rhythm_level(1).star_pct[1]}%", f"У тебя {league_v1.rhythm_level(1).hearts} сердца", "30–60 нажатий", "от 3×3 до 12×16"):
    assert needle in helper, f"league-help.js: «{needle}» расходится с кодом"
assert "cap : 300" in helper.replace("cap = me.casual ? me.casual.cap : 300", "cap : 300") and league_pass.CASUAL_DAILY_CAP == 300
print(f"OK: guide {len(topics)} topics, {len(guide['glossary'])} terms, {len(guide['faq'])} answers; numbers match code; no internal words in player text")
