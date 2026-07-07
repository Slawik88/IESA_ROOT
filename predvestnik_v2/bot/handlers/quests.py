# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
from aiogram import Router, types

from bot.filters.text_commands import TextCmd
from core.registry import DAILY_QUESTS
from core.constants import DAILY_QUEST_COMPLETE_BONUS, WEEKLY_QUEST_COMPLETE_BONUS
from services.quests import (
    get_or_assign_quests, daily_bonus_status,
    get_or_assign_weekly_quests, weekly_bonus_status,
)
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
async def cmd_quests(message: types.Message, db):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # tz_offset=None → get_or_assign_quests resolves the CHAT-local timezone,
    # the same one increment_metric uses, so assignment + progress always agree.
    quests = await get_or_assign_quests(db, user_id, chat_id)

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

        # Human-readable metric name
        metric_labels = {
            "messages_in_chat_today": "Написать сообщений",
            "pet_feeds_today": "Накормить питомца",
            "gacha_spins_today": "Крутить гачу",
            "expeditions_today": "Экспедиций",
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

    # БЛОК 5: супер-награда за закрытие ВСЕХ заданий дня
    done = sum(1 for q in quests if q.get("completed"))
    bonus = await daily_bonus_status(db, user_id, chat_id)
    bstatus = "✅ Получено!" if bonus["claimed"] else f"{done}/{len(quests)} закрыто"
    lines.append(
        f"🏆 <b>Бонус за ВСЕ дневные</b> — {bstatus}\n"
        f"   Награда: {_reward_str(DAILY_QUEST_COMPLETE_BONUS)}"
    )

    # БЛОК 5: недельные квесты (фиксированный набор, прогресс копится всю неделю)
    weekly = await get_or_assign_weekly_quests(db, user_id, chat_id)
    if weekly:
        lines.append("🗓 <b>НЕДЕЛЬНЫЕ ЗАДАНИЯ</b>")
        for q in weekly:
            progress = q.get("progress", 0.0)
            target = q.get("target", 1)
            bar = _progress_bar(progress, target)
            status = "✅" if q.get("completed") else "🔲"
            lines.append(
                f"{status} <b>{q.get('name', q.get('quest_id', '?'))}</b> — {int(progress)}/{target}\n"
                f"   [{bar}]  Награда: {_reward_str(q.get('reward', {}))}"
            )
        wdone = sum(1 for q in weekly if q.get("completed"))
        wbonus = await weekly_bonus_status(db, user_id, chat_id)
        wbstatus = "✅ Получено!" if wbonus["claimed"] else f"{wdone}/{len(weekly)} закрыто"
        lines.append(
            f"🏆 <b>Бонус за ВСЕ недельные</b> — {wbstatus}\n"
            f"   Награда: {_reward_str(WEEKLY_QUEST_COMPLETE_BONUS)}"
        )

    lines.append("\n<i>Дневные обновляются каждый день, недельные — раз в неделю. "
                 "Прогресс идёт и в чате, и на сайте.</i>")
    await message.answer("\n\n".join(lines), parse_mode="HTML")
