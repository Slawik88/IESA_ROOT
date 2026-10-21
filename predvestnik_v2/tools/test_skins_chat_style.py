#!/usr/bin/env python3
"""Скины в чате без базы: разметка текста, картинка и видео для каждого скина на каждом тире (docs/SKINS_CHAT_DESIGN_HANDOFF.md).

Главное правило разметки: строка с рамкой («┊», «⊱», «─»…) не шире LINE_EM, иначе на узком экране она переносится
и продолжение уходит без «┊». Свободный текст (фраза SSS, сноска) переноситься может."""
from __future__ import annotations

import os
import random
import sys
import time
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOT_TOKEN", "123456:offline-style-test")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1/predvestnik_preprod")

from PIL import Image  # noqa: E402

from bot.chat import activity_graph, profile, profile_view, skin_card, skin_motion  # noqa: E402
from bot.chat.skin_card_draw import H, W  # noqa: E402
from core import skins_v3_chat_layout as L  # noqa: E402
from core.skins_v3 import TIERS  # noqa: E402
from core.skins_v3_catalog import SKINS  # noqa: E402
from core.skins_v3_chat import ORNAMENT_MAX, chat_look, ornament_line  # noqa: E402
from core.skins_v3_chat_phrases import PHRASES  # noqa: E402
from core.skins_v3_chat_kits import KITS  # noqa: E402
from services import skin_chat_news  # noqa: E402

COMPOSE_LIMIT_SEC = 0.6     # картинка с холодным декором; бюджет в боте 0.9 с
MOTION_LIMIT_SEC = 3.0      # видео SSS; бюджет в боте 3 с
FREE = ("«", "<i>Серия", "За каждый")     # свободные строки: им можно переноситься


def sample() -> profile_view.CardData:
    """Длинные, но настоящие данные: так выглядит карточка активного игрока."""
    d = profile_view.CardData(title="Очень Длинное Имя Игрока 🐉", username="a_rather_long_username_x32chars")
    d.head = ["🏷 <b>свлд Арлекино</b>", "Старейшина · 🌌 Главный разработчик · 💖 Спонсор", "👑 VIP · 🆔 1460945748"]
    d.messages = [("сегодня", "1 112"), ("неделя", "14 498"), ("месяц", "61 833")]
    d.totals = [("всего", "1 224 310"), ("во всех", "1 931 002")]
    d.progress = [("серия", "112 дней"), ("рекорд", "400 дней"), ("место", "#13"), ("достижения", "131/641")]
    d.personal = ["📅 В чате <b>1210</b> дней · 🕓 5 мин назад", "↩️ Вернулся в чат · впервые здесь 01.02.2026",
                  "⚠️ Варнов <b>2</b>", "💞 В браке с @​lina_ash_the_longest", "\x00[Пепел] · вместе 129 дней"]
    d.wallet = ["мора <b>1 697 000</b> 🪙", "алмазы <b>6 000</b> 💎", "эссенция <b>86 000</b> 🔮", "зарники <b>4 120</b> ✨"]
    return d


def check_lines(text: str, where: str) -> None:
    for line in text.splitlines():
        if line and not line.startswith(FREE):
            assert L.fits(line), f"{where}: {L.width_em(line):.1f} em > {L.LINE_EM}: {L.plain(line)!r}"


def catalog_rules() -> None:
    assert set(PHRASES) == set(SKINS), set(SKINS) ^ set(PHRASES)
    for sid in SKINS:
        assert len(PHRASES[sid]) <= 60 and len(ornament_line(sid)) <= ORNAMENT_MAX, sid
        for tier in TIERS:
            look = chat_look(sid, tier)
            assert look and look.glyph and look.title and all(look.icons), (sid, tier)
            assert (look.sep != "·") == (TIERS.index(tier) >= TIERS.index("B")), (sid, tier)
            assert (look.phrase is not None) == (tier == "SSS"), (sid, tier)
    assert chat_look("nope", "D") is None and chat_look("frost", "X") is None
    assert chat_look("sakura_storm", "D", set_complete=True).crest == "🌸 Набор «Сад Сакуры» собран"
    assert chat_look("sakura_storm", "D").crest is None and chat_look("frost", "D", set_complete=True).crest is None


def layout() -> None:
    """Каждый скин × тир: карточка, баланс, стрик, достижения и новости не шире экрана и влезают в подпись."""
    balance = ["🪙 Мора: <b>1 697 000</b>", "💎 Алмазы: <b>6 000</b>", "🔮 Эссенция: <b>86 000</b>", "✨ Зарники: <b>4 120</b>"]
    medals = [("Общение", "🥇 💬 <b>Болтун</b> ✨", "ур. 11/12 · 1 234 567 / 2 000 000"), ("Семья", "🥉 💞 <b>Верность</b>", "ур. 3/9 · максимум")]
    for sid in SKINS:
        for tier in TIERS:
            look = chat_look(sid, tier, set_complete=True)
            text = profile_view.styled(sample(), look)
            check_lines(text, f"card {sid}/{tier}")
            assert profile.caption_len(text) <= profile.CAPTION_LIMIT, (sid, tier, profile.caption_len(text))
            check_lines(profile_view.balance(look, balance), f"balance {sid}/{tier}")
            check_lines(profile_view.streak(look, "@​a_rather_long_username", 112, 400, "⏳ Напишите в чат, чтобы засчитать сегодня"), f"streak {sid}/{tier}")
            check_lines(profile_view.achievements(look, "Ваши", medals, 131, 641, "За каждый 5-й уровень"), f"achievements {sid}/{tier}")
        for kind in ("buy", "sss"):
            check_lines(skin_chat_news.text(1, "a_rather_long_username_x32chars", [{"skin_id": sid, "kind": kind}]), f"news {sid}/{kind}")
    many = [{"skin_id": s, "kind": k} for s, k in (("glass_heart", "buy"), ("phantom_carriage", "sss"), ("gingerbread_house", "buy"))]
    check_lines(skin_chat_news.text(1, "a_rather_long_username_x32chars", many), "news many")


def kits_and_tiers() -> None:
    """У каждого скина свой набор символов, у каждого тира — свой вид."""
    assert set(KITS) == set(SKINS), set(SKINS) ^ set(KITS)
    assert len(set(KITS.values())) == len(KITS), "два скина с одинаковым набором символов"
    for sid in SKINS:
        views = {profile_view.styled(sample(), chat_look(sid, tier)) for tier in TIERS}
        assert len(views) == len(TIERS), (sid, len(views))


def plain_unchanged() -> None:
    """Без скина карточка ровно та, что была до скинов (стиль v2)."""
    d = profile_view.CardData(title="Макс", username="maks", head=["🏷 <b>Сяо</b>"],
                              messages=[("сегодня", "1"), ("неделя", "2"), ("месяц", "3")], totals=[("всего", "4")],
                              progress=[("серия", "1 день"), ("рекорд", "2 дня"), ("место", "#1")],
                              personal=["💞 В браке с @​x", "\x00вместе 3 дня"], wallet=["мора <b>1</b> 🪙", "алмазы <b>2</b> 💎", "эссенция <b>3</b> 🔮"])
    assert profile_view.plain(d) == (
        "👤 <b>Макс</b> · @maks\n🏷 <b>Сяо</b>\n\n"
        "💬 <b>Сообщения</b>\n<blockquote>сегодня <b>1</b> · неделя <b>2</b> · месяц <b>3</b>\nвсего <b>4</b></blockquote>\n\n"
        "🔥 <b>Прогресс</b>\n<blockquote>серия <b>1 день</b> · рекорд <b>2 дня</b>\nместо <b>#1</b></blockquote>\n\n"
        "💞 В браке с @​x\n<blockquote>вместе 3 дня</blockquote>\n\n"
        "💰 <b>Кошелёк</b>\n<blockquote>мора <b>1</b> 🪙 · алмазы <b>2</b> 💎\nэссенция <b>3</b> 🔮</blockquote>"), profile_view.plain(d)


def images_and_motion() -> None:
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
            img = Image.open(BytesIO(jpeg))
            assert img.size == (W, H) and img.format == "JPEG", (sid, tier, img.size)
    assert worst < COMPOSE_LIMIT_SEC, f"slowest card {worst:.3f}s"
    assert skin_card.drawable("🐉🔥") == "" and skin_card.drawable("Макс 🐉 Max") == "Макс Max"
    assert skin_motion.available(), "PyAV (av) не установлен: видео SSS не будет"
    slowest = 0.0
    for sid in ("sakura_storm", "midnight_comet", "crimson_dark"):
        look = chat_look(sid, "SSS")
        png = activity_graph.render(counts, start, theme=skin_card.theme_for(look))
        started = time.perf_counter()
        mp4 = skin_card.motion(png, look, "Макс", "maks")
        slowest = max(slowest, time.perf_counter() - started)
        assert mp4[4:8] == b"ftyp" and 20_000 < len(mp4) < 2_000_000, (sid, len(mp4))
    assert slowest < MOTION_LIMIT_SEC, f"slowest motion {slowest:.2f}s"
    print(f"cards: {len(SKINS) * len(TIERS)} rendered, slowest {worst:.3f}s; motion slowest {slowest:.2f}s")


if __name__ == "__main__":
    catalog_rules()
    kits_and_tiers()
    plain_unchanged()
    layout()
    images_and_motion()
    print("skins chat style: OK")
