#!/usr/bin/env python3
"""Банк «Шипперим» (bot/chat/ship_texts/, S21): объём, чистота и безопасность подстановок.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_ship_texts.py
"""
from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "1:test-ship-texts")
os.environ.setdefault("DATABASE_URL", "postgresql://ship-texts@127.0.0.1:5433/ship-texts")

import unittest

from bot.chat.ship_texts import BANK
from bot.chat.ship_texts.announce import ANNOUNCE
from bot.chat.ship_texts.author_included import AUTHOR_INCLUDED
from bot.chat.ship_texts.compat import COMPAT_0_10, COMPAT_96_100
from bot.chat.ship_texts.cooldown import COOLDOWN
from bot.chat.ship_texts.nobody import NOBODY
from bot.chat.ship_texts.opted_out import OPTED_OUT
from bot.chat.ship_texts.self_pair import SELF_PAIR
from core import ship

# Самый длинный ник: эмодзи, кириллица, латиница, HTML-символы — после экранирования ничего не ломается.
LONG_NICK = '<b>Влюблённый_Ёжик_🦔_&page=1</b> "с цитатой"'
MIN_TOTAL = 500
MIN_CATEGORY = {"announce": 200, "self_pair": 50, "author_included": 15, "nobody": 20, "cooldown": 25, "opted_out": 15,
                "compat_96_100": 20, "compat_86_95": 20, "compat_71_85": 20, "compat_56_70": 20,
                "compat_41_55": 20, "compat_26_40": 20, "compat_11_25": 20, "compat_0_10": 20}


class VolumeTests(unittest.TestCase):
    def test_total_and_every_category(self):
        for category, minimum in MIN_CATEGORY.items():
            self.assertGreaterEqual(len(BANK.texts[category]), minimum, category)
        self.assertGreaterEqual(BANK.size(), MIN_TOTAL)


class SafetyTests(unittest.TestCase):
    def test_no_html_or_foreign_braces_in_templates(self):
        # Разрешены только подстановки, объявленные в банке: {a}, {b} и {sec}.
        for category, phrases in BANK.texts.items():
            for template in phrases:
                self.assertNotRegex(template, r"[<>]", f"{category}: {template[:60]}")
                self.assertNotRegex(template, r"\{(?!(?:[ab]|sec)})[^}]*\}", f"{category}: {template[:60]}")

    def test_placeholders_render_with_the_longest_nick(self):
        escaped = html.escape(LONG_NICK)
        for template in list(ANNOUNCE) + list(SELF_PAIR) + list(AUTHOR_INCLUDED) + list(OPTED_OUT):
            rendered = template.format(a=escaped, b=escaped, sec=90)
            self.assertGreater(len(rendered), 0)
            self.assertNotIn("&amp;amp;", rendered)

    def test_cooldown_renders_with_seconds(self):
        for template in COOLDOWN:
            rendered = template.format(sec=37)
            self.assertIn("37", rendered, template)

    def test_no_ping_links_anywhere(self):
        for category, phrases in BANK.texts.items():
            for template in phrases:
                self.assertNotIn("tg://user?id=", template, category)

    def test_percent_buckets_cover_0_100_exactly(self):
        keys = {ship.percent_bucket_key(p) for p in range(101)}
        self.assertEqual(keys, set(BANK.texts) & {f"compat_{lo}_{hi}" for lo, hi, _ in ship.PERCENT_BUCKETS})
        self.assertTrue(set(BANK.texts))
        for low, high, key in ship.PERCENT_BUCKETS:
            for percent in range(low, high + 1):
                self.assertEqual(ship.percent_bucket_key(percent), key)
        with self.assertRaises(ValueError):
            ship.percent_bucket_key(101)

    def test_compatibility_percent_is_stable_and_symmetric(self):
        self.assertEqual(ship.compatibility_percent(7, 13), ship.compatibility_percent(13, 7))
        spread = {ship.compatibility_percent(a, b) for a, b in ((i, i * 3 + 1) for i in range(1, 300))}
        self.assertGreater(len(spread), 60, "проценты пар не должны слипаться в одном месте")


class ToneTests(unittest.TestCase):
    def test_every_text_ends_with_emoji(self):
        emoji_tail = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u23E9-\u23FA]\uFE0F?\s*$")
        for category, phrases in BANK.texts.items():
            for template in phrases:
                self.assertRegex(template, emoji_tail, f"{category}: {template[:60]}")

    def test_pair_texts_avoid_gendered_past_about_a_single_player(self):
        # {a}/{b} — один человек; мужской/женский род прошедшего времени о нём не пишем.
        # «{a} и {b} обменялись» — законное множественное число, как и средний род чужого существительного.
        gendered = re.compile(r"\{[ab]\} [а-яё]+(?:л|ла|лся|лась)\b")
        for category in ("announce", "self_pair", "author_included", "opted_out"):
            for template in BANK.texts[category]:
                for match in gendered.finditer(template):
                    before = template[max(0, match.start() - 7):match.start()]
                    self.assertIn("{a} и ", before, f"{category}: {template[:70]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
