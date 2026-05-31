from aiogram import Router, types

from bot.filters.text_commands import TextCmd
from core.registry import DAILY_QUESTS
from services.quests import get_or_assign_quests
from services.utils import format_currency

router = Router(name="quests_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_quests"))


def _progress_bar(progress: float, target: float) -> str:
    ratio = min(1.0, progress / target) if target > 0 else 1.0
    filled = round(ratio * 5)
    return "█" * filled + "░" * (5 - filled)


def _reward_str(reward: dict) -> str:
    parts = []
    if reward.get("mora", 0) > 0:
        parts.append(f"+{format_currency(reward['mora'])} 🪙")
    if reward.get("diamonds", 0) > 0:
        parts.append(f"+{reward['diamonds']} 💎")
    for item_id, qty in reward.get("items", []):
        from core.registry import ITEMS_REGISTRY
        name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        parts.append(f"+{qty}× {name}")
    return ", ".join(parts) if parts else "—"


@router.message(TextCmd(["задания", "квесты", "дейлики"]))
async def cmd_quests(message: types.Message, db, timezone_offset: str = "+0 hours"):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Parse tz_offset from string like "+3 hours"
    try:
        tz_offset = int(timezone_offset.split()[0])
    except (ValueError, IndexError):
        tz_offset = 0

    quests = await get_or_assign_quests(db, user_id, chat_id, tz_offset)

    lines = ["📋 <b>ЕЖЕДНЕВНЫЕ ЗАДАНИЯ</b>\n"]
    for q in quests:
        quest_def = next((d for d in DAILY_QUESTS if d["id"] == q.get("quest_id", q.get("id", ""))), q)
        progress = q.get("progress", 0.0)
        target = quest_def.get("target", 1)
        completed = q.get("completed", 0)
        reward = quest_def.get("reward", {})

        bar = _progress_bar(progress, target)
        status = "✅" if completed else "🔲"
        prog_str = f"{int(progress)}/{target}"
        name = quest_def.get("id", "?")

        # Human-readable metric name
        metric_labels = {
            "messages_in_chat_today": "Написать сообщений",
            "pet_feeds_today": "Накормить питомца",
            "gacha_spins_today": "Крутить гачу",
            "expeditions_today": "Экспедиций",
            "eggs_opened_today": "Открыть яйцо",
            "warps_to_distinct_users_today": "Варпы разным игрокам",
            "auction_bids_today": "Ставка на аукцион",
            "warps_hug_distinct_today": "Обнять разных игроков",
            "rare_or_better_pet_dups_today": "Rare+ дубликатов",
            "pet_level_ups_today": "Уровень питомца поднят",
        }
        metric = quest_def.get("metric", "")
        label = metric_labels.get(metric, metric)

        lines.append(
            f"{status} <b>{label}</b> — {prog_str}\n"
            f"   [{bar}]  Награда: {_reward_str(reward)}"
        )

    lines.append("\n<i>Задания обновляются каждый день. Выполняйте действия в боте.</i>")
    await message.answer("\n\n".join(lines) if len(quests) > 1 else "\n".join(lines),
                         parse_mode="HTML")
