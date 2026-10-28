#!/usr/bin/env python3
"""Every mechanic a player can reach has a topic in the player guide (FastAPI/static/guide-v3.json), or an explicit exception with a reason (S08).

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_guide_coverage.py

Sources of «what a player can reach», read from the code, not from memory:
- the bottom dock tabs and the «Ещё» rows of FastAPI/static/index.html (and rows added by scripts: «Чистка чатов»);
- every chat-bot command with a help section (bot/chat registry);
- every feature switch (infrastructure/repositories/system_flags.py).
A new tab, row, command or switch without a line below fails the test: write the topic (docs/PLAYER_COPY.md) or add an exception with a reason.
For commands outside the staff sections the topic must also name the command, so the player finds it by search.
The coverage table for people: docs/roadmap/findings/B2-guide-coverage.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql://coverage@127.0.0.1:5433/coverage")   # the bot config needs one; nothing connects

STATIC = ROOT / "FastAPI" / "static"
guide = json.loads((STATIC / "guide-v3.json").read_text(encoding="utf-8"))
topics = {t["id"]: t for t in guide["topics"]}

# ── Нижняя полоса: data-page → тема (у «Кошелька» нет data-page, он сверен отдельно) ───────────────────────────────────────
TABS = {"profile": "profile", "arena": "games", "exchange-v1": "market", "pets": "pets", "questlog": "quests", "looks": "looks", "chests": "keys",
        "inventory": "inventory", "top": "profile", "more": "map"}
# ── «Ещё»: data-nav-key → тема или причина, почему темы нет ───────────────────────────────────────────────────────────────
MORE = {"chats": "profile", "top": "profile", "inventory": "inventory", "chests": "keys", "looks": "looks", "promo": "promo", "wallet": "wallet",
        "zarniki": "zarniki", "vip": "vip", "settings": "settings", "purge": "chat-admin", "guide": "",
        "support": "", "news": "", "community-link": "", "updates-link": "", "refresh": "", "admin": ""}
MORE_EXCEPT = {"guide": "это и есть Путеводитель", "support": "окно жалобы объясняет себя само", "news": "«Что нового» — лента обновлений, а не механика",
               "community-link": "ссылка на канал Telegram", "updates-link": "ссылка на канал Telegram", "refresh": "служебная кнопка «Обновить данные»",
               "admin": "только персоналу; справочник администрации — S09"}
# ── Команды чат-бота: раздел «бот помощь» → тема; отдельные команды — своя тема ────────────────────────────────────────────
SECTION_TOPIC = {"basic": "bot", "stats": "profile", "profile": "profile", "family": "family", "social": "warps", "games": "games", "pets": "trail",
                 "stars": "dust", "moderation": "chat-admin", "purge": "chat-admin", "settings": "chat-admin"}
# в этих разделах команд много и они для администрации: тема описывает их группой, имя каждой искать не нужно (полный список — «бот помощь»)
GROUP_SECTIONS = {"moderation", "purge", "settings", "pets"}
COMMAND_TOPIC = {"перевод": "transfers", "стрик": "streak", "вип": "vip", "промокод": "promo", "достижения": "ach", "тег": "chat-admin", "теги": "chat-admin",
                 "отменить удаление": "settings", "восстановить аккаунт": "settings", "баланс": "wallet", "мафия": "mafia", "мафия онлайн": "mafia-online",
                 "слова": "words", "слово": "words", "ритм": "rhythm", "квесты": "quests", "неактивы": "bot", "18+": "warps"}
# ── Выключатели: ключ → тема или причина ──────────────────────────────────────────────────────────────────────────────────────
FLAGS = {"tab_economy": "transfers", "tab_purge": "chat-admin", "tab_cosmetics": "looks", "tab_quests": "quests", "game_rhythm_v2": "rhythm",
         "game_minesweeper_v2": "mines", "game_mafia_v1": "mafia", "game_casino_v1": "casino", "game_mafia_online": "mafia-online", "content_chests_v1": "keys",
         "star_dust_v1": "dust", "pets_v2": "trail", "pets_level_up_v1": "pet-growth", "pets_route_rewards_v1": "trail", "shop_v1": "keys", "season_pass_v1": "pass",
         "economy_player_exchange_v1": "market", "economy_player_exchange_shorts_v1": "market", "coin_market_v2": "market", "coin_market_v2_shorts": "market"}
FLAG_EXCEPT = {"tab_bp": "прежний Боевой пропуск, экрана нет (его место занял Пропуск сезона)", "tab_zoo": "прежний Зоопарк, экрана нет",
               "tab_market": "прежний рынок с гачей, экрана нет", "tab_auction": "прежний аукцион, экрана нет",
               "game_reconstruction_v1": "игра в разработке, игрокам не показана", "reconstruction_real_settlement_v1": "служебный выключатель той же игры",
               "gifts_v2": "подарки по тирам в разработке (закрыты флагом): тема — когда откроются, см. «Находки по пути»"}


def body(tid: str) -> str:
    t = topics[tid]
    parts = [t["title"], t["lead"], t["where"]["path"], *(t.get("kw") or [])]
    for b in t["blocks"]:
        parts += [b.get("h") or "", b.get("text") or ""]
        for i in b.get("items", []):
            parts += [v for v in (i.values() if isinstance(i, dict) else [i]) if isinstance(v, str)]
        for side in ("a", "b"):
            if side in b:
                parts += [b[side]["h"], *b[side]["items"]]
    return " ".join(parts).lower().replace("ё", "е")


def main() -> None:
    problems: list[str] = []
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    dock = set(re.findall(r'class="nb[^"]*"[^>]*data-page="([^"]+)"', index))
    for page in sorted(dock):
        if TABS.get(page) not in topics:
            problems.append(f"вкладка внизу «{page}»: нет темы (TABS)")
    assert "showCurrModal()\"" in index and "wallet" in topics, "вкладка «Кошелёк» ведёт в тему wallet"
    rows = set(re.findall(r'data-nav-key="([^"]+)"', index))
    scripts = "".join(p.read_text(encoding="utf-8") for p in sorted(STATIC.glob("app.*.js")))
    rows |= set(re.findall(r"dataset\.navKey\s*=\s*'([\w-]+)'", scripts))   # rows a script adds for some players («Чистка чатов»)
    for key in sorted(rows):
        if key not in MORE:
            problems.append(f"строка «Ещё» «{key}»: нет ни темы, ни исключения (MORE)")
        elif MORE[key] and MORE[key] not in topics:
            problems.append(f"строка «Ещё» «{key}»: тема {MORE[key]} не существует")
        elif not MORE[key] and key not in MORE_EXCEPT:
            problems.append(f"строка «Ещё» «{key}»: исключение без причины")

    import bot.chat  # noqa: F401 - registers every command
    from bot.chat.framework import registry
    seen: set[int] = set()
    commands = 0
    for cmd in registry._by_name.values():
        if id(cmd) in seen or not cmd.section:
            continue
        seen.add(id(cmd))
        commands += 1
        tid = COMMAND_TOPIC.get(cmd.name) or SECTION_TOPIC.get(cmd.section)
        if tid not in topics:
            problems.append(f"команда «бот {cmd.name}» (раздел {cmd.section}): нет темы")
            continue
        if cmd.section not in GROUP_SECTIONS and cmd.name.lower().replace("ё", "е") not in body(tid):
            problems.append(f"команда «бот {cmd.name}»: тема «{tid}» её не называет — игрок не найдёт её поиском")

    from infrastructure.repositories.system_flags import _DEFAULTS
    for key, _label, _on in _DEFAULTS:
        if key in FLAG_EXCEPT:
            continue
        if FLAGS.get(key) not in topics:
            problems.append(f"выключатель «{key}»: нет ни темы, ни исключения с причиной (FLAGS / FLAG_EXCEPT)")
    assert not problems, "\n".join(problems)
    print(f"OK: {len(dock)} tabs, {len(rows)} «Ещё» rows, {commands} bot commands, {len(_DEFAULTS)} switches — each has a topic or a reasoned exception")


if __name__ == "__main__":
    main()
