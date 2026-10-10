"""Единые приёмы оформления сообщений бота (HTML-подмножество Telegram, без CSS).

Правило: событие одной строкой с эмодзи и жирным именем, подробности под ним цитатой (на телефоне она читается как отдельный блок), списки в цитате."""
from __future__ import annotations

from html import escape


def reason_quote(reason: str | None) -> str:
    """Причина санкции отдельной цитатой под строкой события; пусто, если причины нет."""
    return f"\n<blockquote>Причина: {escape(reason)}</blockquote>" if reason else ""


def quote(lines: list[str]) -> str:
    """Список строк одним блоком-цитатой."""
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"
