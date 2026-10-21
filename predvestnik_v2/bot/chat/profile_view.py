"""Вид карточки «бот я» и соседних сообщений: обычный (стиль v2) и в стиле надетого скина.

Здесь только оформление готовых данных, без базы: данные собирает bot/chat/profile.py (CardData), разметку скина
даёт core/skins_v3_chat_layout.py. Обычный вид — ровно тот, что был до скинов."""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from bot.chat.style import quote
from core import skins_v3_chat_layout as L
from core.skins_v3_chat import ChatLook


def esc(s) -> str:
    return html.escape(str(s or ""))


def pair(label: str, value: str) -> str:
    return f"{label} <b>{value}</b>"


def pair_rows(items: list[tuple[str, str]]) -> list[str]:
    """Ячейки-пары раскладываются по две в строку: «серия 18 дней · рекорд 40 дней»."""
    return [" · ".join(pair(*item) for item in items[i:i + 2]) for i in range(0, len(items), 2)]


@dataclass
class CardData:
    title: str
    username: str | None
    head: list[str] = field(default_factory=list)       # тег, роли, VIP и ID — по строке
    messages: list[tuple[str, str]] = field(default_factory=list)   # («сегодня», «12»)
    totals: list[tuple[str, str]] = field(default_factory=list)
    progress: list[tuple[str, str]] = field(default_factory=list)
    personal: list[str] = field(default_factory=list)   # свободные строки; «» — подстрока предыдущей
    wallet: list[str] = field(default_factory=list)


def plain(data: CardData) -> str:
    """Карточка без скина — ровно та, что была до скинов."""
    head = [f"👤 <b>{esc(data.title)}</b>" + (f" · @{esc(data.username)}" if data.username else ""), *data.head]
    blocks = []
    if data.messages:
        blocks.append("💬 <b>Сообщения</b>\n" + quote([" · ".join(pair(*c) for c in data.messages), " · ".join(pair(*c) for c in data.totals)]))
    if data.progress:
        blocks.append("🔥 <b>Прогресс</b>\n" + quote(pair_rows(data.progress)))
    if data.personal:
        blocks.append("\n".join(quote([line[1:]]) if line.startswith("\x00") else line for line in data.personal))
    blocks.append("💰 <b>Кошелёк</b>\n" + quote([" · ".join(data.wallet[i:i + 2]) for i in range(0, len(data.wallet), 2)]))
    return "\n\n".join(["\n".join(head), *blocks])


SHORT = {"сегодня": "день", "во всех": "везде"}   # в стиле скина строки короче: так они не переносятся на узком экране


def _cells(items: list[tuple[str, str]]) -> list[str]:
    return [pair(SHORT.get(label, label), value) for label, value in items]


def styled(data: CardData, look: ChatLook) -> str:
    """Карточка в стиле скина: шапка, разделы со строками скина, подпись SS/SSS (core/skins_v3_chat_layout.py)."""
    profile_rows = [r for line in data.head for r in L.wrap(look, line)]
    profile_rows += L.crest_rows(look)
    parts = [L.banner(look, data.title, data.username)]
    if profile_rows:
        parts.append(L.section(look, look.glyph, "Профиль", profile_rows))
    if data.messages:
        parts.append(L.section(look, look.icons[0], "Сообщения", L.pack(look, _cells(data.messages + data.totals))))
    if data.progress:
        parts.append(L.section(look, look.icons[1], "Прогресс", L.pack(look, _cells(data.progress))))
    if data.personal:
        rows = []
        for line in data.personal:
            rows += L.wrap(look, line[1:], nested=True) if line.startswith("\x00") else L.wrap(look, line)
        parts.append(L.section(look, "📅", "В чате", rows))
    parts.append(L.section(look, look.icons[2], "Кошелёк", L.pack(look, data.wallet)))
    return L.message(look, parts)


def balance(look: ChatLook, lines: list[str]) -> str:
    """«бот баланс» в стиле скина: строки баланса — раздел «Кошелёк»."""
    return L.message(look, [f"{look.glyph} <b>Баланс</b>", L.section(look, look.icons[2], "Кошелёк", [r for x in lines for r in L.wrap(look, x)])])


def streak(look: ChatLook, who: str, current: int, best: int, status: str) -> str:
    """«бот стрик» в стиле скина."""
    rows = [L.row(look) + f"🔥 сейчас <b>{current}</b>", L.row(look) + f"🏅 лучший <b>{best}</b>", *L.wrap(look, status)]
    return L.message(look, [L.heading(look, who, "стрик"), L.section(look, look.icons[1], "Серия", rows),
                            "<i>Серия и график учитывают активность во всех чатах.</i>"])


def achievements(look: ChatLook, who: str, items: list[tuple[str, str, str]], total: int, total_max: int, footnote: str) -> str:
    """«бот достижения» в стиле скина: раздел на группу; items — (группа, строка с именем, строка прогресса)."""
    groups: dict[str, list[str]] = {}
    for group, head, progress in items:
        groups.setdefault(group, []).extend(L.wrap(look, head) + L.wrap(look, progress, nested=True))
    parts = [f"{L.heading(look, who, 'достижения')}\n{L.row(look)}уровней: <b>{total}</b> из {total_max}"]
    parts += [L.section(look, "🏆", title, rows) for title, rows in groups.items()]
    return L.message(look, [*parts, footnote])
