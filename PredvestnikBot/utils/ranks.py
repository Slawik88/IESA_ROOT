# Ранги от низшего к высшему
RANKS: dict[str, int] = {
    "user":         0,
    "moderator":    1,
    "admin_junior": 2,
    "admin_senior": 3,
    "co_owner":     4,
    "owner":        5,
    "developer":    6,
    # Обратная совместимость с данными старой БД
    "vip":          0,
    "helper":       1,
    "admin":        2,
}

RANK_NAMES: dict[str, str] = {
    "user":         "👤 Участник",
    "moderator":    "🛡 Модератор",
    "admin_junior": "⚡ Админ Младший",
    "admin_senior": "💎 Админ Старший",
    "co_owner":     "👑 Совладелец",
    "owner":        "🔱 Владелец",
    "developer":    "🛠 Разработчик",
    # Обратная совместимость
    "vip":          "👤 Участник",
    "helper":       "🛡 Модератор",
    "admin":        "⚡ Админ Младший",
}


def rank_level(rank: str) -> int:
    return RANKS.get(rank, 0)


def rank_name(rank: str, custom_title: str | None = None) -> str:
    """Return display name for rank. If custom_title is set, shows it alongside the rank badge."""
    base = RANK_NAMES.get(rank, "👤 Пользователь")
    if custom_title:
        return f"{base}  ·  {custom_title}"
    return base


def has_permission(user_rank: str, min_rank: str) -> bool:
    return rank_level(user_rank) >= rank_level(min_rank)

