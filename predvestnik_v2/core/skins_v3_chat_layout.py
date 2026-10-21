"""Текст сообщений бота в стиле надетого скина (HTML Telegram): рамки из символов, разделы, строки «┊», фраза SSS.

Вид (владелец, 2026-10-21):
    ⊱⟡━━꧁༺ ❄ ༻꧂━━⟡⊰
    ┊꧁ ❄️ Макс ꧂┊
    ⊱⟡━━꧁༺ ❄ ༻꧂━━⟡⊰

    ⊱⟡━𓊈🧊СООБЩЕНИЯ𓊉━⟡⊰
    ┊ сегодня 112 ❄ неделя 498
    ┊ месяц 1 833
    ⊱⟡━━━━━━━━━━━━━⟡⊰

Шрифт в Telegram пропорциональный, поэтому держится только то, что привязано к левому краю. Ломает вид перенос:
продолжение строки уходит без «┊». Поэтому каждая строка меряется (width_em) и не шире LINE_EM; ячейки, которые не
влезают, уходят на следующую строку «┊», а не обрываются. Линии рамок берутся из вида рамки скина, символ — из частиц.

Тир (core/skins_v3_chat.py): D, C — простые разделы; B, A — разделы с 𓊈…𓊉 и концами ⊱⟡; S, SS — плюс блок с
именем сверху; SSS — плюс подпись внизу и фраза образа."""
from __future__ import annotations

import functools
import html
import re
from pathlib import Path

from core.skins_v3 import TIERS
from core.skins_v3_catalog import SKINS
from core.skins_v3_chat import ChatLook

LINE_EM = 15.0          # ширина строки в em шрифта чата: столько помещается в пузырь на экране 320 pt
LINES = {"ring": "─", "dash": "┄", "double": "═", "seg": "━", "drip": "┅"}
ROW, SUB = "┊ ", "┊ ╰ "
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


def level(look: ChatLook) -> int:
    """0: D, C · 1: B, A · 2: S, SS · 3: SSS."""
    return (0, 0, 1, 1, 2, 2, 3)[TIERS.index(look.tier)]


def _line(look: ChatLook) -> str:
    return LINES.get(SKINS[look.skin_id]["kinds"].get("frame"), "━")


def cut(text: str, room_em: float) -> str:
    """Обрезать простой текст так, чтобы он занял не больше room_em, с «…»."""
    if width_em(text) <= room_em:
        return text
    while text and width_em(text + "…") > room_em:
        text = text[:-1]
    return text.rstrip() + "…"


def pack(cells: list[str], sep: str, prefix: str = ROW) -> list[str]:
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


def wrap(line: str, prefix: str = ROW) -> list[str]:
    """Свободная строка раздела: не влезла — делится по « · » на строку и подстроки «╰», длинная часть — по словам."""
    if fits(prefix + line):
        return [prefix + line]
    head, *rest = line.split(" · ")
    out = _lines(head, prefix, SUB)
    for part in rest:
        if out[-1].startswith(SUB) and fits(f"{out[-1]} · {part}"):
            out[-1] = f"{out[-1]} · {part}"
        else:
            out += _lines(part, SUB, SUB)
    return out


_PROBE = "Сообщения"     # самый длинный заголовок: по нему выбирается одна рамка для всех разделов сообщения


@functools.lru_cache(maxsize=64)
def _full_headers(skin_id: str) -> bool:
    ln = LINES.get(SKINS[skin_id]["kinds"].get("frame"), "━")
    return fits(f"⊱⟡{ln}𓊈🧊<b>{_PROBE.upper()}</b>𓊉{ln}⟡⊰")


def section(look: ChatLook, icon: str, title: str, rows: list[str]) -> str:
    """Раздел: заголовок с рамкой, строки (уже с «┊»), нижняя черта."""
    ln, top = _line(look), html.escape(title.upper())
    if level(look) == 0:
        head, close = f"{ln * 2} {icon} <b>{top}</b> {ln * 2}", ln * 14
    else:
        edge = ln if _full_headers(look.skin_id) else ""
        head, close = f"⊱⟡{edge}𓊈{icon}<b>{top}</b>𓊉{edge}⟡⊰", f"⊱⟡{ln * 13}⟡⊰"
    return "\n".join([head, *rows, close])


def banner(look: ChatLook, name: str, username: str | None) -> str:
    """Шапка: на S+ блок с именем в рамке, ниже — одна строка с именем. name и username — простой текст."""
    sym, glyph = look.sep, look.glyph
    if level(look) < 2:
        shown = html.escape(cut(name, LINE_EM - 2.5))
        lines = [f"{glyph} <b>{shown}</b>"] + ([ROW + html.escape(cut(f"@{username}", LINE_EM - 1.5))] if username else [])
        return "\n".join(lines + _skin_rows(look))
    ln = _line(look)
    shown = html.escape(cut(name, LINE_EM - 6.5))
    lines = [f"⊱⟡{ln * 2}꧁༺ {sym} ༻꧂{ln * 2}⟡⊰", f"┊꧁ {glyph} <b>{shown}</b> ꧂┊"]
    if username:
        lines.append(ROW + html.escape(cut(f"@{username}", LINE_EM - 1.5)))
    named = " · ".join([look.title] + ([look.name] if look.name != look.title else []))
    lines += [*_skin_rows(named), f"⊱⟡{ln * 2}꧁༺ <b>{look.tier}</b> ༻꧂{ln * 2}⟡⊰"]   # на S+ тир стоит в нижней рамке шапки
    return "\n".join(lines)


def _skin_rows(line: str | ChatLook) -> list[str]:
    """«┊ Дитя Стужи · Изморозь · B» курсивом; длинный титул — с подстрокой «╰»."""
    text = line.skin_line if isinstance(line, ChatLook) else line
    return [f"{r[:len(r) - len(r.lstrip('┊ ╰'))]}<i>{r.lstrip('┊ ╰')}</i>" for r in wrap(html.escape(text))]


def crest_rows(look: ChatLook) -> list[str]:
    """«🌸 Набор собран · «Сад Сакуры»»: короче, чем фраза из каталога, и делится на строку и подстроку."""
    if not look.crest:
        return []
    found = re.match(r"^(\S+) Набор «(.+)» собран$", look.crest)
    text = f"{found.group(1)} Набор собран · «{found.group(2)}»" if found else look.crest
    return wrap(html.escape(text))


def heading(look: ChatLook, who_html: str, suffix: str) -> str:
    """«❄️ <b>Ваш стрик</b>»: имя (уже экранированное) сокращается, чтобы строка влезла в экран."""
    name = html.unescape(who_html)
    line = f"{look.glyph} <b>{html.escape(name)} {suffix}</b>"
    while not fits(line) and name:
        name = name[:-1]
        line = f"{look.glyph} <b>{html.escape(name.rstrip())}… {suffix}</b>"
    return line


def footer(look: ChatLook) -> str | None:
    """SSS: подпись образа и его фраза."""
    if level(look) < 3:
        return None
    name = html.escape(look.name)
    sign = next((v for v in (f"꧁𓊈𒆜 {name} 𒆜𓊉꧂", f"꧁ {name} ꧂", f"{look.sep} {name} {look.sep}") if fits(v)), name)
    return sign + (f"\n\n«{html.escape(look.phrase)}» ✨" if look.phrase else "")


def message(look: ChatLook, parts: list[str]) -> str:
    """Склеить шапку, разделы и подпись пустыми строками, как в образце."""
    tail = footer(look)
    return "\n\n".join([p for p in parts if p] + ([tail] if tail else []))
