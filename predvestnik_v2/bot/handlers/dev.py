"""
bot/handlers/dev.py
Developer-only commands. All handlers behind F.from_user.id == config.developer_id filter.
"""
from aiogram import Router, types, F

from bot.config import config
from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY
from services.utils import resolve_target, safe_html, format_currency

router = Router()
router.message.filter(F.from_user.id == config.developer_id)


# ── Dev item registry ─────────────────────────────────────────────────────────

@router.message(TextCmd(["dev предметы", "реестр предметов"]))
async def cmd_dev_items(message: types.Message):
    text = "📦 <b>РЕЕСТР ПРЕДМЕТОВ:</b>\n"
    for k, v in ITEMS_REGISTRY.items():
        text += f"• <code>{k}</code> — {v['name']}\n"
    await message.answer(text, parse_mode="HTML")


# ── Dev stats ─────────────────────────────────────────────────────────────────

@router.message(TextCmd(["dev стат", "dev stat", "dev статистика"]))
async def cmd_dev_stat(message: types.Message, db):
    async with db.execute("SELECT COUNT(*) FROM users") as c:
        users = (await c.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM pets") as c:
        pets = (await c.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM chat_settings") as c:
        chats = (await c.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM marriages WHERE user1_id IS NOT NULL") as c:
        marriages = (await c.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM active_expeditions") as c:
        active_exped = (await c.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM auction_lots WHERE status = 'active'") as c:
        active_lots = (await c.fetchone())[0]

    await message.answer(
        f"📊 <b>СИСТЕМНАЯ СТАТИСТИКА</b>\n\n"
        f"├ 👤 Пользователей: <code>{users}</code>\n"
        f"├ 🐾 Питомцев: <code>{pets}</code>\n"
        f"├ 🏘 Чатов: <code>{chats}</code>\n"
        f"├ 💍 Браков: <code>{marriages}</code>\n"
        f"├ 🗺 Активных экспедиций: <code>{active_exped}</code>\n"
        f"└ 🏛 Активных лотов: <code>{active_lots}</code>",
        parse_mode="HTML",
    )


# ── Dev user info ─────────────────────────────────────────────────────────────

@router.message(TextCmd(["dev юзер", "dev user"]))
async def cmd_dev_user(message: types.Message, db, text_args: str = None):
    target_id, target_name, _ = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer("ℹ️ <code>бот dev юзер, @ник</code>", parse_mode="HTML")

    from infrastructure.repositories.economy import get_balance
    from infrastructure.repositories.users import get_global_rank
    bal = await get_balance(db, target_id)
    grank = await get_global_rank(db, target_id)

    async with db.execute(
        "SELECT COUNT(*) FROM pets WHERE owner_id = ?", (target_id,)
    ) as c:
        pet_count = (await c.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE user_tg_id = ?", (target_id,)
    ) as c:
        chat_count = (await c.fetchone())[0]

    await message.answer(
        f"🔍 <b>DEV ДОСЬЕ:</b> {safe_html(target_name)} <code>({target_id})</code>\n\n"
        f"├ 🌍 Глобальный ранг: <code>{grank}</code>\n"
        f"├ 🪙 Мора: <code>{format_currency(bal['user_balance_mora'])}</code>\n"
        f"├ 💎 Алмазы: <code>{format_currency(bal['user_balance_diamonds'])}</code>\n"
        f"├ 🐾 Питомцев: <code>{pet_count}</code>\n"
        f"└ 💬 Чатов: <code>{chat_count}</code>",
        parse_mode="HTML",
    )


# ── Dev balance adjust ────────────────────────────────────────────────────────

@router.message(TextCmd(["dev баланс", "dev balance"]))
async def cmd_dev_balance(message: types.Message, db, text_args: str = None):
    import re as _re
    usage = "ℹ️ <code>бот dev баланс, @ник, [мора], [алмазы]</code>"
    if not text_args:
        return await message.answer(usage, parse_mode="HTML")

    # Support comma-separated: "@ник, 1000, 5"
    # AND space/keyword-separated: "@ник мора 99999999" or "@ник 1000 5"
    parts_comma = [p.strip() for p in text_args.split(",")]
    target_id, target_name, _ = await resolve_target(message, db, parts_comma[0])
    if not target_id:
        return await message.answer("❌ Пользователь не найден.", parse_mode="HTML")

    mora = 0.0
    diamonds = 0.0
    if len(parts_comma) >= 2:
        try:
            mora = float(parts_comma[1]) if parts_comma[1] else 0.0
            diamonds = float(parts_comma[2]) if len(parts_comma) > 2 and parts_comma[2] else 0.0
        except ValueError:
            return await message.answer(f"❌ Неверный формат чисел.\n{usage}", parse_mode="HTML")
    else:
        # No commas — extract numbers from text_args (ignoring word tokens like "мора"/"алмазы")
        nums = _re.findall(r'\d+(?:[.,]\d+)?', text_args)
        try:
            mora = float(nums[0].replace(',', '.')) if len(nums) > 0 else 0.0
            diamonds = float(nums[1].replace(',', '.')) if len(nums) > 1 else 0.0
        except (ValueError, IndexError):
            return await message.answer(f"❌ Не удалось разобрать числа.\n{usage}", parse_mode="HTML")

    from infrastructure.repositories.economy import set_balance
    await set_balance(db, target_id, mora, diamonds, chat_id=message.chat.id)

    await message.answer(
        f"✅ <b>Баланс установлен</b>\n"
        f"👤 {safe_html(target_name)}\n"
        f"├ 🪙 Мора: <code>{format_currency(mora)}</code>\n"
        f"└ 💎 Алмазы: <code>{format_currency(diamonds)}</code>",
        parse_mode="HTML",
    )


# ── Dev streak reset ──────────────────────────────────────────────────────────

@router.message(TextCmd(["dev сбросить стрик", "dev reset streak"]))
async def cmd_dev_reset_streak(message: types.Message, db, text_args: str = None):
    target_id, target_name, _ = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer("ℹ️ <code>бот dev сбросить стрик, @ник</code>", parse_mode="HTML")

    await db.execute(
        "UPDATE daily_login SET streak = 0, last_login = NULL, recovery_streak = 0 "
        "WHERE user_id = ?",
        (target_id,),
    )
    await db.commit()
    await message.answer(
        f"✅ Стрик сброшен для {safe_html(target_name)}.", parse_mode="HTML"
    )


# ── Dev force events ──────────────────────────────────────────────────────────

@router.message(TextCmd(["dev ивент сундук", "dev chest"]))
async def cmd_dev_chest(message: types.Message, db):
    from datetime import datetime, timezone, timedelta
    from infrastructure.repositories.chest_events import create_chest, update_last_chest_at
    expires = datetime.now(timezone.utc) + timedelta(seconds=90)
    expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")
    chest_id = await create_chest(db, message.chat.id, expires_str)
    await update_last_chest_at(db, message.chat.id)
    await db.commit()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from bot.handlers.events import ChestCB
    from core.constants import CHEST_MAX_CLAIMANTS

    b = InlineKeyboardBuilder()
    b.button(text=f"👋 Забрать! (0/{CHEST_MAX_CLAIMANTS})", callback_data=ChestCB(chest_id=chest_id))
    await message.answer(
        "💰 <b>DEV — ПРИНУДИТЕЛЬНЫЙ СУНДУК!</b>\n\n"
        "🥇 1 место: <b>70 🪙</b> + 🎟 Жетон\n"
        "🥈 2 место: <b>65 🪙</b> + 🎟 Жетон\n"
        "🥉 3 место: <b>60 🪙</b> + 🎟 Жетон\n"
        "4–15 место: <b>55 → 10 🪙</b>\n\n"
        "Нажми быстрее — чем раньше, тем больше! ⏳ 90 сек.",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )


@router.message(TextCmd(["dev ивент обмен", "dev exchange"]))
async def cmd_dev_exchange(message: types.Message, db):
    from datetime import datetime, timezone, timedelta
    from infrastructure.repositories.exchange import create_event, activate_event
    now = datetime.now(timezone.utc)
    starts = now.strftime("%Y-%m-%d %H:%M:%S")
    ends = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    eid = await create_event(db, starts, ends)
    await activate_event(db, eid)
    await db.commit()
    from core.constants import EXCHANGE_RATE_MORA_PER_DIAMOND, EXCHANGE_DAILY_CAP_DIAMONDS
    await message.answer(
        f"✅ <b>Ивент обмена запущен</b> (24ч)\n"
        f"├ Курс: {int(EXCHANGE_RATE_MORA_PER_DIAMOND)} 🪙 = 1 💎\n"
        f"└ Лимит: {int(EXCHANGE_DAILY_CAP_DIAMONDS)} 💎/день\n\n"
        f"<code>бот обмен</code>",
        parse_mode="HTML",
    )


@router.message(TextCmd(["dev акция", "dev deal"]))
async def cmd_dev_deal(message: types.Message, db):
    from services.daily_deal import generate_deal_slots
    from infrastructure.repositories.daily_deal import save_deals
    from datetime import datetime, timezone
    slots = generate_deal_slots()
    await save_deals(db, slots, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    await message.answer("✅ Акция дня принудительно обновлена.\n<code>бот акция</code>", parse_mode="HTML")


# ── C1-C: Global blacklist ────────────────────────────────────────────────────

# ── C2: Global module toggles ─────────────────────────────────────────────────

_MODULE_KEYS = [
    "module_shop", "module_gacha", "module_expeditions", "module_auction",
    "module_games", "module_exchange", "module_quests", "module_zoo",
    "module_warps", "module_daily_deal",
]
_MODULE_EMOJI = {
    "module_shop": "🛒", "module_gacha": "🎰", "module_expeditions": "🗺",
    "module_auction": "🏛", "module_games": "🎲", "module_exchange": "💱",
    "module_quests": "📋", "module_zoo": "🐾", "module_warps": "🤝",
    "module_daily_deal": "🏷",
}


@router.message(TextCmd(["dev модули", "dev modules"]))
async def cmd_dev_modules(message: types.Message, db):
    lines = ["🧩 <b>ГЛОБАЛЬНЫЕ МОДУЛИ</b>\n"]
    for key in _MODULE_KEYS:
        async with db.execute(
            "SELECT enabled, disabled_reason FROM global_module_toggles WHERE module_key = ?",
            (key,),
        ) as c:
            row = await c.fetchone()
        enabled = row[0] if row else 1
        reason = f" ({row[1]})" if row and row[1] else ""
        status = "✅" if enabled else "❌"
        emoji = _MODULE_EMOJI.get(key, "•")
        lines.append(f"├ {emoji} <code>{key}</code>: {status}{reason}")
    lines[-1] = lines[-1].replace("├", "└", 1)
    lines.append("\n<i>бот dev модуль вкл/выкл, [module_key] [причина]</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(TextCmd(["dev модуль вкл", "dev module on"]))
async def cmd_dev_module_on(message: types.Message, db, text_args: str = None):
    if not text_args:
        return await message.answer("ℹ️ <code>бот dev модуль вкл, [module_key]</code>", parse_mode="HTML")
    key = text_args.strip().lower()
    if key not in _MODULE_KEYS:
        return await message.answer(f"❌ Неизвестный ключ. Доступные: {', '.join(_MODULE_KEYS)}", parse_mode="HTML")
    await db.execute(
        "INSERT INTO global_module_toggles (module_key, enabled, updated_at) VALUES (?, 1, CURRENT_TIMESTAMP) "
        "ON CONFLICT(module_key) DO UPDATE SET enabled=1, disabled_reason=NULL, updated_at=CURRENT_TIMESTAMP",
        (key,),
    )
    await db.commit()
    await message.answer(f"✅ Модуль <code>{key}</code> включён глобально.", parse_mode="HTML")


@router.message(TextCmd(["dev модуль выкл", "dev module off"]))
async def cmd_dev_module_off(message: types.Message, db, text_args: str = None):
    if not text_args:
        return await message.answer("ℹ️ <code>бот dev модуль выкл, [module_key] [причина]</code>", parse_mode="HTML")
    parts = [p.strip() for p in text_args.split(",", 1)]
    key = parts[0].lower()
    reason = parts[1] if len(parts) > 1 else None
    if key not in _MODULE_KEYS:
        return await message.answer(f"❌ Неизвестный ключ.", parse_mode="HTML")
    await db.execute(
        "INSERT INTO global_module_toggles (module_key, enabled, disabled_reason, updated_at) "
        "VALUES (?, 0, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(module_key) DO UPDATE SET enabled=0, disabled_reason=excluded.disabled_reason, updated_at=CURRENT_TIMESTAMP",
        (key, reason),
    )
    await db.commit()
    reason_str = f" Причина: {safe_html(reason)}" if reason else ""
    await message.answer(f"❌ Модуль <code>{key}</code> отключён глобально.{reason_str}", parse_mode="HTML")


@router.message(TextCmd(["dev глобал чс", "dev global bl"]))
async def cmd_dev_global_bl_list(message: types.Message, db):
    from infrastructure.repositories.blacklist import get_global_blacklist
    entries = await get_global_blacklist(db)
    if not entries:
        return await message.answer(
            "🌐 <b>ГЛОБАЛЬНЫЙ ЧС</b>\n\n<i>Пусто.</i>", parse_mode="HTML"
        )
    lines = [f"🌐 <b>ГЛОБАЛЬНЫЙ ЧС</b> ({len(entries)})\n"]
    for i, e in enumerate(entries[:30]):
        prefix = "└" if i == len(entries[:30]) - 1 else "├"
        r = f" — {safe_html(e['reason'])}" if e.get("reason") else ""
        lines.append(f"{prefix} [{e['entity_type']}] <code>{e['entity_id']}</code>{r}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(TextCmd(["dev глобал чс добавить", "dev global bl add"]))
async def cmd_dev_global_bl_add(message: types.Message, db, text_args: str = None):
    from infrastructure.repositories.blacklist import add_to_global_blacklist
    if not text_args:
        return await message.answer(
            "ℹ️ <code>бот dev глобал чс добавить, @юзер [причина]</code>\n"
            "или <code>бот dev глобал чс добавить, [chat_id]</code>",
            parse_mode="HTML",
        )
    parts = [p.strip() for p in text_args.split(",", 1)]
    raw = parts[0]
    reason = parts[1].strip() if len(parts) > 1 else None

    # Determine user vs chat
    if raw.lstrip("-").isdigit():
        entity_id = int(raw)
        entity_type = "chat" if entity_id < 0 else "user"
    else:
        target_id, _, _ = await resolve_target(message, db, raw)
        if not target_id:
            return await message.answer("❌ Пользователь не найден.", parse_mode="HTML")
        entity_id = target_id
        entity_type = "user"

    await add_to_global_blacklist(db, entity_type, entity_id, reason)
    await db.commit()
    await message.answer(
        f"✅ [{entity_type}] <code>{entity_id}</code> добавлен в глобальный ЧС.",
        parse_mode="HTML",
    )


@router.message(TextCmd(["dev глобал чс убрать", "dev global bl remove"]))
async def cmd_dev_global_bl_remove(message: types.Message, db, text_args: str = None):
    from infrastructure.repositories.blacklist import remove_from_global_blacklist
    if not text_args:
        return await message.answer(
            "ℹ️ <code>бот dev глобал чс убрать, @юзер</code> или <code>[id]</code>",
            parse_mode="HTML",
        )
    raw = text_args.strip()
    if raw.lstrip("-").isdigit():
        entity_id = int(raw)
        entity_type = "chat" if entity_id < 0 else "user"
    else:
        target_id, _, _ = await resolve_target(message, db, raw)
        if not target_id:
            return await message.answer("❌ Не найдено.", parse_mode="HTML")
        entity_id = target_id
        entity_type = "user"
    removed = await remove_from_global_blacklist(db, entity_type, entity_id)
    await db.commit()
    if removed:
        await message.answer(f"✅ [{entity_type}] <code>{entity_id}</code> снят с глобального ЧС.", parse_mode="HTML")
    else:
        await message.answer("ℹ️ Не найден в глобальном ЧС.", parse_mode="HTML")


@router.message(TextCmd(["dev гача сброс", "dev reset pity"]))
async def cmd_dev_reset_pity(message: types.Message, db, text_args: str = None):
    target_id, target_name, _ = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer("ℹ️ <code>бот dev гача сброс, @ник</code>", parse_mode="HTML")
    await db.execute("DELETE FROM gacha_pity WHERE user_id = ?", (target_id,))
    await db.commit()
    await message.answer(f"✅ Пити гачи сброшен для {safe_html(target_name)}.", parse_mode="HTML")
