#!/usr/bin/env python3
"""Общий механизм банков текстов (bot/chat/text_banks.py, S21): что он ловит и что отдаёт.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_text_banks.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "1:test-text-banks")
os.environ.setdefault("DATABASE_URL", "postgresql://text-banks@127.0.0.1:5433/text-banks")

import unittest

from bot.chat import text_banks


def build(texts, fields=None, **kw):
    return text_banks.build(texts, fields or {}, **kw)


class BuildTests(unittest.TestCase):
    def test_accepts_a_valid_bank(self):
        bank = build({"hello": ("Привет, {a}! Рад тебя видеть снова 🎉",)}, {"hello": ("a", "b")})
        self.assertEqual(bank.size(), 1)
        self.assertEqual(bank.pick("hello", a="Мяу", b="Гав"), "Привет, Мяу! Рад тебя видеть снова 🎉")

    def test_rejects_duplicates_after_normalization(self):
        with self.assertRaisesRegex(ValueError, "дубль"):
            build({"hello": ("Ты + Он!", "ТЫ+ОН", "ты он")})

    def test_rejects_duplicate_across_categories(self):
        with self.assertRaisesRegex(ValueError, "дубль"):
            build({"a": ("Одинаковая фраза про котов 🐈",), "b": ("Одинаковая фраза про котов 🐈",)})

    def test_rejects_unknown_placeholder(self):
        with self.assertRaisesRegex(ValueError, "чужие подстановки"):
            build({"hello": ("Привет-привет, {c} и {a}, давно не виделись!",)}, {"hello": ("a",)})

    def test_rejects_cyrillic_placeholder(self):
        with self.assertRaisesRegex(ValueError, "скобки"):
            build({"hello": ("Привет-привет, {ник}, давно не виделись, рад встрече!",)}, {"hello": ("a",)})

    def test_rejects_stray_braces(self):
        with self.assertRaisesRegex(ValueError, "скобки"):
            build({"hello": ("Скобки { тут лишние,.format() упадёт 🧱",)}, {"hello": ("a",)})

    def test_rejects_stop_word(self):
        with self.assertRaisesRegex(ValueError, "кулдаун"):
            build({"hello": ("Пауза, кулдаун закончится через минуту ⏳",)}, stop_words=("кулдаун",))

    def test_rejects_links_and_mentions(self):
        with self.assertRaisesRegex(ValueError, "t.me"):
            build({"hello": ("Ссылка t.me/example тут запрещена 🔗",)})
        with self.assertRaisesRegex(ValueError, "упоминания"):
            build({"hello": ("Напиши на @example, он в курсе 📮",)})

    def test_rejects_wrong_length(self):
        with self.assertRaisesRegex(ValueError, "длина"):
            build({"hello": ("Коротко ⛔",)}, min_len=20, max_len=200)
        with self.assertRaisesRegex(ValueError, "длина"):
            build({"hello": ("Длинно " + "очень " * 40 + "⛔",)}, min_len=20, max_len=200)

    def test_rejects_empty_category(self):
        with self.assertRaisesRegex(ValueError, "пустая категория"):
            build({"hello": ()})

    def test_error_lists_every_problem_at_once(self):
        with self.assertRaises(ValueError) as caught:
            build({"hello": ("Кулдаун снова ⏳", "Кулдаун снова ⏳")}, stop_words=("кулдаун",))
        self.assertIn("кулдаун", str(caught.exception))
        self.assertIn("дубль", str(caught.exception))


class PickTests(unittest.TestCase):
    def setUp(self):
        self.bank = build(
            {"a": ("Первая фраза про облака ☁️", "Вторая фраза про чайники 🫖"), "b": ("Единственная фраза про мёд 🍯",)},
            {"a": ("x",), "b": ("x",)},
        )

    def test_pick_returns_both_phrases_over_many_calls(self):
        seen = {self.bank.pick("a") for _ in range(200)}
        self.assertEqual(len(seen), 2)

    def test_pick_stable_is_deterministic(self):
        first = self.bank.pick_stable("a", "seed-1")
        self.assertEqual(first, self.bank.pick_stable("a", "seed-1"))
        self.assertIn(first, self.bank.texts["a"])

    def test_pick_stable_spreads_seeds(self):
        seen = {self.bank.pick_stable("a", f"seed-{i}") for i in range(100)}
        self.assertEqual(len(seen), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
