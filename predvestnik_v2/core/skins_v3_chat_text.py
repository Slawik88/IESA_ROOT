"""Ширина строк сообщения бота и перенос без «съехавших» рамок (основа core/skins_v3_chat_layout.py).

Шрифт в Telegram пропорциональный, поэтому держится только то, что привязано к левому краю. Ломает вид перенос:
продолжение строки уходит без знака строки. Поэтому каждая строка меряется (width_em) и не шире LINE_EM; ячейки,
которые не влезают, уходят на следующую строку, длинное — на подстроки по словам (ссылка <a> не делится)."""
from __future__ import annotations

import functools
import html
import re
from pathlib import Path

LINE_EM = 15.0          # ширина строки в em шрифта чата: столько помещается в пузырь на экране 320 pt
_EMOJI_EM, _MISSING_EM = 1.25, 1.0
_ZERO = {0x200B, 0x200C, 0x200D, 0xFE0E, 0xFE0F}


@functools.lru_cache(maxsize=2)
def _metrics(bold: bool = False) -> dict[int, float]:
    """Ширины символов DejaVu Sans (идёт вместе с matplotlib). Он шире шрифтов Telegram, поэтому оценка с запасом."""
    from fontTools.ttLib import TTFont
    import matplotlib
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    font = TTFont(str(Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf" / name))
    upem, hmtx = font["head"].unitsPerEm, font["hmtx"]
    return {cp: hmtx[glyph][0] / upem for cp, glyph in font["cmap"].getBestCmap().items()}


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _run_em(chars: str, bold: bool) -> float:
    widths = _metrics(bold)
    total = 0.0
    for i, ch in enumerate(chars):
        cp = ord(ch)
        if cp in _ZERO:
            continue
        as_emoji = i + 1 < len(chars) and ord(chars[i + 1]) == 0xFE0F   # «❄️»: телефон рисует эмодзи, а не знак шрифта
        if cp >= 0x1F000 or as_emoji or (0x2600 <= cp <= 0x27BF and cp not in widths):
            total += _EMOJI_EM
        else:
            total += widths.get(cp, _MISSING_EM)
    return total


def width_em(text: str) -> float:
    """Ширина строки (HTML Telegram) в em: полужирное — по полужирному начертанию, эмодзи по 1,25, неизвестные символы по 1."""
    total, bold = 0.0, 0
    for piece in re.split(r"(<[^>]+>)", text):
        if piece.startswith("<"):
            tag = piece.strip("</> ").split()[0].lower() if piece.strip("</> ") else ""
            if tag == "b":
                bold += -1 if piece.startswith("</") else 1
            continue
        total += _run_em(html.unescape(piece), bold > 0)
    return total


def fits(line: str) -> bool:
    return width_em(line) <= LINE_EM


def cut(text: str, room_em: float) -> str:
    """Обрезать простой текст так, чтобы он занял не больше room_em, с «…»."""
    if width_em(text) <= room_em:
        return text
    while text and width_em(text + "…") > room_em:
        text = text[:-1]
    return text.rstrip() + "…"


def pack(cells: list[str], sep: str, prefix: str) -> list[str]:
    """Ячейки в строки «┊ a ❄ b»: в строку столько, сколько влезает по ширине."""
    rows: list[str] = []
    for cell in cells:
        if rows and fits(f"{rows[-1]} {sep} {cell}"):
            rows[-1] = f"{rows[-1]} {sep} {cell}"
        else:
            rows.append(prefix + cell)
    return rows


_SOFT = ("b", "i", "u", "s")    # такие теги перенос может разорвать: закрыть в конце строки и открыть заново


def _words(text: str) -> list[str]:
    """Слова строки. Внутри <b>/<i> слово делится с закрытием и повторным открытием тега; ссылку <a> не делит."""
    words, current, stack = [], "", []
    for piece in re.split(r"(<[^>]+>)", text):
        if piece.startswith("<"):
            name = piece.strip("</> ").split()[0].lower() if piece.strip("</> ") else ""
            if piece.startswith("</"):
                if stack and stack[-1] == name:
                    stack.pop()
            elif not piece.endswith("/>"):
                stack.append(name)
            current += piece
            continue
        for i, chunk in enumerate(piece.split(" ")):
            if i and all(t in _SOFT for t in stack):
                words.append(current + "".join(f"</{t}>" for t in reversed(stack)))
                current = "".join(f"<{t}>" for t in stack)
            elif i:
                current += " "
            current += chunk
    words.append(current)
    return [w for w in words if _has_text(w)]


def _has_text(word: str) -> bool:
    return bool(plain(word).strip())


def _lines(text: str, first: str, rest: str) -> list[str]:
    """Перенос по словам: первая строка с префиксом first, продолжения — с rest."""
    if fits(first + text):
        return [first + text]
    out, prefix = [], first
    for word in _words(text):
        joined = _merge(f"{out[-1]} {word}") if out else ""
        if out and fits(joined):
            out[-1] = joined
        else:
            out.append(prefix + word)
            prefix = rest
    return out


def _merge(line: str) -> str:
    """«<b>Лепестковый</b> <b>Вихрь</b>» → «<b>Лепестковый Вихрь</b>» после склейки слов."""
    return re.sub(r"</(b|i|u|s)> <\1>", " ", line)


def wrap(line: str, prefix: str, sub: str) -> list[str]:
    """Свободная строка раздела: не влезла — делится по « · » на строку и подстроки «╰», длинная часть — по словам."""
    if fits(prefix + line):
        return [prefix + line]
    head, *rest = line.split(" · ")
    out = _lines(head, prefix, sub)
    for part in rest:
        if out[-1].startswith(sub) and fits(f"{out[-1]} · {part}"):
            out[-1] = f"{out[-1]} · {part}"
        else:
            out += _lines(part, sub, sub)
    return out
