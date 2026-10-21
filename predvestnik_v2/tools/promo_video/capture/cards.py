"""Настоящие карточки активности «бот я» в оформлении скинов (как бот присылает их в чат).

    cd predvestnik_v2 && BOT_TOKEN=0:promo DATABASE_URL=postgresql://none@127.0.0.1:1/none \
        python3 tools/promo_video/capture/cards.py

Пишет tools/promo_video/assets/card_<скин>_<тир>.jpg. Рисует bot/chat/activity_graph + bot/chat/skin_card на демо-цифрах.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from bot.chat import activity_graph, skin_card  # noqa: E402
from core.skins_v3_chat import chat_look  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "assets")
CARDS = [("starheart", "SSS", "Лиза", "liza"), ("scarlet_star", "SSS", "Марк", "mark_off"),
         ("sakura_storm", "S", "Кира", "kira_bloom"), ("midnight_comet", "SSS", "Тёма", "tema_frog")]

os.makedirs(OUT, exist_ok=True)
for i, (skin, tier, name, username) in enumerate(CARDS):
    rnd = random.Random(i + 4)
    counts = [rnd.randint(30, 160) for _ in range(29)] + [214 - i * 40]
    look = chat_look(skin, tier)
    png = activity_graph.render(counts, date.today() - timedelta(days=29), theme=skin_card.theme_for(look))
    path = os.path.join(OUT, f"card_{skin}_{tier}.jpg")
    with open(path, "wb") as f:
        f.write(skin_card.compose(png, look, name, username))
    print(os.path.relpath(path, ROOT))
