"""Данные для стенда админки (tools/admin_stand.py): ответы API с самыми длинными значениями, чтобы видеть переполнение на 320 px.

Добавляя вкладку в стенд, кладите сюда её ответ и допишите путь в ROUTES.
"""
from __future__ import annotations

SECTIONS = [
    {"key": "people", "title": "Игроки и чаты"}, {"key": "reports", "title": "Жалобы"}, {"key": "metrics", "title": "Метрики"},
    {"key": "journal", "title": "Журнал"}, {"key": "broadcast", "title": "Рассылка"}, {"key": "promo", "title": "Промокоды"},
    {"key": "switches", "title": "Функции"}, {"key": "settings", "title": "Настройки"}, {"key": "health", "title": "Состояние"},
]
ME = {"rank_name": "Владелец", "sections": SECTIONS, "creator": True}

_DAYS = [f"2026-10-{d:02d}" for d in range(6, 13)]
METRICS = {
    "days": 7, "since": "2026-10-06", "until": "2026-10-12", "day_list": _DAYS,
    "everyone": 12345, "players_total": 98765, "chats_total": 321, "excluded": 2,
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
    "bot": {"commands": 23456, "commands_group": 20000, "commands_private": 3456, "top_includes_staff": True, "users": 1234, "users_group": 1000, "users_private": 234,
            "daily": {d: {"users": 100 + i * 20} for i, d in enumerate(_DAYS)},
            "top": [{"command": f"команда{i}", "group": 5000 - i * 100, "private": 300, "total": 5300 - i * 100} for i in range(14)]},
    "chats": {"messages": 154321, "users": 3210, "chats": 87, "daily": {d: {"messages": 20000 + i * 900} for i, d in enumerate(_DAYS)},
              "top": [{"id": -100 - i, "title": "Очень длинное название чата для проверки переноса строк " + str(i), "messages": 9000 - i * 300, "users": 400 - i}
                      for i in range(5)]},
    "economy": {"mora": {"issued": 1234567, "spent": 987654, "net": 246913,
                         "sources": [{"title": "Награды за игры", "amount": 800000}, {"title": "Квесты", "amount": 434567}],
                         "sinks": [{"title": "Магазин", "amount": 700000}]},
                "diamonds": {"issued": 1200, "spent": 3400, "net": -2200, "sources": [], "sinks": []},
                "_staff": {"mora": {"issued": 5000, "spent": 0}}},
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

_LONG = "Очень длинное название чата для проверки переноса строк"
def _report(i, status):
    return {"id": 100 + i, "status": status, "status_title": {"new": "Новая", "in_work": "В работе", "resolved": "Нарушение", "rejected": "Отклонена"}[status],
            "created_at": "2026-10-12T09:00:00+00:00", "chat": {"title": _LONG}, "target": {"id": 500 + i, "name": "@очень_длинный_ник_нарушителя_" + str(i), "tag": "Нин Гуан/ст.адм"},
            "target_reports": 4, "reporter": None if i % 2 else {"id": 900, "name": "@жалобщик", "tag": None},
            "reason": "Оскорбления и спам ссылками " + "очень длинная причина " * 4, "message_text": "ссылка_без_пробелов_" + "x" * 90 + "\nвторая строка",
            "handled_by": {"name": "@mod"} if status in ("resolved", "rejected") else None, "handled_at": "2026-10-12T10:00:00+00:00", "note": "ок"}
REPORTS = {"counts": {"new": 3, "in_work": 1, "resolved": 12, "rejected": 5}, "can_see_reporter": False,
           "repeat": [{"id": 700 + i, "name": "@повторный_нарушитель_" + str(i), "reports": 5, "reporters": 3, "open": 1, "confirmed": 2} for i in range(2)],
           "punish": [{"key": "warn", "title": "Варн"}, {"key": "mute", "title": "Мут"}, {"key": "ban", "title": "Бан"}],
           "items": [_report(0, "new"), _report(1, "new"), _report(2, "in_work")]}
JOURNAL = {"kinds": [{"key": "ban", "title": "Баны"}, {"key": "warn", "title": "Варны"}], "actors": [{"id": 1, "username": "mod_with_long_username"}], "more": False, "next": None,
           "items": [{"title": "Бан", "text": "в чате " + _LONG, "reason": "спам " + "x" * 80, "at": "2026-10-12T09:00:00+00:00",
                      "actor": {"id": 1, "username": "mod_with_long_username", "tag": None}, "user": {"id": 500 + i, "username": "нарушитель_" + str(i), "tag": "Нин Гуан/ст.адм"},
                      "chat": {"id": -100, "title": _LONG}} for i in range(8)]}
ROUTES = {"/me": ME, "/badges": {"reports": 7}, "/metrics": METRICS, "/health": HEALTH, "/reports": REPORTS, "/journal": JOURNAL}

SETTINGS = {"transfer": [{"code": "mora", "title": "🪙 Мора", "enabled": True, "locked": False}, {"code": "zarniki", "title": "✨ Зарники", "enabled": False, "locked": True}],
            "reports": {"to_admin_chat": True, "dm_chat_rank": 4, "dm_staff_rank": 0, "reporter_min_rank": 5},
            "report_options": {"chat_ranks": [{"value": i, "title": f"Ранг {i}"} for i in range(1, 10)], "staff_ranks": [{"value": i, "title": f"Роль {i}"} for i in range(1, 7)]}}
ACCESS_OWNERS = {"enabled": False, "max_chats": 10,
                 "blocked": [{"id": 9001, "username": "очень_длинный_ник_отозванного_владельца", "reason": "спам в чатах " + "x" * 60, "at": "2026-10-12T10:00:00+00:00"}]}
ROUTES.update({"/settings": SETTINGS, "/access/owners": ACCESS_OWNERS})

# Режим владельца чата (--owner): сотрудником он не является, поэтому /me отвечает 403, а работает /owner/*.
_BAN = {"id": 777, "username": "нарушитель_с_очень_длинным_ником_" + "z" * 30, "reason": "спам " + "x" * 70, "until": None}
OWNER_CHAT = {"id": -100, "title": "Очень длинное название чата " + "я" * 40, "closed": False, "max_warnings": 3,
              "bot": {"is_admin": True, "can_moderate": False}, "members": 1284,
              "sanctions": {"bans": [_BAN, {**_BAN, "id": 778, "until": "2026-10-20T10:00:00+00:00"}],
                            "mutes": [{"id": 779, "username": "мут_" + "y" * 40, "until": "2026-10-14T10:00:00+00:00"}],
                            "warns": [{"id": 780, "username": "варн_" + "w" * 40, "count": 2}]}}
OWNER_ROUTES = {"/me": (403, {"detail": "Админка доступна только персоналу бота."}),
                "/owner/me": {"user_id": 5001, "kind": "owner", "max_chats": 10, "chat_actions": [], "member_actions": [],
                              "chats": [{"id": -100, "title": OWNER_CHAT["title"]}, {"id": -200, "title": "Второй чат"}]},
                "/owner/chat/-100": OWNER_CHAT}
