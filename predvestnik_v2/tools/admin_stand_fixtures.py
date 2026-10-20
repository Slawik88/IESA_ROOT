"""Данные для стенда админки (tools/admin_stand.py): ответы API с самыми длинными значениями, чтобы видеть переполнение на 320 px.

Добавляя вкладку в стенд, кладите сюда её ответ и допишите путь в ROUTES.
"""
from __future__ import annotations

import base64

SECTIONS = [
    {"key": "people", "title": "Игроки и чаты"}, {"key": "reports", "title": "Жалобы"}, {"key": "metrics", "title": "Метрики"},
    {"key": "journal", "title": "Журнал"}, {"key": "broadcast", "title": "Рассылка"}, {"key": "promo", "title": "Промокоды"},
    {"key": "switches", "title": "Функции"}, {"key": "settings", "title": "Настройки"}, {"key": "health", "title": "Состояние"},
    {"key": "access", "title": "Права"},
]
ME = {"user_id": 5000, "rank": 6, "rank_name": "Владелец", "sections": SECTIONS, "creator": True,
      "ranks": ["🌱 Младший хелпер", "💬 Хелпер", "🎓 Старший хелпер", "🛠 Разработчик", "👑 Владелец"]}

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


def _avatar(color: str, letter: str) -> str:
    """Круглая картинка-заглушка вместо фото из Telegram: стенд не ходит в Bot API."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96">'
           f'<rect width="96" height="96" rx="48" fill="{color}"/>'
           f'<text x="48" y="63" text-anchor="middle" font-family="Arial,sans-serif" font-size="44" '
           f'font-weight="700" fill="#fff">{letter}</text></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()


_AVA = [_avatar("#2563eb", "А"), _avatar("#0f766e", "Б"), _avatar("#9333ea", "В"), _avatar("#b45309", "Г")]
PEOPLE = {
    "total": 137, "offset": 0, "limit": 20, "next_offset": 20,
    "players": [
        {"id": 5000, "username": "anna_very_long_username", "name": "Анна Очень-Длинная-Фамилия", "rank_name": "🎓 Старший хелпер",
         "messages": 123456, "last": "2026-10-12T09:00:00+00:00", "avatar": _AVA[0],
         "tags": ["Нин Гуан/ст.адм", "Клан «Очень длинное название для переноса»"]},
        {"id": 5001, "username": "just_nick", "name": "", "rank_name": "", "messages": 0,
         "last": None, "avatar": _AVA[1], "tags": []},
        {"id": 5002, "username": None, "name": "Борис", "rank_name": "🌱 Младший хелпер", "messages": 42,
         "last": "2026-10-10T18:30:00+00:00", "avatar": None, "tags": ["Новичок"]},
        {"id": 5003, "username": "n" * 32, "name": "Игрок с очень длинным именем, которое не помещается в одну строку на телефоне",
         "rank_name": "", "messages": 9876543, "last": "2026-09-01T10:00:00+00:00", "avatar": _AVA[2], "tags": []},
        {"id": 5004, "username": None, "name": "", "rank_name": "🛠 Разработчик", "messages": 7,
         "last": None, "avatar": None, "tags": ["На контроле", "Баг-хантер"]},
    ],
    "chats": [
        {"id": -1001234567890, "title": _LONG + " и ещё немного", "members": 12345, "messages": 987654,
         "last": "2026-10-12T08:00:00+00:00"},
        {"id": -1009876543210, "title": "Чат без сообщений", "members": 3, "messages": 0, "last": None},
    ],
}
MARKS = {"items": [
    {"id": "bug_hunter", "title": "Баг-хантер", "glyph": "🐞"},
    {"id": "veteran", "title": "Ветеран", "glyph": "🎖"},
    {"id": "storyteller", "title": "Рассказчик", "glyph": "📖"},
    {"id": "very_long_mark", "title": "Очень длинное название регалии для проверки", "glyph": "🏅"},
]}
_MEMBER_ACTIONS = [
    {"key": "local_rank", "title": "🎖 Ранг в чате"}, {"key": "warn", "title": "⚠️ Выдать предупреждение"},
    {"key": "mute", "title": "🔇 Замутить в чате"}, {"key": "unmute", "title": "🔊 Снять мут"},
    {"key": "unwarn_all", "title": "🧽 Снять все предупреждения"}, {"key": "kick", "title": "👢 Выгнать из чата"},
    {"key": "ban", "title": "⛔ Забанить в чате"}, {"key": "unban", "title": "✅ Снять бан в чате"},
]
_PLAYER_ACTIONS = [
    {"key": "block", "title": "🙈 Бот перестанет отвечать"}, {"key": "global_ban", "title": "🚫 Забанить во всех чатах"},
    {"key": "balance", "title": "💰 Изменить баланс"}, {"key": "vip", "title": "👑 Выдать VIP"},
    {"key": "rank", "title": "🎖 Изменить роль"}, {"key": "mark_grant", "title": "🏅 Выдать метку"},
    {"key": "mark_revoke", "title": "✖️ Снять метку"}, {"key": "revoke_sessions", "title": "🔒 Завершить сессии админки"},
]
PLAYER = {
    "id": 5000, "username": "anna_very_long_username", "name": "Анна Очень-Длинная-Фамилия", "avatar": _AVA[0],
    "rank": 4, "rank_name": "🎓 Старший хелпер", "sponsor": True, "deleted_at": None,
    "balances": {"mora": 1234567, "diamonds": 1200, "zarniki": 99, "essence": 5400},
    "vip": {"until": "2026-10-27T10:00:00+00:00", "days_left": 7},
    "family": {"partner": 5001, "partner_username": "just_nick", "since": "2026-01-01T10:00:00+00:00",
               "children": 2, "parents": 2, "is_parent": True},
    "streak": {"current": 5, "best": 12}, "achievements": {"count": 3, "levels": 7},
    "messages": {"today": 42, "week": 300, "total": 12345},
    "chats": [
        {"id": -1001234567890, "title": _LONG, "messages": 12000, "last": "2026-10-12T09:00:00+00:00",
         "tag": "Нин Гуан/ст.адм", "left": False, "muted": False, "muted_until": None, "ban": None, "warns": 1,
         "rank_name": "🎓 Старший хелпер", "local_rank": 4},
        {"id": -1009876543210, "title": "Второй чат", "messages": 345, "last": "2026-10-01T10:00:00+00:00",
         "tag": None, "left": True, "muted": True, "muted_until": "2026-10-20T10:00:00+00:00",
         "ban": {"until": None}, "warns": 0, "rank_name": "👤 Игрок", "local_rank": 0},
    ],
    "global_ban": None, "blocked": None, "watch": None,
    "names": [{"kind": "username", "value": "anna_old_nick", "at": "2026-09-01T10:00:00+00:00"}],
    "tag_history": [{"tag": "Нин Гуан/ст.адм", "chat_id": -1001234567890, "chat_title": _LONG,
                     "at": "2026-10-01T10:00:00+00:00"}],
    "nicknames": [{"nickname": "Анна", "chat": {"id": -1001234567890, "title": _LONG}}],
    "marks": {"given": [{"id": "veteran", "title": "Ветеран", "glyph": "🎖", "desc": "Давно с проектом"}],
              "earned": [{"id": "storyteller", "title": "Рассказчик", "glyph": "📖", "desc": "Много историй"}],
              "grantable": [{"id": "bug_hunter", "title": "Баг-хантер", "glyph": "🐞", "desc": "Нашёл ошибку"},
                            {"id": "very_long_mark", "title": "Очень длинное название регалии", "glyph": "🏅", "desc": "Проверка переноса"}]},
    "reports": {"total": 3, "open": 1, "confirmed": 2, "last": [
        {"id": 100, "status": "new", "status_title": "Новая", "reason": "Спам ссылками",
         "chat": _LONG, "created_at": "2026-10-12T09:00:00+00:00"}]},
    "notes": {"total": 2, "next": None, "items": [
        {"id": 1, "text": "Проверяли жалобу на спам: пока не подтвердилось.", "at": "2026-10-10T10:00:00+00:00",
         "author": {"id": 1, "username": "mod_with_long_username"}, "can_remove": True},
        {"id": 2, "text": "Второй аккаунт под вопросом.", "at": "2026-10-09T10:00:00+00:00",
         "author": {"id": 2, "username": "helper"}, "can_remove": False}]},
    "linked": {"invited_by": {"id": 5001, "username": "just_nick"},
               "invited": {"total": 2, "items": [{"id": 5002, "username": None}]},
               "same_username": [{"id": 5004, "username": "anna_old_nick", "value": "anna_old_nick"}],
               "same_name": [{"id": 5003, "username": "n" * 32, "name": "Анна Очень-Длинная-Фамилия"}]},
    "history": [
        {"title": "Предупреждение", "text": "", "reason": "оффтоп", "at": "2026-10-11T10:00:00+00:00",
         "actor": {"id": 1, "username": "mod_with_long_username"}, "user": {"id": 5000, "username": "anna_very_long_username", "tag": "Нин Гуан/ст.адм"},
         "chat": {"id": -1001234567890, "title": _LONG}},
        {"title": "Баланс", "text": "🪙 +500", "reason": "конкурс", "at": "2026-10-10T10:00:00+00:00",
         "actor": {"id": 1, "username": "mod_with_long_username"}, "user": {"id": 5000, "username": "anna_very_long_username", "tag": None},
         "chat": None}],
    "actions": {"player": _PLAYER_ACTIONS, "member": _MEMBER_ACTIONS},
    "local_ranks": [{"rank": i, "name": f"Ранг {i}"} for i in range(1, 9)],
    "ranks": [{"rank": i, "name": f"Роль {i}"} for i in range(1, 6)],
    "currencies": [{"code": "mora", "title": "🪙 Мора", "decimals": 0}],
    "confirm_rules": {},
}
ATTENTION = {"items": [
    {"id": 5000, "username": "anna_very_long_username", "name": "Анна Очень-Длинная-Фамилия", "avatar": _AVA[0],
     "flag": "⛔ бан во всех чатах", "flag_kind": "bad", "note": "причина: спам ссылками", "at": "2026-10-12T09:00:00+00:00", "at_label": "забанена"},
    {"id": 5003, "username": "n" * 32, "name": "", "avatar": _AVA[2],
     "flag": "⚠️ жалоб: 3", "flag_kind": "warn", "note": "в работе: 1 · подтверждено: 2", "at": "2026-10-01T10:00:00+00:00", "at_label": "последняя жалоба"},
    {"id": 5004, "username": None, "name": "Игрок без ника", "avatar": None,
     "flag": "👁 на контроле", "flag_kind": "warn", "note": "причина: проверяем жалобы", "at": "2026-10-11T10:00:00+00:00", "at_label": "на контроле с"},
], "total": 3}
CHATS_ATTENTION = {"items": [
    {"id": -1001234567890, "title": _LONG, "members": 12345, "last": "2026-08-01T10:00:00+00:00",
     "problems": [{"key": "no_rights", "title": "у бота нет прав"}, {"key": "quiet", "title": "тихо 30 дней"}]},
    {"id": -1009876543210, "title": "Маленький чат", "members": 3, "last": None,
     "problems": [{"key": "left", "title": "бота удалили"}]},
], "total": 7}
ONBOARDING = {"days": 7, "added": 12, "ready": 7, "waiting": 3, "gave_up": 2,
              "events": [{"title": "Открыли мастер", "count": 12, "chats": 10},
                         {"title": "Выбрали чат", "count": 9, "chats": 8},
                         {"title": "Выдали права", "count": 7, "chats": 7}],
              "stuck": [{"id": -1001234567890, "title": _LONG, "reminders": 2,
                         "added_at": "2026-10-08T10:00:00+00:00", "inviter": {"id": 5000, "username": "anna_very_long_username"}}]}
def _report(i, status):
    return {"id": 100 + i, "status": status, "status_title": {"new": "Новая", "in_work": "В работе", "resolved": "Нарушение", "rejected": "Отклонена"}[status],
            "created_at": "2026-10-12T09:00:00+00:00", "chat": {"title": _LONG}, "target": {"id": 500 + i, "name": "@очень_длинный_ник_нарушителя_" + str(i), "tag": "Нин Гуан/ст.адм"},
            "target_reports": 4, "reporter": None if i % 2 else {"id": 900, "name": "@жалобщик", "tag": None},
            "reason": "Оскорбления и спам ссылками " + "очень длинная причина " * 4, "message_text": "ссылка_без_пробелов_" + "x" * 90 + "\nвторая строка",
            "handled_by": {"name": "@mod"} if status in ("resolved", "rejected") else None, "handled_at": "2026-10-12T10:00:00+00:00", "note": "ок"}
REPORTS = {"counts": {"new": 3, "in_work": 1, "resolved": 12, "rejected": 5}, "can_see_reporter": False,
           "repeat": [{"id": 700 + i, "name": "@повторный_нарушитель_" + str(i), "reports": 5, "reporters": 3, "open": 1, "confirmed": 2} for i in range(2)],
           "punish": [{"key": "warn", "title": "⚠️ Выдать предупреждение"}, {"key": "mute", "title": "🔇 Замутить в чате"}, {"key": "ban", "title": "⛔ Забанить в чате"}],
           "items": [_report(0, "new"), _report(1, "new"), _report(2, "in_work")]}
JOURNAL = {"kinds": [{"key": "ban", "title": "Баны"}, {"key": "warn", "title": "Варны"}], "actors": [{"id": 1, "username": "mod_with_long_username"}], "more": False, "next": None,
           "items": [{"title": "Бан", "text": "", "reason": "спам " + "x" * 80, "at": "2026-10-12T09:00:00+00:00",
                      "actor": {"id": 1, "username": "mod_with_long_username", "tag": None}, "user": {"id": 500 + i, "username": "нарушитель_" + str(i), "tag": "Нин Гуан/ст.адм"},
                      "chat": {"id": -100, "title": _LONG}} for i in range(8)]}
ROUTES = {"/me": ME, "/badges": {"reports": 7}, "/metrics": METRICS, "/health": HEALTH, "/reports": REPORTS, "/journal": JOURNAL,
          "/search": PEOPLE, "/marks": MARKS, "/people/attention": ATTENTION, "/chats/attention": CHATS_ATTENTION,
          "/chats/onboarding": ONBOARDING}
BROADCAST = {
    "audiences": [{"key": "players", "title": "Игроки"}, {"key": "chats", "title": "Чаты"}],
    "sizes": {"players": 98765, "chats": 321},
    "templates": [{"id": 1, "title": "Шаблон с очень длинным названием для проверки", "text": "Текст шаблона",
                   "html": False, "button": {"text": "Играть", "url": "https://t.me/predvestnik_bot"}}],
    "items": [
        {"id": 12, "audience_title": "Все игроки", "status": "done", "status_title": "Отправлена",
         "sent": 12345, "total": 12345, "failed": 5, "created_at": "2026-10-12T09:00:00+00:00", "actor": "@mod",
         "text": "Текст рассылки с очень длинной строкой без пробелов: " + "x" * 90, "html": False, "button": None},
        {"id": 13, "audience_title": "Чаты", "status": "scheduled", "status_title": "Запланирована",
         "sent": 0, "total": 321, "failed": 0, "created_at": "2026-10-12T09:00:00+00:00",
         "scheduled_at": "2026-10-20T09:00:00+00:00", "actor": "mod_with_long_username",
         "text": "Напоминание", "html": True, "button": {"text": "Открыть", "url": "https://t.me/x"}},
    ],
}
ROUTES["/broadcasts"] = BROADCAST
ROUTES["/broadcasts/preview"] = {"count": 98765, "title": "Все игроки"}
ROUTES["/player/5000"] = PLAYER
PROMO = {"items": [
    {"code": "WELCOME2026", "is_active": True, "legacy": False, "activations": 321, "max_activations": 1000,
     "rewards_text": ["🪙 500 моры", "👑 VIP на 3 дня"], "allowed_chats": [{"id": -1001234567890}],
     "valid_until": "2026-11-01T10:00:00+00:00", "valid_from": None, "show_in_app": True},
    {"code": "ОЧЕНЬ-ДЛИННЫЙ-КОД-ДЛЯ-ПРОВЕРКИ-ПЕРЕНОСА", "is_active": False, "legacy": False, "activations": 0,
     "max_activations": None, "rewards_text": [], "allowed_chats": [], "valid_until": None, "valid_from": None},
    {"code": "OLDCODE", "is_active": True, "legacy": True, "activations": 12, "max_activations": None,
     "rewards_text": ["Старый формат"], "allowed_chats": [], "valid_until": None, "valid_from": None},
]}
ROUTES["/promo"] = PROMO
SWITCHES = {
    "state": {"global": {"notice:achievements": {"reason": "чиним до вечера"}}, "chat": {}},
    "catalog": [
        {"title": "Основное", "scope": "global", "items": [
            {"key": "all", "title": "Бот целиком", "hint": "Все команды, игры и уведомления"},
            {"key": "site", "title": "Сайт", "hint": "Мини-приложение и веб-страницы"},
            {"key": "games", "title": "Игры", "hint": "Запуск игр в чатах"},
        ]},
        {"title": "Уведомления", "scope": "global", "items": [
            {"key": "notice:achievements", "title": "Достижения", "hint": "Сообщения о новых достижениях"},
            {"key": "notice:reports", "title": "Жалобы", "hint": "Уведомления о новых жалобах"},
            {"key": "notice:reports_dm", "title": "Жалобы в личку", "hint": "Только для персонала"},
        ]},
    ],
}
ROUTES["/switches"] = SWITCHES

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

_ROLES = [{"rank": r, "name": n} for r, n in ((2, "🌱 Младший хелпер"), (3, "💬 Хелпер"), (4, "🎓 Старший хелпер"), (5, "🛠 Разработчик"))]
MATRIX = {"floor": 2, "ceiling": 5, "roles": _ROLES, "items": [
    {"key": "section:people", "group": "section", "title": "Игроки и чаты", "default": 2, "current": 2, "changed": False},
    {"key": "section:metrics", "group": "section", "title": "Метрики", "default": 4, "current": 3, "changed": True},
    {"key": "action:ban", "group": "moderation", "title": "⛔ Бан в чате с очень длинным названием права " + "x" * 30, "default": 4, "current": 4, "changed": False},
    {"key": "action:warn", "group": "moderation", "title": "⚠️ Варн в чате", "default": 3, "current": 2, "changed": True}]}
ROUTES["/access/matrix"] = MATRIX
