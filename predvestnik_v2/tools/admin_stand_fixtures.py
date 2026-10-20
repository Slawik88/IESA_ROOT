"""Данные для стенда админки (tools/admin_stand.py): ответы API с самыми длинными значениями, чтобы видеть переполнение на 320 px.

Добавляя вкладку в стенд, кладите сюда её ответ и допишите путь в ROUTES.
"""
from __future__ import annotations

SECTIONS = [
    {"key": "people", "title": "Игроки и чаты"}, {"key": "reports", "title": "Жалобы"}, {"key": "metrics", "title": "Метрики"},
    {"key": "journal", "title": "Журнал"}, {"key": "broadcast", "title": "Рассылка"}, {"key": "promo", "title": "Промокоды"},
    {"key": "switches", "title": "Функции"}, {"key": "settings", "title": "Настройки"}, {"key": "health", "title": "Состояние"},
    {"key": "access", "title": "Права"},
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

_ROLES = [{"rank": r, "name": n} for r, n in ((2, "🌱 Младший хелпер"), (3, "💬 Хелпер"), (4, "🎓 Старший хелпер"), (5, "🛠 Разработчик"))]
MATRIX = {"floor": 2, "ceiling": 5, "roles": _ROLES, "items": [
    {"key": "section:people", "group": "section", "title": "Игроки и чаты", "default": 2, "current": 2, "changed": False},
    {"key": "section:metrics", "group": "section", "title": "Метрики", "default": 4, "current": 3, "changed": True},
    {"key": "action:ban", "group": "moderation", "title": "⛔ Бан в чате с очень длинным названием права " + "x" * 30, "default": 4, "current": 4, "changed": False},
    {"key": "action:warn", "group": "moderation", "title": "⚠️ Варн в чате", "default": 3, "current": 2, "changed": True}]}
ROUTES["/access/matrix"] = MATRIX

# ── Админка 3.0: остальные экраны (главная, люди, чат, рассылка, промокоды, функции, журнал входов, владелец) ──
_AV = None   # фото в стенде нет: проверяется цветной кружок с инициалом
_P = lambda i, name="", u=None: {"id": i, "name": name, "username": u, "avatar": _AV}
SEARCH = {"players": [{**_P(500 + i, "Очень длинное имя игрока номер " + str(i), "nick_" + "q" * (i * 4)), "rank_name": "💬 Хелпер" if i == 1 else "",
                       "messages": 12345 * i, "last": "2026-10-12T09:00:00+00:00", "tags": ["Нин Гуан/ст.адм"] if i % 2 else []} for i in range(6)],
          "chats": [{"id": -100 - i, "title": _LONG + " " + str(i), "members": 1284 - i, "messages": 99999, "last": "2026-10-12T09:00:00+00:00"} for i in range(3)]}
_MEMBER = [{"key": k, "title": t} for k, t in (("local_rank", "🎖 Ранг в чате"), ("warn", "⚠️ Выдать предупреждение"), ("mute", "🔇 Замутить в чате"), ("unmute", "🔊 Снять мут"),
                                               ("kick", "👢 Выгнать из чата"), ("ban", "⛔ Забанить в чате"), ("unban", "✅ Снять бан в чате"), ("unwarn_all", "🧽 Снять все предупреждения"))]
_PLAYER_ACTS = [{"key": k, "title": t} for k, t in (("global_ban", "🚫 Забанить во всех чатах"), ("global_unban", "✅ Снять бан во всех чатах"), ("block", "🙈 Бот не отвечает"),
                                                    ("unblock", "🙉 Бот снова отвечает"), ("balance", "💰 Изменить баланс"), ("vip", "👑 Выдать VIP"), ("rank", "🎖 Изменить роль"),
                                                    ("revoke_sessions", "🔒 Завершить сессии админки"), ("mark_grant", "🏅 Выдать метку"), ("mark_revoke", "✖️ Снять метку"))]
_MARK = lambda i, g, t: {"id": i, "glyph": g, "title": t, "desc": "Описание регалии " + t}
PLAYER = {**_P(500, "Очень длинное имя игрока для проверки переноса", "очень_длинный_ник_игрока"), "rank": 0, "rank_name": "Игрок", "vip": {"days_left": 12}, "sponsor": False,
          "blocked": None, "global_ban": {"reason": "спам во всех чатах " + "x" * 40}, "deleted_at": None,
          "watch": {"reason": "подозрение на мультиаккаунт", "by": {"id": 1, "username": "mod"}, "at": "2026-10-11T09:00:00+00:00"},
          "balances": {"mora": 1234567, "diamonds": 12.5, "essence": 300, "zarniki": 99999}, "messages": {"today": 12, "week": 345, "total": 123456},
          "streak": {"current": 5, "best": 40}, "achievements": {"count": 17, "levels": 30}, "family": {"partner": 501, "partner_username": "партнёр", "since": "2026-01-01", "children": 2},
          "chats": [{"id": -100 - i, "title": _LONG + " " + str(i), "rank_name": "Участник", "local_rank": 1, "messages": 3000 - i, "last": "2026-10-12T09:00:00+00:00",
                     "tag": "Нин Гуан/ст.адм" if i == 0 else None, "left": i == 2, "muted": i == 0, "muted_until": "2026-10-25T10:00:00+00:00",
                     "ban": {"until": None} if i == 1 else None, "warns": 2 if i == 0 else 0} for i in range(3)],
          "reports": {"total": 4, "open": 1, "confirmed": 2, "last": [{"id": 100 + i, "status": ["new", "resolved"][i % 2], "status_title": ["Новая", "Нарушение"][i % 2],
                                                                      "reason": "Оскорбления " + "длинно " * 5, "created_at": "2026-10-12T09:00:00+00:00", "chat": _LONG} for i in range(3)]},
          "notes": {"total": 3, "next": 2, "items": [{"id": i, "text": "Заметка модератора " + "текст " * 12, "at": "2026-10-12T09:00:00+00:00", "author": _P(1, "", "mod"), "can_remove": True} for i in range(2)]},
          "names": [{"kind": "username", "value": "старый_ник", "at": "2026-01-01T00:00:00+00:00"}], "nicknames": [{"chat": {"id": -100, "title": _LONG}, "nickname": "Ник в чате"}],
          "tag_history": [{"tag": "Нин Гуан", "chat_id": -100, "chat_title": _LONG, "at": "2026-10-01T00:00:00+00:00"}],
          "linked": {"invited_by": _P(502, "", "пригласивший"), "invited": {"total": 3, "items": [_P(503, "", "друг")]}, "same_username": [], "same_name": [{**_P(504, "Тёзка"), "name": "Тёзка"}]},
          "history": JOURNAL["items"][:4],
          "marks": {"given": [_MARK("helper", "🛡", "Помощник")], "earned": [_MARK("cart", "🗺", "Картограф")], "grantable": [_MARK("helper", "🛡", "Помощник"), _MARK("artist", "🎨", "Художник")]},
          "actions": {"player": _PLAYER_ACTS, "member": _MEMBER}, "confirm_rules": {"actions": ["global_ban", "rank"], "balance": {"mora": 100000}},
          "currencies": [{"code": "mora", "title": "🪙 Мора"}, {"code": "diamonds", "title": "💎 Алмазы"}],
          "ranks": [{"rank": 0, "name": "Игрок"}, {"rank": 2, "name": "🌱 Младший хелпер"}], "local_ranks": [{"rank": 1, "name": "Участник"}, {"rank": 3, "name": "Модератор"}]}
_SANC = lambda n: {"total": n, "next": 5 if n > 5 else None, "items": [{"user": 600 + i, "username": "нарушитель_" + "n" * 20 + str(i), "tag": None, "until": None, "reason": "спам", "count": 2} for i in range(min(n, 5))]}
CHAT = {"id": -100, "title": _LONG, "closed": False, "warn_limit": 3, "members": 1284, "tagged": 12, "bot": {"can_moderate": False}, "owner": _P(505, "", "владелец"),
        "admin_chat": {"id": -200, "title": "Админ-чат"}, "switched_off": [{"title": "Мафия", "reason": "чиним"}],
        "messages": {"total": 999999, "today": {"messages": 120, "active": 30}, "week": {"messages": 1200, "active": 90}, "month": {"messages": 5000, "active": 200}},
        "actions": {"chat": [{"key": "message", "title": "📣 Написать от бота"}, {"key": "close", "title": "🔒 Закрыть чат"}, {"key": "open", "title": "🔓 Открыть чат"},
                             {"key": "warn_limit", "title": "⚠️ Лимит предупреждений"}, {"key": "leave", "title": "🚪 Бот выйдет из чата"}], "member": _MEMBER},
        "sanctions": {"bans": _SANC(7), "mutes": _SANC(1), "warns": _SANC(0)},
        "top": [{"id": 600 + i, "username": "активный_" + str(i), "tag": None, "messages": 900 - i} for i in range(5)], "history": JOURNAL["items"][:3],
        "settings": {"ranks": [{"key": "rank_ban", "title": "Бан", "rank": 3, "name": "Модератор"}], "purge": {"on": True, "min_rank": "Модератор", "action_rank": "Старший"},
                     "shield_days": 3, "modules": [{"icon": "🎭", "name": "Мафия", "on": False}, {"icon": "🐾", "name": "Питомцы", "on": True}], "flags": [{"title": "Приветствие", "on": True}]},
        "can_edit_rights": True, "rank_rights": {"actions": [{"key": "ban", "title": "Бан", "default": 3}], "ranks": [{"rank": 1, "name": "Участник"}, {"rank": 3, "name": "Модератор"}], "values": {"ban": 3}}}
ATTN_PEOPLE = {"items": [{**_P(700, "Нарушитель Длинноимённый", "bad_guy"), "flag": "⛔ бан везде", "flag_kind": "bad", "note": "спам", "at": "2026-10-12T09:00:00+00:00", "at_label": "с"},
                         {**_P(701, "", "watch_me"), "flag": "👁 на контроле", "flag_kind": "warn", "note": None, "at": None}], "total": 2}
ATTN_CHATS = {"total": 5, "items": [{"id": -100 - i, "title": _LONG, "members": 50, "last": None, "problems": [{"key": "no_rights", "title": "бот без прав"}]} for i in range(5)]}
ONBOARDING = {"days": 7, "added": 5, "ready": 3, "waiting": 1, "gave_up": 1, "events": [{"title": "Нажали «Выдать права»", "count": 9, "chats": 4}], "stuck": []}
BROADCASTS = {"audiences": [{"key": "players", "title": "Игрокам в личку"}, {"key": "chats", "title": "В чаты"}], "sizes": {"players": 12345, "chats": 321},
              "templates": [{"id": 1, "title": "Новости недели", "text": "<b>Новости</b>", "html": True, "button": None}],
              "items": [{"id": 9, "status": "running", "status_title": "Идёт", "audience_title": "Игрокам в личку · все", "text": "Текст рассылки " * 20, "html": False, "button": {"text": "Играть", "url": "https://t.me/x"},
                         "sent": 500, "failed": 12, "total": 1200, "created_at": "2026-10-12T09:00:00+00:00", "actor": "@mod"},
                        {"id": 8, "status": "scheduled", "status_title": "Запланирована", "audience_title": "В чаты", "text": "Позже", "html": False, "button": None,
                         "sent": 0, "failed": 0, "total": 0, "created_at": "2026-10-12T09:00:00+00:00", "scheduled_at": "2026-10-30T09:00:00+00:00", "actor": "@mod"}]}
PROMO_ITEMS = {"items": [{"code": "AUTUMN2026LONGCODE", "is_active": True, "legacy": False, "valid_from": None, "valid_until": "2026-12-01T00:00:00+00:00", "max_activations": 100,
                          "activations": 64, "allowed_chats": [], "rewards_text": ["🪙 1 000 мора", "👑 7 дн. VIP"]}, {"code": "OFF", "is_active": False, "legacy": False, "max_activations": 0,
                          "activations": 3, "allowed_chats": [-100], "rewards_text": []}]}
PROMO = {**PROMO_ITEMS["items"][0], "note": "Для конкурса в канале", "rewards": [{"type": "mora", "amount": 1000}], "chats": [], "allowed_users": [], "show_in_app": True, "warnings": ["Лимит большой для такой награды"],
         "stats": {"activations": 64, "limit": 100, "left": 36, "chats": 3, "private": 10, "first_at": "2026-10-01T00:00:00+00:00", "last_at": "2026-10-12T00:00:00+00:00",
                   "spent": {"mora": 64000}, "per_day": [{"day": f"2026-10-{d:02d}", "n": d % 5} for d in range(1, 15)]},
         "redemptions": [{"user_id": 500 + i, "username": "игрок_" + str(i), "chat_id": -100 if i % 2 else None, "chat_title": _LONG, "at": "2026-10-12T09:00:00+00:00", "granted": ["1 000 мора"]} for i in range(4)]}
PROMO_OPTIONS = {"rewards": [{"type": "mora", "title": "🪙 Мора", "field": "amount"}, {"type": "skin", "title": "🎭 Образ", "field": "id"}], "skins": [], "private_skins": []}
SWITCHES = {"state": {"global": {"mafia": {"reason": "чиним"}}, "chat": {}}, "catalog": [
    {"title": "Чат-бот", "scope": "bot", "items": [{"key": "all", "title": "Весь бот", "hint": "Бот молчит на все команды"},
                                                  {"key": "games", "title": "Игры", "hint": "Весь раздел", "items": [{"key": "mafia", "title": "Мафия", "hint": "Игра в мафию"}, {"key": "rhythm", "title": "Ритм", "hint": ""}]}]},
    {"title": "Сайт", "scope": "site", "items": [{"key": "site", "title": "Весь сайт", "hint": "Мини-приложение отвечает «временно закрыто»"}]}]}
LOGINS = {"items": [{"user": _P(1, "", "mod_with_long_username"), "device": "Android · Telegram", "ip": "203.0.113.5", "at": "2026-10-12T09:00:00+00:00"}]}
ROUTES.update({"/search": SEARCH, "/player/500": PLAYER, "/chat/-100": CHAT, "/people/attention": ATTN_PEOPLE, "/chats/attention": ATTN_CHATS, "/chats/onboarding": ONBOARDING,
               "/marks": {"items": [_MARK("helper", "🛡", "Помощник")]}, "/broadcasts": BROADCASTS, "/broadcasts/preview": {"count": 12345, "title": "Все игроки"},
               "/promo": PROMO_ITEMS, "/promo/AUTUMN2026LONGCODE": PROMO, "/promo-options": PROMO_OPTIONS, "/switches": SWITCHES, "/logins": LOGINS})
OWNER_ROUTES["/owner/chat/-100/members"] = {"items": [{**_P(800, "Участник Чата", "member_one"), "messages": 120, "last": "2026-10-12T09:00:00+00:00"}]}

# Волна 2: значки состояния в поиске (кольцо вокруг лица и иконки справа) — разные сочетания.
_FLAGS = [{"vip": False, "global_ban": True, "bans": 0, "warns": 0, "muted": False, "blocked": False, "watch": True},
          {"vip": False, "global_ban": False, "bans": 0, "warns": 3, "muted": True, "blocked": False, "watch": False},
          {"vip": True, "global_ban": False, "bans": 0, "warns": 0, "muted": False, "blocked": False, "watch": False},
          {"vip": True, "global_ban": False, "bans": 2, "warns": 1, "muted": True, "blocked": True, "watch": True}]
for _i, _p in enumerate(SEARCH["players"][:4]):
    _p["flags"] = _FLAGS[_i]
SEARCH["players"][5]["last"] = "2099-01-01T00:00:00+00:00"[:0] or None   # «не писал»
