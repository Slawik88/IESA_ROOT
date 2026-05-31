# services/roles.py
# Pure rank-hierarchy and permission logic. No config or platform imports.

GLOBAL_RANKS_MAP: dict[int, str] = {
    0: "👤 Пользователь",
    1: "🛡 Хелпер",
    2: "⚔️ Старший хелпер",
    3: "🌌 Главный разработчик",
}
DEVELOPER_GLOBAL_RANK: int = 3  # auto-assigned rank; cannot be manually given to others

LOCAL_RANKS_MAP: dict[int, str] = {
    0: "👤 Пользователь",
    1: "👁 Модератор",
    2: "👮‍♂️ Младший админ",
    3: "👮‍♂️ Админ",
    4: "🕵️‍♂️ Старший админ",
    5: "👑 Совладелец",
    6: "👑 Владелец",
}

_DEV_LABEL = "🌌 Главный разработчик"

def get_global_rank_name(user_id: int, rank_id: int, developer_id: int = 0) -> str:
    if developer_id and user_id == developer_id:
        return _DEV_LABEL
    return GLOBAL_RANKS_MAP.get(rank_id, "👤 Пользователь")

def get_local_rank_name(user_id: int, rank_id: int, developer_id: int = 0) -> str:
    if developer_id and user_id == developer_id:
        return _DEV_LABEL
    return LOCAL_RANKS_MAP.get(rank_id, "👤 Пользователь")

def can_assign_local_rank(
    admin_id: int,
    admin_local_rank: int,
    target_current_rank: int,
    target_new_rank: int,
    developer_id: int = 0,
) -> tuple[bool, str]:
    if developer_id and admin_id == developer_id:
        return True, ""
    if admin_local_rank < 1:
        return False, "❌ <b>Отказано:</b> У вас нет административных прав для выдачи ролей."
    if target_current_rank >= admin_local_rank:
        return False, "⚠️ <b>Отказано:</b> Вы не можете изменять ранг пользователя, чей статус равен вашему или выше."
    if target_new_rank >= admin_local_rank:
        return False, "⚠️ <b>Отказано:</b> Вы не можете выдать ранг, равный или превышающий ваш собственный."
    return True, ""

def can_confirm_rank(admin_id: int, admin_local_rank: int, developer_id: int = 0) -> bool:
    if developer_id and admin_id == developer_id:
        return True
    return admin_local_rank >= 5


def get_global_ranks_list_text() -> str:
    lines = [f"├ <code>{rid}</code> — {name}" for rid, name in GLOBAL_RANKS_MAP.items()]
    if lines:
        lines[-1] = lines[-1].replace("├", "└")
    return "\n".join(lines)


def get_local_ranks_list_text() -> str:
    lines = [f"├ <code>{rid}</code> — {name}" for rid, name in LOCAL_RANKS_MAP.items()]
    if lines:
        lines[-1] = lines[-1].replace("├", "└")
    return "\n".join(lines)