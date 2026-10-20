"""Текст сообщений бота в стиле надетого скина: значки разделов, разделитель, орнамент, фраза SSS.

Правила (что даёт тир, откуда берутся значки) — core/skins_v3_chat.py. Без скина каждая функция возвращает то, что было
раньше, поэтому вызывающему коду не нужно проверять, есть ли образ."""
from __future__ import annotations

from html import escape

from core.skins_v3_chat import ChatLook

MESSAGES, PROGRESS, WALLET = 0, 1, 2


def icon(look: ChatLook | None, section: int, default: str) -> str:
    return look.icons[section] if look else default


def sep(look: ChatLook | None) -> str:
    """Разделитель ячеек внутри цитат: « · » или символ скина с тира B."""
    return f" {look.sep} " if look else " · "


def name_icon(look: ChatLook | None, default: str = "👤") -> str:
    return look.glyph if look else default


def head_lines(look: ChatLook | None) -> list[str]:
    """Строки под именем: титул и скин, знак собранного набора, орнамент-разделитель (с тира B)."""
    if not look:
        return []
    lines = [f"<i>{escape(look.skin_line)}</i>"]
    if look.crest:
        lines.append(f"<i>{escape(look.crest)}</i>")
    if look.divider:
        lines.append(escape(look.divider))
    return lines


def frame(look: ChatLook | None, text: str) -> str:
    """Орнамент сверху и снизу (с тира S) и фраза скина последней строкой (SSS)."""
    if not look:
        return text
    parts = [text]
    if look.frame:
        parts = [escape(look.frame), text, escape(look.frame)]
    if look.phrase:
        parts.append(f"<i>{escape(look.phrase)}</i>")
    return "\n".join(parts)
