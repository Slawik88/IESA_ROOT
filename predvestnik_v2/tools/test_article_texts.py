#!/usr/bin/env python3
"""Банк «Моя статья» (bot/chat/article_texts/, S22): объём, граница контента, безопасность.

Граница сессии (файл S22): пародия про самого игрока; sexual-темы и всё с
несовершеннолетними запрещены; без инструкций «как совершить»; без реальных
людей; без формулировок, выдающих текст за настоящий правовой документ.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_article_texts.py
"""
from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "1:test-article-texts")
os.environ.setdefault("DATABASE_URL", "postgresql://article-texts@127.0.0.1:5433/article-texts")

import unittest

from bot.chat.article import PARODY_MARK
from bot.chat.article_texts import BANK, DESCRIPTIONS
from bot.chat.article_texts.articles import ARTICLES, BY_NUMBER

MIN_TOTAL = 500
MIN_DESCRIPTIONS = 300
MIN_CATEGORY = {"intro": 40, "verdict": 60, "repeat": 40, "cooldown": 25, "disabled": 15, "service": 20}

# Корни запрещённых тем (граница сессии): sexual-составы, несовершеннолетние,
# суицид, геноцид; мат и оскорбления; жаргон PLAYER_COPY.
FORBIDDEN_ROOTS = (
    "секс", "порно", "интим", "постель", "эротик", "стриптиз", "оргазм", "обнаж", "проституц",
    "изнасил", "растлен", "педофил", "несовершеннолетн",
    "суицид", "самоубийств", "повесил", "геноцид",
    "бля", "хуй", "пизд", "еба", "ёб", "сука", "мраз", "ненавиж",
)
# Фразы, выдающие текст за настоящий правовой документ.
LEGAL_IMPERSONATION = (
    "УК РФ", "уголовный кодекс", "уголовного кодекса", "согласно ст", "вы обязаны",
    "лет тюрьмы", "лет лишения", "год тюрьмы", "смертная казнь", "сроком до",
)
# Инструкции и исполнение запрещены границей; подстраховка по формулировкам.
INSTRUCTION_MARKS = ("как совершить", "пошаговая", "инструкция по совершению", "способ совершить")


def all_bank_phrases() -> list[str]:
    return [template for phrases in BANK.texts.values() for template in phrases]


def gather() -> list[str]:
    """Все тексты банка плюс описания статей — для пограничных проверок."""
    return all_bank_phrases() + [description for _, description in DESCRIPTIONS]


class VolumeTests(unittest.TestCase):
    def test_total_and_categories(self):
        for category, minimum in MIN_CATEGORY.items():
            self.assertGreaterEqual(len(BANK.texts[category]), minimum, category)
        self.assertGreaterEqual(BANK.size() + len(DESCRIPTIONS), MIN_TOTAL)

    def test_descriptions_volume(self):
        self.assertGreaterEqual(len(DESCRIPTIONS), MIN_DESCRIPTIONS)

    def test_whitelist_consistency(self):
        self.assertGreaterEqual(len(ARTICLES), 90, "белый список статей")
        self.assertEqual(len({number for number, _ in ARTICLES}), len(ARTICLES), "номера уникальны")
        for number, name in ARTICLES:
            self.assertRegex(number, r"^\d{2,3}(\.\d)?$", number)
            self.assertTrue(2 <= len(name) <= 80, name)
            self.assertEqual(BY_NUMBER[number], name)


class BoundaryTests(unittest.TestCase):
    def test_forbidden_roots_absent(self):
        for text in gather():
            lowered = text.lower().replace("ё", "е")
            for root in FORBIDDEN_ROOTS:
                self.assertNotIn(root, lowered, f"граница контента: «{root}» в «{text[:70]}»")

    def test_no_legal_impersonation(self):
        for text in gather():
            for phrase in LEGAL_IMPERSONATION:
                self.assertNotIn(phrase, text, f"не притворяемся документом: «{phrase}» в «{text[:70]}»")

    def test_no_instruction_marks(self):
        for text in gather():
            lowered = text.lower()
            for phrase in INSTRUCTION_MARKS:
                self.assertNotIn(phrase, lowered, f"без инструкций: «{phrase}» в «{text[:70]}»")

    def test_parody_mark_present_in_module(self):
        self.assertIn("Пародия", PARODY_MARK)
        self.assertIn("не юридическая", PARODY_MARK)

    def test_descriptions_reference_whitelist(self):
        for number, _ in DESCRIPTIONS:
            self.assertIn(number, BY_NUMBER, number)


class SafetyTests(unittest.TestCase):
    def test_no_foreign_braces_in_templates(self):
        for category, phrases in BANK.texts.items():
            for template in phrases:
                self.assertNotRegex(template, r"\{(?!(?:[ab]|sec)})[^}]*\}", f"{category}: {template[:60]}")

    def test_disabled_category_keeps_html_code_only(self):
        for template in BANK.texts["disabled"]:
            self.assertTrue(re.fullmatch(r"[^<>]*<code>[^<>]*</code>", template), template[:60])

    def test_templates_without_markup_are_plain(self):
        for category in ("intro", "verdict", "repeat", "cooldown", "service"):
            for template in BANK.texts[category]:
                self.assertNotRegex(template, r"[<>]", f"{category}: {template[:60]}")

    def test_no_links_or_mentions_anywhere(self):
        for text in gather():
            for fragment in ("http://", "https://", "t.me", "tg://", "@"):
                self.assertNotIn(fragment, text, text[:70])

    def test_descriptions_render_with_long_nick(self):
        nick = html.escape('<b>Подсудимый_Ёжик_🦔_&page=1</b>')
        for number, description in DESCRIPTIONS:
            rendered = f"Обвиняемый: {nick}\nСт. {number} — {BY_NUMBER[number]}\n{description}"
            self.assertGreater(len(rendered), 0)


class DeterminismTests(unittest.TestCase):
    def test_daily_index_is_stable_and_spread(self):
        from datetime import date
        from core import article
        day = date(2026, 11, 1)
        for user_id in (1, 42, 1001, 999999):
            index = article.daily_description_index(user_id, day, len(DESCRIPTIONS))
            self.assertEqual(index, article.daily_description_index(user_id, day, len(DESCRIPTIONS)))
            self.assertEqual(index, article.daily_description_index(user_id, day.isoformat(), len(DESCRIPTIONS)))
        spread = {article.daily_description_index(u, day, len(DESCRIPTIONS)) for u in range(1, 400)}
        self.assertGreater(len(spread), 100, "статьи игроков не должны слипаться")
        with self.assertRaises(ValueError):
            article.daily_description_index(1, day, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
