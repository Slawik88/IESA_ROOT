"""Текст сообщений бота в стиле надетого скина (HTML Telegram): рамки из символов скина, разделы, строки, фраза SSS.

Образец владельца (2026-10-21) — «Лепестковый Вихрь» на SSS:
    ⊱⟡━꧁༺ 🌸 ༻꧂━⟡⊰
    ┊꧁༺ 🌸 Макс ༻꧂┊
    ┊ ╰ Повелитель Лепестков
    ⊱⟡━꧁༺ SSS ༻꧂━⟡⊰

    ⊱⟡✿𓊈💮СООБЩЕНИЯ𓊉✿⟡⊰
    ┊ день 112 ✿ неделя 498
    ⊱⟡✿━━━━━✿━━━━━✿⟡⊰

У каждого скина свой набор символов (core/skins_v3_chat_kits.py), у каждого тира своя ступень:
  D    знак строки скина, заголовок раздела — значок и название
  C    + линии скина вокруг заголовка и черта под разделом
  B    + концы и скобки рамки скина, разделитель ячеек — знак скина
  A    + знак скина в рамке заголовка и в середине черты
  S    + имя в отдельном блоке со скобками скина, тир в нижней рамке блока
  SS   + знаки скина по краям черты, короткая подпись образа внизу
  SSS  + корона скина в шапке и подписи, фраза образа
Каждая строка с рамкой не шире экрана 320 pt (core/skins_v3_chat_text.py): не влезло — перенос на следующую строку."""
from __future__ import annotations

import functools
import html
import re

from core.skins_v3 import TIERS
from core.skins_v3_chat import ChatLook
from core.skins_v3_chat_kits import Kit, kit_of
from core.skins_v3_chat_text import LINE_EM, cut, fits, pack as _pack, plain, width_em, wrap as _wrap  # noqa: F401

_PROBE = "Сообщения"     # самый длинный заголовок: по нему выбирается одна рамка для всех разделов сообщения


def tier_step(look: ChatLook) -> int:
    """0 (D) … 6 (SSS)."""
    return TIERS.index(look.tier)


def kit(look: ChatLook) -> Kit:
    return kit_of(look.skin_id)


def row(look: ChatLook) -> str:
    return f"{kit(look).row} "


def sub(look: ChatLook) -> str:
    k = kit(look)
    return f"{k.row} {k.sub} "


def sep(look: ChatLook) -> str:
    return kit(look).mark if tier_step(look) >= 2 else "·"


def wrap(look: ChatLook, line: str, *, nested: bool = False) -> list[str]:
    """Свободная строка раздела; nested — сразу подстрокой."""
    return _wrap(line, sub(look) if nested else row(look), sub(look))


def pack(look: ChatLook, cells: list[str]) -> list[str]:
    return _pack(cells, sep(look), row(look))


def _heads(k: Kit, t: int, icon: str, top: str) -> list[str]:
    """Варианты заголовка раздела от богатого к простому."""
    (a, b), (o, c), ln, m = k.ends, k.sec, k.line, k.mark
    plain_head = f"{icon} <b>{top}</b>"
    if t == 0:
        return [plain_head]
    if t == 1:
        return [f"{ln * 2} {icon} <b>{top}</b> {ln * 2}", f"{ln} {icon} <b>{top}</b> {ln}", plain_head]
    framed = [f"{a}{ln}{o}{icon}<b>{top}</b>{c}{ln}{b}", f"{a}{o}{icon}<b>{top}</b>{c}{b}", f"{o}{icon}<b>{top}</b>{c}"]
    if t >= 3:
        framed.insert(0, f"{a}{m}{o}{icon}<b>{top}</b>{c}{m}{b}")
    return framed + [plain_head]


@functools.lru_cache(maxsize=512)
def _head_choice(skin_id: str, t: int) -> int:
    """Какой вариант заголовка влезает для самого длинного названия: один на всё сообщение, чтобы разделы были одинаковы."""
    variants = _heads(kit_of(skin_id), t, "🧊", _PROBE.upper())
    return next((i for i, v in enumerate(variants) if fits(v)), len(variants) - 1)


def _close(k: Kit, t: int) -> str | None:
    (a, b), ln, m = k.ends, k.line, k.mark
    return (None, ln * 14, f"{a}{ln * 13}{b}", f"{a}{ln * 6}{m}{ln * 6}{b}", f"{a}{ln * 6}{m}{ln * 6}{b}",
            f"{a}{m}{ln * 5}{m}{ln * 5}{m}{b}", f"{a}{m}{ln * 5}{m}{ln * 5}{m}{b}")[t]


def section(look: ChatLook, icon: str, title: str, rows: list[str]) -> str:
    """Раздел: заголовок в рамке скина, строки (уже со знаком строки), черта."""
    k, t = kit(look), tier_step(look)
    variants = _heads(k, t, icon, html.escape(title.upper()))
    head = variants[min(_head_choice(look.skin_id, t), len(variants) - 1)]
    close = _close(k, t)
    return "\n".join([head, *rows] + ([close] if close and fits(close) else []))


def _named(look: ChatLook) -> str:
    return " · ".join([look.title] + ([look.name] if look.name != look.title else []))


def _italic(rows: list[str], prefixes: tuple[str, ...]) -> list[str]:
    out = []
    for r in rows:
        pre = next((p for p in prefixes if r.startswith(p)), "")
        out.append(f"{pre}<i>{r[len(pre):]}</i>")
    return out


def banner(look: ChatLook, name: str, username: str | None) -> str:
    """Шапка сообщения. name и username — простой текст. До S — строка с именем, с S — блок в скобках скина."""
    k, t, glyph = kit(look), tier_step(look), look.glyph
    nick = [row(look) + html.escape(cut(f"@{username}", LINE_EM - 1.5))] if username else []
    if t < 4:
        a, b = k.ends if t >= 2 else ("", "")
        shown = html.escape(cut(name, LINE_EM - 3.5 - width_em(a + b)))
        head = f"{a} {glyph} <b>{shown}</b> {b}".strip() if t >= 2 else f"{glyph} <b>{shown}</b>"
        rows = _italic(wrap(look, html.escape(look.skin_line)), (sub(look), row(look)))
        return "\n".join([head, *nick, *rows])
    (a, b), (to, tc), ln, m = k.ends, k.title, k.line, k.mark
    centre = k.crown if t == 6 else (f"{m}{m}" if t == 5 else m)
    top = next((v for v in (f"{a}{ln}{to} {centre} {tc}{ln}{b}", f"{to} {centre} {tc}") if fits(v)), centre)
    bottom = next((v for v in (f"{a}{ln}{to} <b>{look.tier}</b> {tc}{ln}{b}", f"{to} <b>{look.tier}</b> {tc}") if fits(v)), f"<b>{look.tier}</b>")
    shown = html.escape(cut(name, LINE_EM - 4.0 - width_em(to + tc) - 2 * width_em(k.row)))
    middle = f"{k.row}{to} {glyph} <b>{shown}</b> {tc}{k.row}"
    rows = _italic(wrap(look, html.escape(_named(look)), nested=True), (sub(look), row(look)))
    return "\n".join([top, middle, *nick, *rows, bottom])


def crest_rows(look: ChatLook) -> list[str]:
    """«🌸 Набор собран · «Сад Сакуры»»: короче фразы из каталога и делится на строку и подстроку."""
    if not look.crest:
        return []
    found = re.match(r"^(\S+) Набор «(.+)» собран$", look.crest)
    text = f"{found.group(1)} Набор собран · «{found.group(2)}»" if found else look.crest
    return wrap(look, html.escape(text))


def heading(look: ChatLook, who_html: str, suffix: str) -> str:
    """«❄️ <b>Ваш стрик</b>»: имя (уже экранированное) сокращается, чтобы строка влезла в экран."""
    name = html.unescape(who_html)
    line = f"{look.glyph} <b>{html.escape(name)} {suffix}</b>"
    while not fits(line) and name:
        name = name[:-1]
        line = f"{look.glyph} <b>{html.escape(name.rstrip())}… {suffix}</b>"
    return line


def footer(look: ChatLook) -> str | None:
    """SS — подпись образа; SSS — подпись с короной и фраза образа."""
    t = tier_step(look)
    if t < 5:
        return None
    k, name = kit(look), html.escape(look.name)
    (to, tc), (o, c), cr, m = k.title, k.sec, k.crown, k.mark
    rich = [f"{to}{o}{cr} {name} {cr}{c}{tc}", f"{to} {cr} {name} {cr} {tc}"] if t == 6 else []
    sign = next((v for v in [*rich, f"{to} {name} {tc}", f"{m} {name} {m}"] if fits(v)), name)
    return sign + (f"\n\n«{html.escape(look.phrase)}» ✨" if t == 6 and look.phrase else "")


def message(look: ChatLook, parts: list[str]) -> str:
    """Склеить шапку, разделы и подпись пустыми строками, как в образце."""
    tail = footer(look)
    return "\n\n".join([p for p in parts if p] + ([tail] if tail else []))
