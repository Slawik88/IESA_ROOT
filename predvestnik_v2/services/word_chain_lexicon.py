"""Offline Russian word validation using the project's existing OpenCorpora dependency."""
from functools import lru_cache

from pymorphy3 import MorphAnalyzer

from core import word_chain as rules


@lru_cache(maxsize=1)
def _dictionary() -> MorphAnalyzer:
    return MorphAnalyzer(lang="ru")


@lru_cache(maxsize=8192)
def is_known(word: str) -> bool:
    # Never accept the analyzer's guesses for invented words: require a dictionary entry.
    return bool(rules.WORD_RE.fullmatch(word) and (word in rules.WORDS or _dictionary().word_is_known(word)))
