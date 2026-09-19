"""Canonical product-surface contract for Mini App and Telegram chat.

Business logic never belongs here.  The registry only decides which adapter a
surface must expose, so a useful chat command cannot silently regress into a
generic Web App redirect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal


ChatMode = Literal["shared_action", "chat_summary", "web_only", "retired"]


@dataclass(frozen=True)
class SurfaceSpec:
    surface_id: str
    title: str
    start_param: str
    chat_mode: ChatMode
    aliases: tuple[str, ...]


SURFACES: Final[tuple[SurfaceSpec, ...]] = (
    SurfaceSpec("shop", "🛒 Архив мастерской", "shop", "retired", ("магазин", "лавка", "шоп")),
    SurfaceSpec("daily_deal", "🏷 Архив акций", "deal", "retired", ("акция", "акция дня", "магазин дня", "ежедневный магазин")),
    SurfaceSpec("gacha", "🗃 Архив находок", "gacha", "retired", ("крутка", "гача", "гаша", "лутбокс", "пити", "pity", "мои пити")),
    SurfaceSpec("auction", "🏛 Аукцион", "auction", "web_only", ("аукцион", "аукцион выставить", "аукцион создать", "аукцион мои", "аукцион ставка")),
    SurfaceSpec("themes", "🎨 Темы профиля", "themes", "shared_action", ("темы", "тема профиля", "профиль темы")),
    SurfaceSpec("craft", "🔨 Архив крафта", "craft", "retired", ("крафт", "craft", "скрафтить", "создать предмет")),
    SurfaceSpec("relics", "🏛 Реликвии", "relics", "web_only", ("реликвии", "реликвия", "relics")),
    SurfaceSpec("exchange", "💱 Обменник", "exchange", "web_only", ("обмен", "конвертация", "обменять")),
    SurfaceSpec("crypto", "📈 Крипто-Биржа", "crypto", "web_only", ("биржа", "крипто", "crypto", "криптобиржа")),
    SurfaceSpec("game", "🎮 Центр Предвестника", "games", "web_only", ("игра", "игры", "дуэль", "дуэли", "pvp", "врата", "бездна", "битва", "бой", "арена")),
    SurfaceSpec("battle_pass", "🎫 Боевой пропуск", "bp", "web_only", ("бп", "боевой пропуск", "пропуск")),
    SurfaceSpec("quests", "📋 Квесты", "quests", "web_only", ("задания", "квесты", "дейлики")),
    SurfaceSpec("inventory", "🎒 Инвентарь", "inventory", "chat_summary", ("инвентарь", "рюкзак", "вещи", "использовать", "открыть")),
    SurfaceSpec("achievements", "🏆 Достижения", "ach", "chat_summary", ("достижения", "ачивки", "ачивменты")),
    SurfaceSpec("rhythm", "◌ Ритм", "games", "chat_summary", ("ритм",)),
    SurfaceSpec("companions", "🐾 Спутники", "zoo", "chat_summary", ("питомец", "мой питомец", "активный питомец", "зоопарк", "питомник", "питомцы", "питомци", "мои питомцы", "мои питомци")),
    SurfaceSpec("expeditions", "🗺 Поход спутника", "zoo", "chat_summary", ("поход", "походы", "экспедиция", "экспедиции", "ускорить поход")),
    SurfaceSpec("notifications", "🔔 Уведомления", "notifications", "shared_action", ("уведомления", "настройки уведомлений", "нотификации")),
    SurfaceSpec("clans", "🛡 Кланы", "clans", "chat_summary", ("клан", "кланы", "гильдия", "гильдии", "клан создать", "клан основать", "клан выйти", "клан покинуть")),
    SurfaceSpec("cosmetics", "🎨 Косметика", "cosmetics", "web_only", ("косметика", "внешний вид", "скин", "облик", "образ", "looks")),
    SurfaceSpec("legacy_units", "🗄 Архив старых отрядов", "game", "retired", ("казарма", "юниты", "юнит", "отряд", "призыв", "призыв юнита", "боевые юниты")),
)


SURFACE_BY_ID: Final = {surface.surface_id: surface for surface in SURFACES}


def surfaces_for_redirect() -> tuple[SurfaceSpec, ...]:
    return tuple(s for s in SURFACES if s.chat_mode in {"web_only", "retired"})


def surface(surface_id: str) -> SurfaceSpec:
    return SURFACE_BY_ID[surface_id]
