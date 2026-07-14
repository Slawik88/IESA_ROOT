# core/admin_permissions.py
# Реестр админ-функций для гибкой настройки прав глобальных рангов (БЛОК 21.2, W-права).
# Без внешних зависимостей (правило core/).
#
# Модель:
#   - Ранг 3 (Главный разработчик) ВСЕГДА имеет все права; его набор не настраивается.
#   - Ранги 1–2 по умолчанию получают права, у которых default <= их ранг.
#   - Дефолт можно перекрыть записью в global_rank_permissions (allowed TRUE/FALSE).
#   - locked=True — право нельзя выдать рангам 1–2 вообще (SQL-консоль, управление штатом):
#     цена ошибки — целостность БД / сама система прав.
#   - Снятие санкции требует того же права, что и выдача её типа (симметрия, антипир сверху).

ADMIN_PERMISSIONS: dict[str, dict] = {
    # ── 🚨 Санкции ────────────────────────────────────────────────────────────
    "sanction_warn_user":     {"label": "⚠️ Варн игроку",             "group": "🚨 Санкции", "default": 1},
    "sanction_restrict_user": {"label": "🔇 Ограничение игроку",      "group": "🚨 Санкции", "default": 2},
    "sanction_ban_user":      {"label": "🚫 Бан игроку",              "group": "🚨 Санкции", "default": 3},
    "sanction_warn_chat":     {"label": "⚠️ Варн чату",               "group": "🚨 Санкции", "default": 2},
    "sanction_restrict_chat": {"label": "🔇 Ограничение чату",        "group": "🚨 Санкции", "default": 2},
    "sanction_ban_chat":      {"label": "🚫 Бан чату",                "group": "🚨 Санкции", "default": 3},

    # ── 📨 Апелляции ──────────────────────────────────────────────────────────
    "appeals_view":    {"label": "📨 Видеть апелляции и диалоги",     "group": "📨 Апелляции", "default": 1},
    "appeals_reply":   {"label": "💬 Отвечать в апелляциях",          "group": "📨 Апелляции", "default": 1},
    "appeals_resolve": {"label": "⚖️ Принимать/отклонять апелляции",  "group": "📨 Апелляции", "default": 1},
    "appeals_close":   {"label": "📪 Закрывать дела",                 "group": "📨 Апелляции", "default": 1},

    # ── 🌐 Сеть чатов ─────────────────────────────────────────────────────────
    "members_view":    {"label": "👥 Списки чатов и участников",      "group": "🌐 Сеть чатов", "default": 1},
    "sanctions_view":  {"label": "🚫 Вкладка «Ограничения»",          "group": "🌐 Сеть чатов", "default": 1},
    "log_view":        {"label": "📋 Глобальный журнал санкций",      "group": "🌐 Сеть чатов", "default": 1},
    "chats_view_all":  {"label": "🌐 Видеть ВСЕ чаты бота",           "group": "🌐 Сеть чатов", "default": 3},

    # ── 👤 Игроки и досье ─────────────────────────────────────────────────────
    "dossier_view":           {"label": "🔎 Центр игрока (досье)",            "group": "👤 Игроки и досье", "default": 3},
    "user_search":            {"label": "🔍 Глобальный поиск игроков",        "group": "👤 Игроки и досье", "default": 3},
    "local_actions_any_chat": {"label": "⚡ Локальные варн/мут/кик в любом чате (как Ст.Адм)",
                               "group": "👤 Игроки и досье", "default": 3},

    # ── 💰 Экономика ──────────────────────────────────────────────────────────
    "economy_balance": {"label": "💰 Править балансы игроков",        "group": "💰 Экономика", "default": 3},
    "economy_items":   {"label": "🎁 Выдавать/забирать предметы",     "group": "💰 Экономика", "default": 3},
    "economy_vip":     {"label": "👑 Управлять VIP",                  "group": "💰 Экономика", "default": 3},
    "promo_manage":    {"label": "🎟 Промокоды (CRUD)",               "group": "💰 Экономика", "default": 3},
    "log_admin_view":  {"label": "📜 Журнал выдач консоли",           "group": "💰 Экономика", "default": 3},

    # ── 🎫 Контент ────────────────────────────────────────────────────────────
    "bp_manage":     {"label": "🎫 Боевой пропуск (сезоны/награды/XP)", "group": "🎫 Контент", "default": 3},
    "themes_manage": {"label": "🎨 Theme Lab и метаданные тем",         "group": "🎫 Контент", "default": 3},

    # ── 🖥 Система ────────────────────────────────────────────────────────────
    "console_overview": {"label": "📊 Сводка «Система» (цифры проекта)", "group": "🖥 Система", "default": 3},
    "metrics_view":     {"label": "📈 Метрики посещаемости",             "group": "🖥 Система", "default": 3},
    "flags_manage":     {"label": "🔌 Глобальные флаги модулей",         "group": "🖥 Система", "default": 3},
    "modules_manage":   {"label": "🧩 Модули конкретного чата",          "group": "🖥 Система", "default": 3},
    "broadcast_send":   {"label": "📢 Рассылка по чатам/ЛС",             "group": "🖥 Система", "default": 3},
    "sql_run":          {"label": "🖥 SQL-консоль",                      "group": "🖥 Система", "default": 3, "locked": True},
    "staff_manage":     {"label": "👮 Штат и настройка прав",            "group": "🖥 Система", "default": 3, "locked": True},
}

# Порядок групп для UI (реестр — единственный источник правды).
PERMISSION_GROUPS: list[str] = [
    "🚨 Санкции", "📨 Апелляции", "🌐 Сеть чатов",
    "👤 Игроки и досье", "💰 Экономика", "🎫 Контент", "🖥 Система",
]


def default_perms_for_rank(rank: int) -> set[str]:
    """Дефолтный набор прав ранга без учёта БД-оверрайдов. Ранг 3 — всё."""
    if rank >= 3:
        return set(ADMIN_PERMISSIONS)
    if rank < 1:
        return set()
    return {k for k, meta in ADMIN_PERMISSIONS.items()
            if meta["default"] <= rank and not meta.get("locked")}
