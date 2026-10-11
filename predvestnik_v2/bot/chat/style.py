"""Единые приёмы оформления сообщений бота (HTML-подмножество Telegram, без CSS).

Правило: событие одной строкой с эмодзи и жирным именем, подробности под ним цитатой (на телефоне она читается как отдельный блок), списки в цитате."""
from __future__ import annotations

from html import escape


def reason_quote(reason: str | None) -> str:
    """Причина санкции отдельной цитатой под строкой события; пусто, если причины нет."""
    return f"\n<blockquote>Причина: {escape(reason)}</blockquote>" if reason else ""


def profile_link(user_id: int, username: str | None, tag: str | None = None) -> str:
    """Игрок в списке: ник ссылкой на профиль в Telegram, после него тег `[Сяо]`. Тег приходит уже очищенным, здесь он экранируется.

    Для ника ссылка t.me/<ник>: она открывает профиль и никого не пингует, в отличие от tg://user?id=. Без ника другого пути нет,
    остаётся tg://user?id (такие игроки в списках редки)."""
    if username:
        name = f'<a href="https://t.me/{escape(username, quote=True)}">@{escape(username)}</a>'
    else:
        name = f'<a href="tg://user?id={int(user_id)}">id{int(user_id)}</a>'
    return name + (f" [{escape(tag)}]" if tag else "")


def quote(lines: list[str]) -> str:
    """Список строк одним блоком-цитатой."""
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"
