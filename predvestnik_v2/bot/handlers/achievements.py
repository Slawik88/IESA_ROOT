# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
from aiogram import Router, types
from bot.filters.text_commands import TextCmd
from core.registry import ACHIEVEMENTS, ACHIEVEMENT_LEVEL_REWARDS
from infrastructure.repositories.achievements import get_all_achievements
from infrastructure.repositories import users as users_repo
from bot.keyboards.cta import answer_group_only

router = Router(name="achievements_router")

_MAX_PER_PAGE = 8


def _progress_bar(progress: float, thresholds: list, level: int) -> str:
    if level >= 10:
        return "██████ MAX"
    target = thresholds[level]
    ratio = min(1.0, progress / target) if target > 0 else 1.0
    filled = round(ratio * 5)
    return "█" * filled + "░" * (5 - filled)


def _next_reward_str(level: int) -> str:
    if level >= 10:
        return "МАКСИМУМ"
    reward = ACHIEVEMENT_LEVEL_REWARDS.get(level + 1, {})
    parts = []
    if reward.get("mora", 0) > 0:
        parts.append(f"+{int(reward['mora'])} 🪙")
    if reward.get("diamonds", 0) > 0:
        parts.append(f"+{reward['diamonds']} 💎")
    for iid, qty in reward.get("items", ()):
        parts.append(f"+{qty}× {iid}")
    return ", ".join(parts) if parts else "—"


@router.message(TextCmd(["достижения", "ачивки", "ачивменты"]))
async def cmd_achievements(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)

    user_id = message.from_user.id
    user_data = await get_all_achievements(db, user_id)

    from infrastructure.repositories.achievements import upsert_achievement

    # Sync "talker" with real message count
    global_msgs = await users_repo.get_messages_global(db, user_id)
    if global_msgs["all_time"] > 0:
        talker = user_data.get("talker", {"level": 0, "progress": 0})
        new_prog = max(talker["progress"], float(global_msgs["all_time"]))
        thresholds = ACHIEVEMENTS["talker"]["thresholds"]
        new_level = talker["level"]
        while new_level < 10 and new_prog >= thresholds[new_level]:
            new_level += 1
        if new_prog != talker["progress"] or new_level != talker["level"]:
            await upsert_achievement(db, user_id, "talker", new_level, new_prog)
            await db.commit()
            user_data["talker"] = {"level": new_level, "progress": new_prog}

    # Sync "persistent" with real MAX streak across all chats
    async with db.execute(
        "SELECT MAX(streak) FROM daily_login WHERE user_id = ?", (user_id,)
    ) as _sc:
        _srow = await _sc.fetchone()
    real_max_streak = float(_srow[0]) if _srow and _srow[0] else 0.0
    if real_max_streak > 0:
        persistent = user_data.get("persistent", {"level": 0, "progress": 0.0})
        new_prog = max(persistent["progress"], real_max_streak)
        thresholds = ACHIEVEMENTS["persistent"]["thresholds"]
        new_level = persistent["level"]
        while new_level < 10 and new_prog >= thresholds[new_level]:
            new_level += 1
        if new_prog != persistent["progress"] or new_level != persistent["level"]:
            await upsert_achievement(db, user_id, "persistent", new_level, new_prog)
            await db.commit()
            user_data["persistent"] = {"level": new_level, "progress": new_prog}

    total_unlocked = sum(1 for d in user_data.values() if d["level"] > 0)
    total_max = sum(1 for d in user_data.values() if d["level"] >= 10)

    lines = [
        "🏆 <b>МОИ ДОСТИЖЕНИЯ</b>\n",
        f"└ Открыто: <b>{total_unlocked}/{len(ACHIEVEMENTS)}</b> · Максимум: <b>{total_max}</b>\n",
    ]

    for ach_id, ach in ACHIEVEMENTS.items():
        data = user_data.get(ach_id, {"level": 0, "progress": 0.0})
        level = data["level"]
        progress = data["progress"]
        thresholds = ach["thresholds"]

        bar = _progress_bar(progress, thresholds, level)
        if level >= 10:
            progress_str = "MAX"
        else:
            target = thresholds[level]
            progress_str = f"{int(progress)}/{int(target)}"

        reward_str = _next_reward_str(level)

        lines.append(
            f"{ach['icon']} <b>{ach['name']}</b> — Ур.{level}/10\n"
            f"   [{bar}] {progress_str}"
            + (f"\n   └ след. награда: <i>{reward_str}</i>" if level < 10 else "")
        )

    await message.answer("\n\n".join(lines), parse_mode="HTML")
