"""
Система Молитв (Гача).

Команды:
  бот молитва / бот помолиться   — крутка гачи (x1 за 120 🪙, x10 за 1000 🪙; холостяки: 110/950)
  бот инвентарь / бот предметы   — список полученных предметов
  бот продать мусор              — продать весь junk (по 5 🪙 за штуку)
  бот экипировать <id>           — экипировать лего-предмет для профиля
"""

import html
import random
from datetime import datetime

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import GACHA_SINGLE_PRICE, GACHA_MULTI_PRICE, GACHA_PITY_COUNT, MINI_APP_TG_URL
from shared_prices import GACHA_SINGLES_SINGLE, GACHA_SINGLES_MULTI
from api.gacha import (
    _JUNK_ITEMS, _COMMON_ITEMS, _RARE_ITEMS, _LEGENDARY_ITEMS,
)
from database.db import (
    add_mora,
    deduct_mora,
    get_gacha_inventory,
    get_mora,
    get_received_gifts,
    get_top_frame,
    get_user_owned_frames,
    get_user_themes,
    is_user_single,
    sell_gacha_junk,
)
from filters.bot_command import BotCommand

router = Router()


# ─── Пул предметов (импорт из api/gacha — единый источник) ──────────────────
# _JUNK_ITEMS, _COMMON_ITEMS, _RARE_ITEMS, _LEGENDARY_ITEMS
# импортируются из api.gacha (см. imports вверху)

_RARITY_EMOJI = {
    "junk":      "⚪",
    "common":    "🟢",
    "rare":      "🟣",
    "legendary": "🟡",
}

_RARITY_LABEL = {
    "junk":      "Мусор",
    "common":    "Обычный",
    "rare":      "Редкий",
    "legendary": "Легендарный",
}


# _roll_one / _do_rolls удалены — основной путь через api.gacha.gacha_roll


def _format_results(results: list[tuple[str, str, str, str]]) -> str:
    lines = []
    for key, name, rarity, desc in results:
        emoji = _RARITY_EMOJI.get(rarity, "⚪")
        lines.append(f"  {emoji} {name}\n      <i>{desc}</i>")
    return "\n".join(lines)


# ─── бот молитва ──────────────────────────────────────────────────────────────

@router.message(BotCommand(
    "молитва", "помолиться", "крутка", "wish", "pray",
    "молитвы", "гача", "gacha",
))
async def cmd_gacha(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Молитвы доступны только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    # PHASE 3: Gacha → Mini App in groups
    abs_cid = abs(message.chat.id)
    btn = InlineKeyboardButton(
        text="🙏 Молитвы в Mini App",
        url=f"{MINI_APP_TG_URL}?startapp={abs_cid}",
    )
    await message.answer(
        "🙏 <b>Молитвы переехали в Mini App!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("gacha:"))
async def cb_gacha_roll(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    count = int(parts[2])

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твоя молитва!", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id

    # Проверяем статус одиночки для цены (делегируем в api.gacha)
    try:
        from api.gacha import gacha_roll as _api_gacha_roll
        res = await _api_gacha_roll(uid, chat_id, count)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    results  = [(it["key"], it["name"], it["rarity"], it["desc"]) for it in res["items"]]
    new_bal  = res["new_balance"]
    pity     = res["pity"]
    single   = res["is_single"]
    price    = res["spent"]

    # Определяем лучшую редкость
    rarities = [r[2] for r in results]
    best_rarity = "junk"
    for check in ("legendary", "rare", "common"):
        if check in rarities:
            best_rarity = check
            break

    result_text  = _format_results(results)
    header       = "🌟" if best_rarity == "legendary" else "✨" if best_rarity == "rare" else "🙏"
    discount_note = "\n🆓 <i>(Применена холостяцкая скидка)</i>" if single else ""
    price1_next  = GACHA_SINGLES_SINGLE if single else GACHA_SINGLE_PRICE
    price10_next = GACHA_SINGLES_MULTI  if single else GACHA_MULTI_PRICE

    # Кнопки для повторных круток
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🙏 Ещё x1 — {price1_next} 🪙",
            callback_data=f"gacha:{uid}:1",
        ),
        InlineKeyboardButton(
            text=f"🙏 Ещё x10 — {price10_next} 🪙",
            callback_data=f"gacha:{uid}:10",
        )],
    ])

    try:
        await callback.message.edit_text(
            f"{header} <b>Результат молитвы (x{count})</b>\n\n"
            f"{result_text}\n\n"
            f"💰 Баланс: <b>{new_bal} 🪙</b>\n"
            f"🔄 До гаранта: <b>{GACHA_PITY_COUNT - pity}</b>{discount_note}",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass
    await callback.answer()

    if res.get("quest_done"):
        try:
            name = html.escape(callback.from_user.full_name)
            await callback.message.answer(
                f"🎉 {name} выполнил ежедневное задание! "
                f"<b>+{res['quest_xp']} XP</b>  <b>+{res['quest_mora']} Моры</b> 🪙",
                parse_mode="HTML",
            )
        except Exception:
            pass

@router.message(BotCommand("инвентарь", "предметы", "inventory", "рюкзак"))
async def cmd_inventory(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Инвентарь доступен только в группах.")
        return

    # PHASE 3: Inventory → Mini App in groups
    abs_cid = abs(message.chat.id)
    btn = InlineKeyboardButton(
        text="🎒 Инвентарь в Mini App",
        url=f"{MINI_APP_TG_URL}?startapp={abs_cid}",
    )
    await message.answer(
        "🎒 <b>Инвентарь переехал в Mini App!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )


async def _build_inventory_page(uid: int, chat_id: int, section: str) -> tuple[str, InlineKeyboardMarkup]:
    """Собирает текст + клавиатуру для одной секции инвентаря."""
    tab_buttons = [
        InlineKeyboardButton(
            text=f"{'▶ ' if section == 'items' else ''}📦 Предметы",
            callback_data=f"inv:items:{uid}:{chat_id}",
        ),
        InlineKeyboardButton(
            text=f"{'▶ ' if section == 'cosmetics' else ''}🎨 Косметика",
            callback_data=f"inv:cosmetics:{uid}:{chat_id}",
        ),
        InlineKeyboardButton(
            text=f"{'▶ ' if section == 'gifts' else ''}🎁 Подарки",
            callback_data=f"inv:gifts:{uid}:{chat_id}",
        ),
    ]

    if section == "items":
        text = await _inv_items(uid, chat_id)
    elif section == "cosmetics":
        text = await _inv_cosmetics(uid, chat_id)
    else:
        text = await _inv_gifts(uid, chat_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[tab_buttons])
    return text, kb


async def _inv_items(uid: int, chat_id: int) -> str:
    items = await get_gacha_inventory(uid, chat_id)
    if not items:
        return (
            "🎒 <b>Предметы</b>\n\n"
            "Инвентарь пуст.\n"
            "Получи предметы: <code>бот молитва</code>"
        )

    by_rarity: dict[str, list] = {}
    for item in items:
        r = item["rarity"]
        by_rarity.setdefault(r, []).append(item)

    lines = ["📦 <b>Предметы</b>\n"]
    order = ["legendary", "rare", "common", "junk"]
    for rarity in order:
        group = by_rarity.get(rarity)
        if not group:
            continue
        emoji = _RARITY_EMOJI.get(rarity, "⚪")
        label = _RARITY_LABEL.get(rarity, rarity)
        lines.append(f"\n{emoji} <b>{label}</b> ({len(group)}):")
        # Look up description from item pools
        for item in group[:8]:
            desc = _ITEM_DESC.get(item["item_key"], "")
            equipped = " ◀ <b>экип.</b>" if item.get("equipped") else ""
            desc_line = f"\n      <i>{desc}</i>" if desc else ""
            lines.append(f"  {item['item_name']}{equipped} <code>#{item['id']}</code>{desc_line}")
        if len(group) > 8:
            lines.append(f"  <i>...и ещё {len(group) - 8}</i>")

    junk_count = len(by_rarity.get("junk", []))
    if junk_count > 0:
        lines.append(f"\n🗑 <code>бот продать мусор</code> — продать мусор ({junk_count} шт.)")
    lego_count = len(by_rarity.get("legendary", []))
    if lego_count > 0:
        lines.append("🏆 <code>бот экипировать #ID</code>")
    return "\n".join(lines)


async def _inv_cosmetics(uid: int, chat_id: int) -> str:
    from config import PROFILE_THEMES
    from handlers.economy import TOP_FRAMES

    owned_themes = {t["theme_key"] for t in await get_user_themes(uid, chat_id)}
    active_theme = None
    mora_row = await get_mora(uid, chat_id)
    if mora_row:
        active_theme = mora_row.get("active_theme") or "default"
    equipped_frame = await get_top_frame(uid, chat_id) or "default"
    owned_frames = await get_user_owned_frames(uid, chat_id)
    owned_frames.add("default")  # default is always owned

    lines = ["🎨 <b>Косметика</b>\n"]

    # ─── Рамки ───
    lines.append("🖼 <b>Рамки</b>:")
    any_frame = False
    for key, emoji, name, price, desc in TOP_FRAMES:
        if key not in owned_frames:
            continue
        any_frame = True
        equipped_mark = " ◀ <b>надета</b>" if key == equipped_frame else ""
        lines.append(f"  {emoji} {name}{equipped_mark}")
        if desc:
            lines.append(f"      <i>{desc}</i>")
    if not any_frame:
        lines.append("  <i>Нет рамок. Купи в магазине: <code>бот магазин</code></i>")

    # ─── Темы ───
    lines.append("\n🌈 <b>Темы профиля</b>:")
    any_theme = False
    for key, info in PROFILE_THEMES.items():
        if key not in owned_themes and key != "default":
            continue
        any_theme = True
        active_mark = " ◀ <b>активна</b>" if key == active_theme else ""
        lines.append(f"  {info.get('name', key)}{active_mark}")
    if not any_theme:
        lines.append("  <i>Нет тем. Открываются через гачу или покупку.</i>")

    lines.append("\n🎨 Сменить тему: <code>бот темы</code>")
    return "\n".join(lines)


async def _inv_gifts(uid: int, chat_id: int) -> str:
    gifts = await get_received_gifts(uid, chat_id)
    if not gifts:
        return (
            "🎁 <b>Подарки</b>\n\n"
            "<i>Ты ещё не получал подарков.</i>\n"
            "Партнёр может подарить: <code>бот подарить</code>"
        )
    lines = ["🎁 <b>Полученные подарки</b>\n"]
    for g in gifts:
        cnt = g["cnt"]
        lines.append(f"  {g['gift_name']} × {cnt}")
    return "\n".join(lines)


@router.callback_query(lambda c: c.data and c.data.startswith("inv:"))
async def cb_inventory_tab(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    _, section, owner_str, chat_str = parts[:4]
    owner = int(owner_str)
    chat_id = int(chat_str)

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твой инвентарь.", show_alert=True)
        return

    text, kb = await _build_inventory_page(owner, chat_id, section)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


# helper: pre-built item description lookup
_ITEM_DESC: dict[str, str] = {
    item[0]: item[2]
    for pool in (_JUNK_ITEMS, _COMMON_ITEMS, _RARE_ITEMS, _LEGENDARY_ITEMS)
    for item in pool
}


# ─── бот продать мусор ────────────────────────────────────────────────────────

@router.message(BotCommand("продать мусор", "sell junk", "продать хлам"))
async def cmd_sell_junk(message: Message, cmd_args: str):
    if message.chat.type == "private":
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    count, total = await sell_gacha_junk(uid, chat_id)
    if count == 0:
        await message.answer("🗑 Нет мусора для продажи.")
        return

    await message.answer(
        f"🗑 <b>Продано {count} шт. мусора</b>\n"
        f"💰 Получено: <b>+{total} 🪙</b>",
        parse_mode="HTML",
    )


# ─── бот экипировать ──────────────────────────────────────────────────────────

@router.message(BotCommand("экипировать", "equip", "надеть"))
async def cmd_equip(message: Message, cmd_args: str):
    if message.chat.type == "private":
        return

    arg = (cmd_args or "").strip().lstrip("#")
    if not arg.isdigit():
        await message.answer(
            "❌ Укажи ID предмета.\nПример: <code>бот экипировать #42</code>",
            parse_mode="HTML",
        )
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    item_id = int(arg)

    from services.inventory_service import equip_legendary
    from services.exceptions import ItemNotFoundError
    try:
        await equip_legendary(uid, chat_id, item_id)
        await message.answer(
            f"✅ Предмет <b>#{item_id}</b> экипирован!\n"
            f"Он теперь отображается в твоём профиле.",
            parse_mode="HTML",
        )
    except ItemNotFoundError:
        await message.answer(
            "❌ Предмет не найден, не принадлежит тебе или не является легендарным.",
        )
