#!/usr/bin/env python3
"""Скины в чате без базы: стиль текста и картинка для каждого скина на каждом тире (docs/SKINS_CHAT_DESIGN_HANDOFF.md)."""
from __future__ import annotations

import os
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOT_TOKEN", "123456:offline-style-test")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1/predvestnik_preprod")

from PIL import Image  # noqa: E402

from bot.chat import activity_graph, skin_card, skin_text  # noqa: E402
from bot.chat.skin_card_draw import H, W  # noqa: E402
from core.skins_v3 import TIERS  # noqa: E402
from core.skins_v3_catalog import SKINS  # noqa: E402
from core.skins_v3_chat import ORNAMENT_MAX, chat_look, ornament_line  # noqa: E402
from core.skins_v3_chat_phrases import PHRASES  # noqa: E402

COMPOSE_LIMIT_SEC = 0.6     # карточка с холодным декором; бюджет в боте 0.9 с


def text_rules() -> None:
    assert set(PHRASES) == set(SKINS), set(SKINS) ^ set(PHRASES)
    for sid in SKINS:
        assert len(PHRASES[sid]) <= 60, (sid, len(PHRASES[sid]))
        assert len(ornament_line(sid)) <= ORNAMENT_MAX, sid
        for tier in TIERS:
            look = chat_look(sid, tier)
            assert look and look.glyph and look.title and all(look.icons), (sid, tier)
            at = TIERS.index(tier)
            assert (look.sep != "·") == (at >= TIERS.index("B")), (sid, tier, look.sep)
            assert (look.divider is not None) == (at >= TIERS.index("B")), (sid, tier)
            assert (look.frame is not None) == (at >= TIERS.index("S")), (sid, tier)
            assert (look.phrase is not None) == (tier == "SSS"), (sid, tier)
            for line in filter(None, (look.divider, look.frame)):
                assert len(line) <= ORNAMENT_MAX, (sid, tier, line)
    assert chat_look("nope", "D") is None and chat_look("frost", "X") is None
    # набор: знак только при собранном наборе и только у скина из набора
    assert chat_look("sakura_storm", "D", set_complete=True).crest == "🌸 Набор «Сад Сакуры» собран"
    assert chat_look("sakura_storm", "D").crest is None and chat_look("frost", "D", set_complete=True).crest is None
    # без скина всё как было
    assert skin_text.sep(None) == " · " and skin_text.icon(None, skin_text.MESSAGES, "💬") == "💬"
    assert skin_text.frame(None, "x") == "x" and skin_text.head_lines(None) == [] and skin_text.name_icon(None) == "👤"
    sss = chat_look("frost", "SSS")
    framed = skin_text.frame(sss, "тело")
    assert framed.splitlines()[0] == sss.frame and framed.splitlines()[2] == sss.frame and PHRASES["frost"] in framed
    # «Лесной Странник»: титул равен названию, в строке он один раз
    assert chat_look("forest", "D").skin_line == "Лесной Странник · D"
    assert chat_look("frost", "B").skin_line == "Дитя Стужи · Изморозь · B"


def images() -> None:
    random.seed(7)
    counts = [max(0, int(random.gauss(60, 30))) for _ in range(30)]
    start = date(2026, 10, 20) - timedelta(days=29)
    worst = 0.0
    for sid in SKINS:
        for tier in TIERS:
            look = chat_look(sid, tier)
            png = activity_graph.render(counts, start, theme=skin_card.theme_for(look))
            started = time.perf_counter()
            jpeg = skin_card.compose(png, look, "Очень Длинное Имя Игрока 🐉 Ещё длиннее", "a_really_long_username_here")
            worst = max(worst, time.perf_counter() - started)
            from io import BytesIO
            img = Image.open(BytesIO(jpeg))
            assert img.size == (W, H) and img.format == "JPEG", (sid, tier, img.size)
    assert worst < COMPOSE_LIMIT_SEC, f"slowest card {worst:.3f}s"
    # имя из одних эмодзи: рисуется ник, а не квадратики
    assert skin_card.drawable("🐉🔥") == "" and skin_card.drawable("Макс 🐉 Max") == "Макс Max"
    print(f"cards: {len(SKINS) * len(TIERS)} rendered, slowest {worst:.3f}s")


if __name__ == "__main__":
    text_rules()
    images()
    print("skins chat style: OK")
