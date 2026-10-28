#!/usr/bin/env python3
"""The administration guide (FastAPI/static/bot-admin/guide-admin.json) matches the code (S09).

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_admin_guide_contract.py

- every admin section (FastAPI/routers/bot_admin/auth.py SECTIONS, plus «Мои чаты») and every web action (people.py ACTIONS) has a topic;
  a topic is shown from the lowest default role that can use it (min_rank), and its button opens that very section;
- every chat moderation right (core/chat_rank_policy.py ACTIONS) is named in «Команды в чате» with its default rank;
- the bot roles, the configurable bounds (services/admin_access.py) and the limits in the text are the numbers of the code;
- texts follow docs/PLAYER_COPY.md (reader: a new moderator): short paragraphs and steps, «what» first;
- the page loads the data and the script (FastAPI/routers/bot_admin/page.py, index.html).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql://guide@127.0.0.1:5433/guide")   # imported routers read config; nothing connects

from bot.chat.global_ranks import BOT_RANKS, CREATOR  # noqa: E402
from core.chat_rank_policy import ACTIONS as CHAT_ACTIONS, RANKS as CHAT_RANKS  # noqa: E402
from FastAPI.routers.bot_admin.auth import SECTIONS  # noqa: E402
from FastAPI.routers.bot_admin.people import ACTIONS, BULK_MAX, LINKED_MIN_RANK  # noqa: E402
from services.admin_access import CEILING, FLOOR  # noqa: E402

ADMIN = ROOT / "FastAPI" / "static" / "bot-admin"
guide = json.loads((ADMIN / "guide-admin.json").read_text(encoding="utf-8"))
topics = {t["id"]: t for t in guide["topics"]}
problems: list[str] = []


def texts(t: dict) -> list[str]:
    out = [t["title"], t["lead"], t["where"]["path"]]
    for b in t["blocks"]:
        out += [x for x in (b.get("h"), b.get("text")) if x]
        for i in b.get("items", []):
            out += [v for k, v in i.items() if k in ("h", "p", "w") and isinstance(v, str)]
    return out


def short(label: str, text: str, limit: int) -> None:
    if len(text) > limit:
        problems.append(f"{label}: {len(text)} знаков, не больше {limit}: «{text[:60]}…»")
    for s in re.split(r"(?<=[.!?…])\s+", text):
        if len(s.split()) > 22:
            problems.append(f"{label}: предложение длиннее 22 слов: «{s[:60]}…»")


# ── Структура и тексты ─────────────────────────────────────────────────────────────────────────────────────────────────
listed = [tid for g in guide["groups"] for tid in g["topics"]]
assert sorted(listed) == sorted(topics) and len(listed) == len(set(listed)), "каждая тема ровно в одной группе"
assert [t["id"] for t in guide["topics"]] == listed, "порядок тем = порядок групп"
for t in guide["topics"]:
    tid = t["id"]
    assert re.fullmatch(r"[a-z]+(-[a-z]+)*", tid) and len(t["title"]) <= 40, tid
    short(f"{tid}: lead", t["lead"], 120)
    kinds = [b["t"] for b in t["blocks"]]
    assert kinds[0] == "what" and {"steps", "gives", "list", "words"} & set(kinds) and len(kinds) <= 9, f"{tid}: «Что это» первым и хотя бы один блок шагов или списка"
    assert isinstance(t["min_rank"], int) and 1 <= t["min_rank"] <= CREATOR, f"{tid}: min_rank"
    for b in t["blocks"]:
        if b["t"] in ("what", "tip", "warn"):
            short(f"{tid}/{b['t']}", b["text"], 180)
        if b["t"] == "steps":
            assert 3 <= len(b["items"]) <= 5, f"{tid}: шагов от 3 до 5"
            for i in b["items"]:
                short(f"{tid}: шаг", i["h"], 60)
                short(f"{tid}: пояснение шага", i["p"], 200)
        if b["t"] in ("gives", "list"):
            assert 2 <= len(b["items"]) <= (6 if b["t"] == "gives" else 12), f"{tid}: пунктов {len(b['items'])}"
            for i in b["items"]:
                short(f"{tid}: {i['h']}", i["p"], 200)
    if t.get("section"):
        assert t["where"].get("go") == t["section"] and t["where"].get("label"), f"{tid}: кнопка «Открыть» ведёт в свой раздел"
for term in guide["glossary"]:
    assert term["t"] in topics, term
    short(f"словарь «{term['w']}»", term["p"], 120)
for item in guide["faq"]:
    assert item["t"] in topics and item["q"].endswith("?"), item
    short(f"вопрос «{item['q']}»", item["a"], 180)

# ── Разделы и действия админки ─────────────────────────────────────────────────────────────────────────────────────────
by_section = {}
for t in guide["topics"]:
    if t.get("section"):
        by_section.setdefault(t["section"], []).append(t)
for key, (title, rank) in {**SECTIONS, "mychats": ("Мои чаты", 2)}.items():
    if key not in by_section:
        problems.append(f"раздел «{title}» ({key}): нет темы")
        continue
    for t in by_section[key]:
        if t["min_rank"] < rank:
            problems.append(f"{t['id']}: показывается с роли {t['min_rank']}, а раздел «{title}» открыт с {rank}")
owner_topics = [t for t in guide["topics"] if t.get("owner")]
assert any(t.get("section") == "mychats" for t in owner_topics), "владельцу чата есть что читать"
covered = {a: t for t in guide["topics"] for a in t.get("actions", [])}
for key, (label, rank, _kind) in ACTIONS.items():
    t = covered.get(key)
    if not t:
        problems.append(f"действие «{label}» ({key}): нет темы")
for t in guide["topics"]:
    if t.get("actions"):
        lowest = min(ACTIONS[a][1] for a in t["actions"])
        if t["min_rank"] != lowest:
            problems.append(f"{t['id']}: min_rank {t['min_rank']}, а самое доступное действие темы — с роли {lowest}")
        body = " ".join(texts(t))
        for a in t["actions"]:
            r = ACTIONS[a][1]
            if r != t["min_rank"] and f"{r}" not in body:
                problems.append(f"{t['id']}: «{ACTIONS[a][0]}» доступно с роли {r} — назови это число в тексте")

# ── Роли и числа ───────────────────────────────────────────────────────────────────────────────────────────────────────
roles = next(b for b in topics["roles"]["blocks"] if b["t"] == "list")["items"]
assert [i["h"] for i in roles] == [f"{n} {BOT_RANKS[n][1]}" for n in range(1, CREATOR + 1)], "роли в боте — как в bot/chat/global_ranks.py"
roles_text = " ".join(texts(topics["roles"]))
assert f"от {FLOOR} до {CEILING}" in roles_text and f"от {FLOOR} до {CEILING}" in " ".join(texts(topics["access"])), "границы порогов — services/admin_access.py"
assert f"до {BULK_MAX} игроков" in " ".join(texts(topics["watch"])), "массовые действия — people.BULK_MAX"
assert f"({LINKED_MIN_RANK})" in " ".join(texts(topics["find"])), "связанные аккаунты — people.LINKED_MIN_RANK"
for n, (_icon, name) in ((n, CHAT_RANKS[n]) for n in (0, len(CHAT_RANKS) - 1)):
    assert f"({n})" in " ".join(g["p"] for g in guide["glossary"] if g["w"] == "Ранг в чате"), "ранги в чате 0–9"

# ── Команды модерации в чате: каждое право с порогом по умолчанию ──────────────────────────────────────────────────────
items = {i["h"]: i["p"] for b in topics["chat-commands"]["blocks"] if b["t"] == "list" for i in b["items"]}
tip = next(b["text"] for b in topics["chat-commands"]["blocks"] if b["t"] == "tip")
WHERE = {"warn": ("бот варн", "С ранга {r} «{n}»"), "unwarn": ("бот варн", "Снимать — с {r}"), "mute": ("бот мут", "С ранга {r} «{n}»"),
         "unmute": ("бот мут", "Снимать мут — тоже с {r}"), "kick": ("бот кик", "С ранга {r} «{n}»"), "ban": ("бот бан", "С ранга {r} «{n}»"),
         "unban": ("бот бан", "Снимать бан — тоже с {r}"), "lists": ("бот санкции", "с ранга {r}"), "close_chat": ("бот закрыть чат", "С ранга {r}"),
         "shield": ("бот защита", "с ранга {r}"), "immune": ("бот защита", "«Бот иммунитет» — с {r}"), "set_rank": ("бот ранг", "с ранга {r} «{n}»"),
         "purge": ("бот чистка", "Чистка — с ранга {r}"), "purge_write": ("бот чистка", "Писать во время чистки — с {r}"),
         "admin_chat": ("бот привязать админ чат", "с ранга {r} «{n}»"), "settings": ("бот привязать админ чат", "с ранга {r}"),
         "rights": ("бот права", "(ранг {r})"), "warn_limit": ("", "Лимит варнов меняют с ранга {r}"), "write_closed": ("", "в закрытый чат пишут с {r}"),
         "pinged": ("", "пинги в админ-сообщениях — с {r}")}
for action in CHAT_ACTIONS:
    if action.key not in WHERE:
        problems.append(f"право в чате «{action.label}» ({action.key}): не описано в «Команды в чате»")
        continue
    head, phrase = WHERE[action.key]
    text = tip if not head else next((p for h, p in items.items() if h.startswith(head)), "")
    want = phrase.format(r=action.default, n=CHAT_RANKS[action.default][1] if action.default < len(CHAT_RANKS) else "")
    if want not in text:
        problems.append(f"«Команды в чате»: «{action.label}» — ждём «{want}» (порог по умолчанию из core/chat_rank_policy.py)")

# ── Страница админки ──────────────────────────────────────────────────────────────────────────────────────────────────
page = (ROOT / "FastAPI" / "routers" / "bot_admin" / "page.py").read_text(encoding="utf-8")
index = (ADMIN / "index.html").read_text(encoding="utf-8")
assert '"guide-admin.json"' in page and '"admin-guide.js"' in page, "файлы справки отдаются страницей админки (_TYPES)"
assert index.index("admin-guide.js") < index.index("admin-boot.js"), "справка подключена до старта админки"
script = (ADMIN / "admin-guide.js").read_text(encoding="utf-8")
assert "min_rank" in script and "ME.owner" in script and "open(" in script, "справка фильтрует темы по роли и открывает разделы"
assert not problems, "\n".join(problems)
print(f"OK: admin guide {len(topics)} topics, {len(guide['glossary'])} terms, {len(guide['faq'])} answers; "
      f"{len(SECTIONS) + 1} sections, {len(ACTIONS)} actions, {len(CHAT_ACTIONS)} chat rights match the code")
