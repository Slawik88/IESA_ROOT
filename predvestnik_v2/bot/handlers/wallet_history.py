from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.wallet_log import get_recent
from services.utils import format_currency, check_callback_owner

router = Router(name="wallet_history_router")

_SOURCE_LABELS: dict[str, str] = {
    "expedition": "🗺 Поход",
    "gacha_novice": "🎲 Гача (учен.)",
    "gacha_standard": "💫 Гача (станд.)",
    "gacha_premium": "🌟 Гача (премиум)",
    "gacha_diamond": "💎 Гача (алмаз.)",
    "gacha_drop": "🎁 Гача-дроп",
    "streak_daily": "🔥 Стрик (день)",
    "streak_block_end": "🔥 Стрик (блок)",
    "streak_recovery": "💸 Стрик (восст.)",
    "transfer_in": "💸 Перевод ↓",
    "transfer_out": "💸 Перевод ↑",
    "shop_purchase": "🛒 Магазин",
    "daily_deal_purchase": "🛒 Акция дня",
    "level_up": "⭐ Левел-ап",
    "pet_milestone": "🐾 Питомец Ур.",
    "event_chest": "💰 Сундук",
    "gamble_win": "🎲 Игра (победа)",
    "gamble_loss": "🎲 Игра (проигрыш)",
    "exchange_mora_to_dia": "💱 Обмен",
    "duel_win": "⚔️ Дуэль (победа)",
    "duel_loss": "⚔️ Дуэль (проигрыш)",
    "manual_admin": "🛠 Администратор",
    "quest_reward": "📋 Квест",
    "achievement_reward": "🏆 Достижение",
    "hamster_collect": "🐹 Хомяки (сбор)",
    "dragon_bonus": "🐉 Дракон",
    "compensation_overflow": "♻️ Компенсация",
    "auction_sale": "🏛 Аукцион (продажа)",
    "auction_buy": "🏛 Аукцион (покупка)",
    "system": "⚙️ Система",
    "spend": "💸 Списание",
    "contrabanda_stake": "🌑 Контрабанда (ставка)",
    "contrabanda_refund": "🌑 Контрабанда (возврат)",
    "cult_ritual": "🌑 Ритуал",
    "shadow_merchant": "🌑 Тенев. торговец",
}

_FILTER_LABELS = {
    "гача": "🎲 Гача",
    "переводы": "💸 Переводы",
    "магазин": "🛒 Магазин",
    "стрик": "🔥 Стрики",
    "игры": "🎲 Игры",
    "походы": "🗺 Походы",
}


class WalletCB(CallbackData, prefix="wlog"):
    action: str   # "page" | "filter"
    page: int = 1
    filter_src: str = ""
    user_id: int = 0


def _entry_line(e: dict) -> str:
    raw_ts = e.get("created_at", "")
    if hasattr(raw_ts, "strftime"):
        ts = raw_ts.strftime("%Y-%m-%d %H:%M")
    else:
        ts = str(raw_ts)[:16]
    label = _SOURCE_LABELS.get(e["source"], e["source"])

    parts = []
    dm  = e.get("delta_mora", 0.0)
    dd  = e.get("delta_diamonds", 0.0)
    dc  = e.get("delta_zarniki", 0.0)

    if dm != 0:
        sign = "+" if dm > 0 else ""
        parts.append(f"{sign}{format_currency(dm)} 🪙")
    if dd != 0:
        sign = "+" if dd > 0 else ""
        parts.append(f"{sign}{format_currency(dd)} 💎")
    if dc != 0:
        sign = "+" if dc > 0 else ""
        parts.append(f"{sign}{format_currency(dc)} ✨")

    change = " · ".join(parts) if parts else "—"
    bal = f"{format_currency(e['balance_mora_after'])} 🪙"
    note = f" <i>({e['note'][:20]})</i>" if e.get("note") else ""
    return f"<code>{ts}</code>  {label}{note}\n└ {change}  (ост: {bal})"


async def _build_text(db, user_id: int, n: int = 20, filter_src: str = "") -> str:
    bal = await eco_repo.get_balance(db, user_id)
    entries = await get_recent(db, user_id, n=n, filter_source=filter_src or None)
    filter_label = _FILTER_LABELS.get(filter_src.lower(), filter_src) if filter_src else "Все"

    lines = [
        "📜 <b>ИСТОРИЯ КОШЕЛЬКА</b>",
        f"├ Баланс: <code>{format_currency(bal['user_balance_mora'])} 🪙 · {format_currency(bal['user_balance_diamonds'])} 💎</code>",
        f"└ Фильтр: <b>{filter_label}</b>\n",
    ]
    if not entries:
        lines.append("<i>Операций пока нет.</i>")
    else:
        for e in entries:
            lines.append(_entry_line(e))
    return "\n".join(lines)


def _filter_kb(active: str = "", user_id: int = 0) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    filters = [("Все", ""), ("Гача", "гача"), ("Переводы", "переводы"),
               ("Магазин", "магазин"), ("Стрик", "стрик"), ("Игры", "игры"), ("Походы", "походы")]
    for label, src in filters:
        mark = "· " if src == active else ""
        b.button(text=f"{mark}{label}", callback_data=WalletCB(action="filter", filter_src=src, user_id=user_id))
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


@router.message(TextCmd([
    "история кошелька", "история кошелка", "кошелёк история",
    "баланс лог", "лог баланс", "лог кошелька", "лог кошелёк",
]))
async def cmd_wallet_history(message: types.Message, db, text_args: str = None):
    raw = (text_args or "").strip().lower()
    n = 20
    filter_src = ""
    if raw.isdigit():
        n = min(int(raw), 100)
    elif raw:
        filter_src = raw

    text = await _build_text(db, message.from_user.id, n=n, filter_src=filter_src)
    await message.answer(
        text,
        reply_markup=_filter_kb(filter_src, user_id=message.from_user.id),
        parse_mode="HTML",
    )


@router.callback_query(WalletCB.filter(F.action == "filter"))
async def cb_wallet_filter(query: types.CallbackQuery, callback_data: WalletCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text = await _build_text(db, query.from_user.id, n=20, filter_src=callback_data.filter_src)
    try:
        await query.message.edit_text(
            text,
            reply_markup=_filter_kb(callback_data.filter_src, user_id=callback_data.user_id),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await query.answer()


@router.message(TextCmd(["god лог", "god wallet log", "god лог кошелька"]))
async def cmd_dev_wallet_log(
    message: types.Message, db, text_args: str = None, developer_id: int = 0
):
    if message.from_user.id != developer_id:
        return

    target_id: int | None = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif text_args:
        try:
            target_id = int(text_args.strip().split()[0])
        except (ValueError, IndexError):
            pass

    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот god лог, [user_id]</code> или реплай на сообщение.",
            parse_mode="HTML",
        )

    n = 50
    if text_args:
        parts = text_args.strip().split()
        if len(parts) >= 2 and parts[1].isdigit():
            n = min(int(parts[1]), 200)

    text = await _build_text(db, target_id, n=n)
    text = f"🛠 <b>DEV: лог юзера {target_id}</b>\n\n" + text
    await message.answer(text, parse_mode="HTML")
