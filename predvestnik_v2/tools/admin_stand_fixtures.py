"""Данные для стенда админки (tools/admin_stand.py): ответы API с самыми длинными значениями, чтобы видеть переполнение на 320 px.

Добавляя вкладку в стенд, кладите сюда её ответ и допишите путь в ROUTES.
"""
from __future__ import annotations

SECTIONS = [
    {"key": "people", "title": "Игроки и чаты"}, {"key": "reports", "title": "Жалобы"}, {"key": "metrics", "title": "Метрики"},
    {"key": "journal", "title": "Журнал"}, {"key": "broadcast", "title": "Рассылка"}, {"key": "promo", "title": "Промокоды"},
    {"key": "switches", "title": "Функции"}, {"key": "settings", "title": "Настройки"}, {"key": "health", "title": "Состояние"},
]
ME = {"rank_name": "Владелец", "sections": SECTIONS}

_DAYS = [f"2026-10-{d:02d}" for d in range(6, 13)]
METRICS = {
    "days": 7, "since": "2026-10-06", "until": "2026-10-12", "day_list": _DAYS,
    "everyone": 12345, "players_total": 98765, "chats_total": 321,
    "compare": {"everyone": 11000, "visitors": 9000, "commands": 20000, "messages": 150000, "bot_users": 800, "chat_users": 3000},
    "retention": {"d1": {"cohort": 120, "returned": 45, "percent": 37.5}, "d7": {"cohort": 80, "returned": 20, "percent": 25.0}, "d30": {"cohort": 0}},
    "funnel": {"with_bot": 400, "with_bot_percent": 52, "steps": [
        {"key": "opened", "title": "Открыли приложение", "users": 770, "of_first": 100, "of_prev": None},
        {"key": "played", "title": "Сыграли хотя бы раз", "users": 400, "of_first": 52, "of_prev": 52},
        {"key": "spent", "title": "Потратили валюту", "users": None, "of_first": None, "of_prev": None}]},
    "site": {"visitors": 12345, "sessions": 23456, "visits": 345678, "seconds": 443940, "avg_seconds_per_visitor": 7140,
             "daily": {d: {"users": 1000 + i * 150} for i, d in enumerate(_DAYS)},
             "pages": [{"title": t, "visits": 12345 + i, "users": 9876, "seconds": 443940, "avg_seconds": 7140}
                       for i, t in enumerate(["Профиль", "Магазин", "Игры", "Питомцы", "Инвентарь"])],
             "subpages": [{"tab": f"Игры · раздел {i}", "visits": 1200 - i, "users": 300} for i in range(12)]},
    "bot": {"commands": 23456, "commands_group": 20000, "commands_private": 3456, "users": 1234, "users_group": 1000, "users_private": 234,
            "daily": {d: {"users": 100 + i * 20} for i, d in enumerate(_DAYS)},
            "top": [{"command": f"команда{i}", "group": 5000 - i * 100, "private": 300, "total": 5300 - i * 100} for i in range(14)]},
    "chats": {"messages": 154321, "users": 3210, "chats": 87, "daily": {d: {"messages": 20000 + i * 900} for i, d in enumerate(_DAYS)},
              "top": [{"id": -100 - i, "title": "Очень длинное название чата для проверки переноса строк " + str(i), "messages": 9000 - i * 300, "users": 400 - i}
                      for i in range(5)]},
    "economy": {"mora": {"issued": 1234567, "spent": 987654, "net": 246913,
                         "sources": [{"title": "Награды за игры", "amount": 800000}, {"title": "Квесты", "amount": 434567}],
                         "sinks": [{"title": "Магазин", "amount": 700000}]},
                "diamonds": {"issued": 1200, "spent": 3400, "net": -2200, "sources": [], "sinks": []}},
}
HEALTH = {
    "telegram": {"ok": True, "username": "predvestnik_bot", "ms": 142, "error": None},
    "process": {"uptime_seconds": 123 * 3600 + 59 * 60, "started_at": "2026-10-07T08:00:00+00:00", "python": "3.12.3", "commit": "463bcc9"},
    "database": {"ms": 12, "pool": {"size": 10, "idle": 7, "max": 20}},
    "errors": {"count_24h": 3, "recent": [{"text": "TimeoutError: очень длинный текст ошибки " + "x" * 120, "at": "2026-10-12T09:00:00+00:00"}]},
    "chats": {"active": 321, "left": 5, "no_rights": 12, "quiet": 40}, "players": {"total": 98765, "blocked_bot": 321},
    "queues": {"broadcasts_running": 0, "broadcasts_scheduled": 2, "reports_open": 7},
    "digest": {"enabled": True, "hour": 9, "can_edit": True},
}
ROUTES = {"/me": ME, "/badges": {"reports": 7}, "/metrics": METRICS, "/health": HEALTH}
