"""Объявление о новом уровне достижения: мини-описание, шкала лестницы, ступень, «до следующего» (без базы).

Запуск: python tools/test_achievements_announcement.py
"""
from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.chat import achievements as ach      # noqa: E402
from bot.chat.achievements_data import ACHIEVEMENTS, BLURBS   # noqa: E402


def main() -> None:
    assert set(BLURBS) == {a.id for a in ACHIEVEMENTS}, "у каждого достижения должно быть мини-описание, и только у них"
    for a in ACHIEVEMENTS:
        assert 20 <= len(a.blurb) <= 125 and a.blurb.startswith(("Считают", "Считается", "Берётся")) and a.blurb.endswith("."), (a.id, a.blurb)   # что именно считается, а не лирика
        assert not re.search(r"\b(ты|тебя|тебе|твой|твою|твоя)\b", a.blurb.lower()), f"{a.id}: объявление читает весь чат"

    # Шкала: от одной клетки до полной, пустая клетка не бывает «нулём» и полная — только на вершине.
    assert ach.ladder_bar(1, 80) == "▰▱▱▱▱▱▱▱▱▱"
    assert ach.ladder_bar(40, 80) == "▰▰▰▰▰▱▱▱▱▱"
    assert ach.ladder_bar(79, 80) == "▰▰▰▰▰▰▰▰▰▱"
    assert ach.ladder_bar(80, 80) == "▰" * 10
    assert [ach.stage(l, 40) for l in (2, 20, 30, 39, 40)] == [
        "первые шаги", "набирает ход", "уверенный ход", "почти легенда", "легенда"]

    runner = ach.BY_ID["best_day"]
    text = ach.announcement("@sweetpoison234", [ach.Up(runner, 2, 0, 62)])
    assert text.startswith("🏆 @sweetpoison234 — новый уровень!\n\n🏃 <b>Марафонец</b> · ур. 2 из 33"), text
    assert f"<b>За что:</b> {runner.blurb}" in text and "До ур. 3: 70 сообщений (сейчас 62)" in text and "эссенции" not in text, text

    top = ach.BY_ID["mafia_wins"]
    many = ach.announcement("@x", [ach.Up(ach.BY_ID["messages"], 30, 30, 5000), ach.Up(top, top.max_level, 0)])
    assert "сразу 2 новых уровня" in many and "+30 🔮 эссенции" in many and "Вершина лестницы" in many and "легенда" in many, many
    assert "До ур." not in many.split("Хозяин ночи")[1], "на вершине «до следующего» не пишем"

    unknown = ach.announcement("@x", [ach.Up(runner, 5, 0)])      # значение неизвестно (старые вызовы) — без «сейчас»
    assert "сейчас" not in unknown and "До ур. 6:" in unknown
    assert len(ach.announcement("@x", [ach.Up(a, 1, 0, 0) for a in ACHIEVEMENTS])) < 4096, "влезает в одно сообщение Telegram"
    print("OK: объявление о достижении — описание, шкала, ступень, до следующего, вершина, длина")


main()
