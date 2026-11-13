"""Общий механизм банков текстов чат-бота (создан в S21, используется S22).

Банк — словарь «категория → кортеж фраз-шаблонов» с подстановками вида {a}.
build() проверяет банк при сборке: уникальность после нормализации, безопасность
фигурных скобок (str.format падает на чужих скобках), границы длины, отсутствие
ссылок, упоминаний и запрещённых слов. Битая фраза падает с понятной ошибкой
на старте теста, а не доходит до игрока.

Выбор фразы: pick() — случайно, pick_stable() — детерминированно по seed
(одинаковый seed всегда даёт одну и ту же фразу из категории).
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
# Ссылки и упоминания в банке запрещены: имена подставляет код, уже без пинга.
_FORBIDDEN_SUBSTRINGS = ("http://", "https://", "t.me", "tg://", "@")


def normalize(text: str) -> str:
    """Ключ уникальности: регистр, «ё» и знаки не различаются («Ты + Он!» = «ты он»)."""
    return " ".join(re.sub(r"[^\w]+", " ", text.lower().replace("ё", "е")).split())


@dataclass(frozen=True)
class TextBank:
    texts: Mapping[str, tuple[str, ...]]
    fields: Mapping[str, frozenset[str]]

    def size(self) -> int:
        return sum(len(phrases) for phrases in self.texts.values())

    def categories(self) -> tuple[str, ...]:
        return tuple(self.texts)

    def pick(self, category: str, **subs: str) -> str:
        template = random.choice(self.texts[category])
        return template.format(**subs)

    def pick_stable(self, category: str, seed: str, **subs: str) -> str:
        phrases = self.texts[category]
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return phrases[int.from_bytes(digest[:4], "big") % len(phrases)].format(**subs)


def build(texts: Mapping[str, tuple[str, ...]], fields: Mapping[str, Iterable[str]], *,
          min_len: int = 20, max_len: int = 200, stop_words: Iterable[str] = ()) -> TextBank:
    """Собрать и проверить банк; каждая проблема — ValueError с категорией и фразой."""
    if not texts:
        raise ValueError("text bank is empty")
    stop_words = tuple(stop_words)
    problems: list[str] = []
    checked: dict[str, tuple[str, ...]] = {}
    seen_global: set[str] = set()   # дубль ищем по всему банку, не только внутри категории
    for category, phrases in texts.items():
        if not phrases:
            problems.append(f"{category}: пустая категория")
            continue
        allowed = frozenset(fields.get(category, ()))
        seen: set[str] = set()
        valid: list[str] = []
        for template in phrases:
            label = f"{category}: «{template[:60]}»"
            if not isinstance(template, str):
                problems.append(f"{label} — не строка")
                continue
            if len(template) < min_len or len(template) > max_len:
                problems.append(f"{label} — длина {len(template)}, границы {min_len}–{max_len}")
            used = set(_PLACEHOLDER_RE.findall(template))
            unknown = used - allowed
            if unknown:
                problems.append(f"{label} — чужие подстановки {sorted(unknown)}, разрешены {sorted(allowed)}")
            try:
                template.format(**{name: "Имя" for name in allowed})
            except (KeyError, IndexError, ValueError) as error:
                problems.append(f"{label} — битые фигурные скобки: {error}")
            lowered = template.lower().replace("ё", "е")
            for word in stop_words:
                if word in lowered:
                    problems.append(f"{label} — запрещённое слово «{word}»")
            for fragment in _FORBIDDEN_SUBSTRINGS:
                if fragment in template:
                    problems.append(f"{label} — запрещённый фрагмент «{fragment}» (ссылки и упоминания пишёт код)")
            key = normalize(template)
            if key in seen or key in seen_global:
                problems.append(f"{label} — дубль после нормализации")
            seen.add(key)
            seen_global.add(key)
            valid.append(template)
        checked[category] = tuple(valid)
    if problems:
        raise ValueError("text bank rejected:\n" + "\n".join(problems))
    return TextBank(texts=checked, fields={name: frozenset(values) for name, values in fields.items()})
