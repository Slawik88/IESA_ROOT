"""
bot/handlers/promocodes.py
Promo code system:
  User: бот промокод, CODE  → activation with loot animation
  Dev:  бот dev промокод     → management panel (FSM creation wizard)
"""
import asyncio
import json
import re
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from bot.config import config
from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories import promocodes as promo_repo
from services.promocodes import activate_promocode, PromoError, format_reward_text
from services.utils import safe_html

router = Router(name="promo_router")

# ─── FSM States for promo creation ───────────────────────────────────────────

class PromoCreate(StatesGroup):
    code = State()
    description = State()
    mora = State()
    diamonds = State()
    dark_mora = State()       # NEW
    items = State()
    max_uses = State()
    valid_from = State()
    valid_until = State()
    allowed_users = State()   # NEW
    allowed_chats = State()   # NEW


# ─── Callback data ────────────────────────────────────────────────────────────

class PromoCB(CallbackData, prefix="promo_admin"):
    action: str
    data: str = ""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_dev(user_id: int) -> bool:
    return bool(config.developer_id and user_id == config.developer_id)


def _promo_admin_keyboard() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📝 Создать промокод", callback_data=PromoCB(action="create"))
    b.button(text="📋 Список промокодов", callback_data=PromoCB(action="list"))
    b.button(text="🔴 Деактивировать", callback_data=PromoCB(action="deactivate_prompt"))
    b.button(text="🟢 Активировать", callback_data=PromoCB(action="activate_prompt"))
    b.button(text="🗑 Удалить", callback_data=PromoCB(action="delete_prompt"))
    b.adjust(1, 2, 2)
    return b.as_markup()


def _cancel_keyboard() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data=PromoCB(action="cancel"))
    return b.as_markup()


def _confirm_keyboard() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Создать", callback_data=PromoCB(action="confirm_create"))
    b.button(text="❌ Отмена", callback_data=PromoCB(action="cancel"))
    b.adjust(2)
    return b.as_markup()


def _fmt_promo_list_item(p: dict, idx: int, total: int) -> str:
    prefix = "└" if idx == total - 1 else "├"
    status = "🟢" if p["is_active"] else "🔴"
    exp = ""
    if p["valid_until"]:
        exp = f" · до {p['valid_until'][:10]}"
    max_str = (
        f"{p['activations_count']}/{p['max_activations']}"
        if p["max_activations"] > 0
        else f"{p['activations_count']}/∞"
    )
    # Show lock icons if restricted
    locks = ""
    users_raw = p.get("allowed_users_json") or "[]"
    chats_raw = p.get("allowed_chats_json") or "[]"
    try:
        if json.loads(users_raw):
            locks += "👤"
    except Exception:
        pass
    try:
        if json.loads(chats_raw):
            locks += "💬"
    except Exception:
        pass
    lock_str = f" {locks}" if locks else ""
    return f"{prefix} {status} <code>{p['code']}</code>{lock_str} — {max_str} активаций{exp}"


def _progress_bar(pct: int) -> str:
    filled = round(pct / 10)
    bar = "▰" * filled + "▱" * (10 - filled)
    return f"<code>{bar}</code> {pct}%"


# ─── User: activate promo code ────────────────────────────────────────────────

@router.message(TextCmd(["промокод", "promo", "промо"]))
async def cmd_promo_activate(message: types.Message, db, text_args: str = None):
    if not text_args or not text_args.strip():
        return await message.answer(
            "🎁 <b>ПРОМОКОД</b>\n\n"
            "Введи команду с кодом:\n"
            "<code>бот промокод, КОД</code>",
            parse_mode="HTML",
        )

    code = text_args.strip().upper()
    user_id = message.from_user.id
    chat_id = message.chat.id if message.chat.type != "private" else None

    # Frame 1 — initial check
    msg = await message.answer("⏳ <i>Проверяю промокод...</i>", parse_mode="HTML")
    await asyncio.sleep(0.5)

    # Run activation (DB call happens here)
    try:
        reward = await activate_promocode(db, user_id, code, chat_id)
    except PromoError as e:
        await msg.edit_text(str(e), parse_mode="HTML")
        return

    # Frame 2 — code verified, bar at 0%
    await msg.edit_text(
        f"🔑 <b>Код верифицирован!</b>\n\n"
        f"{_progress_bar(0)}",
        parse_mode="HTML",
    )
    await asyncio.sleep(0.55)

    # Frame 3 — loading rewards, bar at 60%
    await msg.edit_text(
        f"🎁 <i>Начисляем награды...</i>\n\n"
        f"{_progress_bar(60)}",
        parse_mode="HTML",
    )
    await asyncio.sleep(0.55)

    # Frame 4 — 100%
    await msg.edit_text(
        f"✨ <i>Готово!</i>\n\n"
        f"{_progress_bar(100)}",
        parse_mode="HTML",
    )
    await asyncio.sleep(0.55)

    # Final reward screen
    reward_lines = format_reward_text(reward)
    desc_line = f"\n📜 <i>{safe_html(reward['description'])}</i>\n" if reward["description"] else "\n"

    text = (
        f"🎊 <b>ПРОМОКОД АКТИВИРОВАН!</b>\n"
        f"╔══════════════════╗\n"
        f"  🎫 <code>{reward['code']}</code>\n"
        f"╚══════════════════╝\n"
        f"{desc_line}\n"
        f"💰 <b>Получено:</b>\n"
        f"{reward_lines}"
    )
    await msg.edit_text(text, parse_mode="HTML")


# ─── Dev: promo admin panel ───────────────────────────────────────────────────

@router.message(TextCmd(["dev промокод", "dev promo"]))
async def cmd_dev_promo_panel(message: types.Message):
    if not _is_dev(message.from_user.id):
        return
    await message.answer(
        "🎫 <b>УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>\n\n"
        "<i>Выберите действие:</i>",
        reply_markup=_promo_admin_keyboard(),
        parse_mode="HTML",
    )


# ─── Dev: list all promo codes ────────────────────────────────────────────────

@router.message(TextCmd(["dev промокод список", "dev promo list"]))
async def cmd_dev_promo_list(message: types.Message, db):
    if not _is_dev(message.from_user.id):
        return
    promos = await promo_repo.list_promocodes(db)
    if not promos:
        return await message.answer(
            "📋 <b>Промокоды</b>\n\n<i>Список пуст.</i>",
            parse_mode="HTML",
        )
    lines = [f"📋 <b>ПРОМОКОДЫ</b> ({len(promos)})\n"]
    for i, p in enumerate(promos[:30]):
        lines.append(_fmt_promo_list_item(p, i, min(len(promos), 30)))
    lines.append("\n<i>👤 — ограничен по пользователям · 💬 — ограничен по чатам</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Dev: promo info command ──────────────────────────────────────────────────

@router.message(TextCmd(["dev промокод инфо", "dev promo info"]))
async def cmd_dev_promo_info(message: types.Message, db, text_args: str = None):
    if not _is_dev(message.from_user.id):
        return
    if not text_args or not text_args.strip():
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот dev промокод инфо, КОД</code>",
            parse_mode="HTML",
        )
    code = text_args.strip().upper()
    promo = await promo_repo.get_promocode(db, code)
    if not promo:
        return await message.answer(f"❌ Промокод <code>{code}</code> не найден.", parse_mode="HTML")

    status_str = "🟢 Активен" if promo["is_active"] else "🔴 Деактивирован"
    max_str = f"{promo['activations_count']}/{promo['max_activations']}" if promo["max_activations"] > 0 else f"{promo['activations_count']}/∞"

    items: dict = {}
    try:
        items = json.loads(promo.get("reward_items_json") or "{}")
    except Exception:
        pass
    items_str = "\n".join(
        f"    ├ {ITEMS_REGISTRY.get(k, {}).get('name', k)} ×{v}" for k, v in items.items()
    ) if items else "    └ <i>нет</i>"
    if items:
        lines = items_str.split("\n")
        lines[-1] = lines[-1].replace("├", "└", 1)
        items_str = "\n".join(lines)

    # Whitelists
    allowed_users: list[int] = []
    allowed_chats: list[int] = []
    try:
        allowed_users = json.loads(promo.get("allowed_users_json") or "[]")
    except Exception:
        pass
    try:
        allowed_chats = json.loads(promo.get("allowed_chats_json") or "[]")
    except Exception:
        pass

    users_str = ", ".join(str(u) for u in allowed_users) if allowed_users else "все"
    chats_str = ", ".join(str(c) for c in allowed_chats) if allowed_chats else "все"

    dark_mora = float(promo.get("reward_dark_mora") or 0)

    raw_created = promo.get("created_at", "")
    if hasattr(raw_created, "strftime"):
        created_str = raw_created.strftime("%Y-%m-%d %H:%M")
    else:
        created_str = str(raw_created)[:16]

    lines_out = [
        f"🔍 <b>ИНФО: <code>{code}</code></b>\n",
        f"├ Статус: {status_str}",
        f"├ Активаций: <code>{max_str}</code>",
        f"├ Начало: <code>{promo['valid_from'] or 'сразу'}</code>",
        f"├ Конец: <code>{promo['valid_until'] or 'бессрочно'}</code>",
        f"├ Создан: <code>{created_str}</code>",
        f"├ Описание: <i>{safe_html(promo.get('description', '') or 'нет')}</i>\n",
        f"💰 <b>Награды:</b>",
        f"├ 🪙 Мора: <code>{float(promo['reward_mora'] or 0):,.0f}</code>",
        f"├ 💎 Алмазы: <code>{float(promo['reward_diamonds'] or 0):,.1f}</code>",
        f"├ 🌑 Тёмная Мора: <code>{dark_mora:,.0f}</code>",
        f"└ 📦 Предметы:\n{items_str}\n",
        f"🔒 <b>Ограничения:</b>",
        f"├ 👤 Пользователи: <code>{users_str}</code>",
        f"└ 💬 Чаты: <code>{chats_str}</code>",
    ]

    # Last activators
    activators = await promo_repo.get_promo_activators(db, code, limit=5)
    if activators:
        lines_out.append("\n👥 <b>Последние активации:</b>")
        for i, a in enumerate(activators):
            prefix = "└" if i == len(activators) - 1 else "├"
            raw_ts = a.get("redeemed_at", "")
            if hasattr(raw_ts, "strftime"):
                ts = raw_ts.strftime("%Y-%m-%d %H:%M")
            else:
                ts = str(raw_ts)[:16]
            chat_part = f" · чат {a['chat_id']}" if a.get("chat_id") else ""
            lines_out.append(f"{prefix} <code>{a['user_id']}</code>{chat_part} — {ts}")

    await message.answer("\n".join(lines_out), parse_mode="HTML")


# ─── Callbacks ────────────────────────────────────────────────────────────────

@router.callback_query(PromoCB.filter())
async def handle_promo_cb(
    query: types.CallbackQuery,
    callback_data: PromoCB,
    db,
    state: FSMContext,
):
    if not _is_dev(query.from_user.id):
        return await query.answer("🔒 Только для разработчика.", show_alert=True)

    action = callback_data.action
    extra = callback_data.data

    if action == "cancel":
        await state.clear()
        try:
            await query.message.edit_text("❌ Отменено.", parse_mode="HTML")
        except Exception:
            pass
        return await query.answer()

    if action == "list":
        promos = await promo_repo.list_promocodes(db)
        if not promos:
            await query.answer("Список пуст.", show_alert=True)
            return
        lines = [f"📋 <b>ПРОМОКОДЫ</b> ({len(promos)})\n"]
        for i, p in enumerate(promos[:30]):
            lines.append(_fmt_promo_list_item(p, i, min(len(promos), 30)))
        lines.append("\n<i>👤 — ограничен по пользователям · 💬 — ограничен по чатам</i>")
        try:
            await query.message.edit_text(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=_promo_admin_keyboard(),
            )
        except Exception:
            pass
        return await query.answer()

    if action == "create":
        await state.set_state(PromoCreate.code)
        try:
            await query.message.edit_text(
                "📝 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
                "Шаг 1/11 — <b>Код промокода</b>\n"
                "<i>Только латиница, цифры, дефис. Будет преобразован в ВЕРХНИЙ РЕГИСТР.</i>\n\n"
                "Напиши код:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return await query.answer()

    if action == "deactivate_prompt":
        await state.set_state(PromoCreate.code)
        await state.update_data(wizard_mode="deactivate")
        try:
            await query.message.edit_text(
                "🔴 <b>Деактивировать промокод</b>\n\n"
                "Напиши код промокода для деактивации:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return await query.answer()

    if action == "activate_prompt":
        await state.set_state(PromoCreate.code)
        await state.update_data(wizard_mode="activate")
        try:
            await query.message.edit_text(
                "🟢 <b>Активировать промокод</b>\n\n"
                "Напиши код промокода для повторной активации:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return await query.answer()

    if action == "delete_prompt":
        await state.set_state(PromoCreate.code)
        await state.update_data(wizard_mode="delete")
        try:
            await query.message.edit_text(
                "🗑 <b>Удалить промокод</b>\n\n"
                "⚠️ Удаляет промокод и всю историю активаций.\n"
                "Напиши код промокода для удаления:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return await query.answer()

    if action == "confirm_create":
        data = await state.get_data()
        if data.get("wizard_mode") != "confirm":
            return await query.answer("Нет данных для создания.", show_alert=True)

        ok = await promo_repo.create_promocode(
            db,
            code=data["code"],
            description=data.get("description", ""),
            mora=float(data.get("mora", 0)),
            diamonds=float(data.get("diamonds", 0)),
            dark_mora=float(data.get("dark_mora", 0)),
            items_json=data.get("items_json", "{}"),
            max_activations=int(data.get("max_uses", 0)),
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
            created_by=query.from_user.id,
            allowed_users_json=data.get("allowed_users_json", "[]"),
            allowed_chats_json=data.get("allowed_chats_json", "[]"),
        )
        await state.clear()

        if ok:
            await query.message.edit_text(
                f"✅ <b>Промокод <code>{data['code']}</code> создан!</b>",
                parse_mode="HTML",
                reply_markup=_promo_admin_keyboard(),
            )
        else:
            await query.message.edit_text(
                f"❌ Промокод <code>{data['code']}</code> уже существует.",
                parse_mode="HTML",
                reply_markup=_promo_admin_keyboard(),
            )
        return await query.answer()

    await query.answer()


# ─── FSM: creation wizard steps ───────────────────────────────────────────────

@router.message(StateFilter(PromoCreate.code))
async def fsm_receive_code(message: types.Message, db, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return

    data = await state.get_data()
    wizard_mode = data.get("wizard_mode", "create")
    code = message.text.strip().upper() if message.text else ""

    # Handle non-create modes (deactivate / activate / delete)
    if wizard_mode == "deactivate":
        ok = await promo_repo.deactivate_promocode(db, code)
        await state.clear()
        txt = f"🔴 Промокод <code>{code}</code> деактивирован." if ok else f"❌ Промокод <code>{code}</code> не найден."
        return await message.answer(txt, parse_mode="HTML")

    if wizard_mode == "activate":
        ok = await promo_repo.activate_promocode_record(db, code)
        await state.clear()
        txt = f"🟢 Промокод <code>{code}</code> активирован." if ok else f"❌ Промокод <code>{code}</code> не найден."
        return await message.answer(txt, parse_mode="HTML")

    if wizard_mode == "delete":
        ok = await promo_repo.delete_promocode(db, code)
        await state.clear()
        txt = f"🗑 Промокод <code>{code}</code> удалён." if ok else f"❌ Промокод <code>{code}</code> не найден."
        return await message.answer(txt, parse_mode="HTML")

    # Create mode — validate code format
    if not re.match(r'^[A-Z0-9\-_]{2,32}$', code):
        return await message.answer(
            "❌ Недопустимый формат кода. Только латиница, цифры, дефис и подчёркивание (2–32 символа).\n"
            "Попробуй ещё раз:",
            reply_markup=_cancel_keyboard(),
            parse_mode="HTML",
        )

    await state.update_data(code=code)
    await state.set_state(PromoCreate.description)
    await message.answer(
        f"✅ Код: <code>{code}</code>\n\n"
        f"Шаг 2/11 — <b>Описание</b>\n"
        f"<i>Короткое описание промокода (или «-» чтобы пропустить):</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.description))
async def fsm_receive_description(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    desc = message.text.strip() if message.text else ""
    if desc == "-":
        desc = ""
    await state.update_data(description=desc)
    await state.set_state(PromoCreate.mora)
    await message.answer(
        f"📝 Описание: <i>{safe_html(desc) or 'нет'}</i>\n\n"
        f"Шаг 3/11 — <b>Награда: Мора 🪙</b>\n"
        f"<i>Введи количество Моры (0 = без Моры):</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.mora))
async def fsm_receive_mora(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    try:
        mora = float(message.text.strip().replace(",", "."))
        if mora < 0:
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("❌ Введи число ≥ 0:", reply_markup=_cancel_keyboard(), parse_mode="HTML")
    await state.update_data(mora=mora)
    await state.set_state(PromoCreate.diamonds)
    await message.answer(
        f"🪙 Мора: <code>{mora:,.0f}</code>\n\n"
        f"Шаг 4/11 — <b>Награда: Алмазы 💎</b>\n"
        f"<i>Введи количество алмазов (0 = без алмазов):</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.diamonds))
async def fsm_receive_diamonds(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    try:
        diamonds = float(message.text.strip().replace(",", "."))
        if diamonds < 0:
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("❌ Введи число ≥ 0:", reply_markup=_cancel_keyboard(), parse_mode="HTML")
    await state.update_data(diamonds=diamonds)
    await state.set_state(PromoCreate.dark_mora)
    await message.answer(
        f"💎 Алмазы: <code>{diamonds:,.1f}</code>\n\n"
        f"Шаг 5/11 — <b>Награда: Тёмная Мора 🌑</b>\n"
        f"<i>Введи количество Тёмной Моры (0 = без Тёмной Моры):</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.dark_mora))
async def fsm_receive_dark_mora(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    try:
        dark_mora = float(message.text.strip().replace(",", "."))
        if dark_mora < 0:
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("❌ Введи число ≥ 0:", reply_markup=_cancel_keyboard(), parse_mode="HTML")
    await state.update_data(dark_mora=dark_mora)
    await state.set_state(PromoCreate.items)
    items_example = ", ".join(f"<code>{k}</code>" for k in list(ITEMS_REGISTRY.keys())[:5])
    await message.answer(
        f"🌑 Тёмная Мора: <code>{dark_mora:,.0f}</code>\n\n"
        f"Шаг 6/11 — <b>Предметы 📦</b>\n"
        f"<i>Формат: <code>item_id:количество item_id:количество</code>\n"
        f"Или «-» чтобы не выдавать предметы.\n\n"
        f"Примеры ID предметов: {items_example}</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.items))
async def fsm_receive_items(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    text = message.text.strip() if message.text else "-"
    items: dict[str, int] = {}

    if text != "-":
        tokens = re.split(r'[\s,]+', text)
        errors = []
        for token in tokens:
            if ":" not in token:
                errors.append(f"<code>{token}</code> — нет ':'")
                continue
            parts = token.split(":", 1)
            item_id = parts[0].strip().lower()
            try:
                qty = int(parts[1].strip())
                if qty <= 0:
                    raise ValueError
            except ValueError:
                errors.append(f"<code>{token}</code> — неверное кол-во")
                continue
            if item_id not in ITEMS_REGISTRY:
                errors.append(f"<code>{item_id}</code> — неизвестный предмет")
                continue
            items[item_id] = qty

        if errors:
            return await message.answer(
                f"❌ Ошибки:\n" + "\n".join(f"├ {e}" for e in errors) +
                "\nПопробуй ещё раз или «-»:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )

    items_json = json.dumps(items, ensure_ascii=False)
    await state.update_data(items_json=items_json)
    await state.set_state(PromoCreate.max_uses)

    items_str = ", ".join(f"{ITEMS_REGISTRY.get(k, {}).get('name', k)} ×{v}" for k, v in items.items()) if items else "нет"
    await message.answer(
        f"📦 Предметы: <i>{safe_html(items_str)}</i>\n\n"
        f"Шаг 7/11 — <b>Лимит активаций</b>\n"
        f"<i>Максимальное количество активаций (0 = безлимит):</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.max_uses))
async def fsm_receive_max_uses(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    try:
        max_uses = int(message.text.strip())
        if max_uses < 0:
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("❌ Введи целое число ≥ 0:", reply_markup=_cancel_keyboard(), parse_mode="HTML")
    await state.update_data(max_uses=max_uses)
    await state.set_state(PromoCreate.valid_from)
    await message.answer(
        f"🔢 Лимит: <code>{'∞' if max_uses == 0 else max_uses}</code>\n\n"
        f"Шаг 8/11 — <b>Дата начала</b>\n"
        f"<i>Формат: <code>ДД.ММ.ГГГГ</code> (или «-» — действует сразу):</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.valid_from))
async def fsm_receive_valid_from(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    text = message.text.strip() if message.text else "-"
    valid_from = None
    if text != "-":
        try:
            dt = datetime.strptime(text, "%d.%m.%Y")
            valid_from = dt.strftime("%Y-%m-%d")
        except ValueError:
            return await message.answer(
                "❌ Неверный формат. Используй <code>ДД.ММ.ГГГГ</code> или «-»:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
    await state.update_data(valid_from=valid_from)
    await state.set_state(PromoCreate.valid_until)
    await message.answer(
        f"📅 Начало: <code>{text if valid_from else 'сразу'}</code>\n\n"
        f"Шаг 9/11 — <b>Дата окончания</b>\n"
        f"<i>Формат: <code>ДД.ММ.ГГГГ</code> (или «-» — бессрочно):</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.valid_until))
async def fsm_receive_valid_until(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    text = message.text.strip() if message.text else "-"
    valid_until = None
    if text != "-":
        try:
            dt = datetime.strptime(text, "%d.%m.%Y")
            valid_until = dt.strftime("%Y-%m-%d")
        except ValueError:
            return await message.answer(
                "❌ Неверный формат. Используй <code>ДД.ММ.ГГГГ</code> или «-»:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
    await state.update_data(valid_until=valid_until)
    await state.set_state(PromoCreate.allowed_users)
    await message.answer(
        f"📅 Конец: <code>{text if valid_until else 'бессрочно'}</code>\n\n"
        f"Шаг 10/11 — <b>Ограничение по пользователям 👤</b>\n"
        f"<i>Введи user_id через пробел, если промокод только для конкретных людей.\n"
        f"Или «-» чтобы не ограничивать.\n\n"
        f"Пример: <code>738240269 123456789</code></i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.allowed_users))
async def fsm_receive_allowed_users(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    text = message.text.strip() if message.text else "-"
    allowed_users: list[int] = []

    if text != "-":
        raw_ids = re.split(r'[\s,]+', text)
        errors = []
        for raw in raw_ids:
            if not raw:
                continue
            try:
                uid = int(raw)
                allowed_users.append(uid)
            except ValueError:
                errors.append(f"<code>{raw}</code>")
        if errors:
            return await message.answer(
                f"❌ Неверные user_id: {', '.join(errors)}\n"
                f"Введи только числа или «-»:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )

    allowed_users_json = json.dumps(allowed_users)
    await state.update_data(allowed_users_json=allowed_users_json)
    await state.set_state(PromoCreate.allowed_chats)

    users_str = ", ".join(str(u) for u in allowed_users) if allowed_users else "все"
    await message.answer(
        f"👤 Пользователи: <code>{users_str}</code>\n\n"
        f"Шаг 11/11 — <b>Ограничение по чатам 💬</b>\n"
        f"<i>Введи chat_id через пробел, если промокод только для определённых чатов.\n"
        f"Или «-» чтобы не ограничивать.\n\n"
        f"Пример: <code>-1001234567890 -1009876543210</code></i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(PromoCreate.allowed_chats))
async def fsm_receive_allowed_chats(message: types.Message, state: FSMContext):
    if not _is_dev(message.from_user.id):
        return
    text = message.text.strip() if message.text else "-"
    allowed_chats: list[int] = []

    if text != "-":
        raw_ids = re.split(r'[\s,]+', text)
        errors = []
        for raw in raw_ids:
            if not raw:
                continue
            try:
                cid = int(raw)
                allowed_chats.append(cid)
            except ValueError:
                errors.append(f"<code>{raw}</code>")
        if errors:
            return await message.answer(
                f"❌ Неверные chat_id: {', '.join(errors)}\n"
                f"Введи только числа или «-»:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )

    allowed_chats_json = json.dumps(allowed_chats)
    await state.update_data(allowed_chats_json=allowed_chats_json, wizard_mode="confirm")
    data = await state.get_data()

    # Build confirmation summary
    items: dict = json.loads(data.get("items_json", "{}"))
    items_str = "\n".join(
        f"    ├ {ITEMS_REGISTRY.get(k, {}).get('name', k)} ×{v}" for k, v in items.items()
    ) if items else "    └ <i>нет</i>"
    if items:
        lines = items_str.split("\n")
        lines[-1] = lines[-1].replace("├", "└", 1)
        items_str = "\n".join(lines)

    max_uses = int(data.get("max_uses", 0))
    dark_mora_val = float(data.get("dark_mora", 0))
    vf = data.get("valid_from") or "сразу"
    vu = data.get("valid_until") or "бессрочно"

    allowed_users_list: list[int] = json.loads(data.get("allowed_users_json", "[]"))
    users_str = ", ".join(str(u) for u in allowed_users_list) if allowed_users_list else "все"
    chats_str = ", ".join(str(c) for c in allowed_chats) if allowed_chats else "все"

    summary = (
        f"📋 <b>ПОДТВЕРЖДЕНИЕ ПРОМОКОДА</b>\n\n"
        f"🎫 Код: <code>{data['code']}</code>\n"
        f"📝 Описание: <i>{safe_html(data.get('description', '')) or 'нет'}</i>\n\n"
        f"💰 <b>Награды:</b>\n"
        f"├ 🪙 Мора: <code>{float(data.get('mora', 0)):,.0f}</code>\n"
        f"├ 💎 Алмазы: <code>{float(data.get('diamonds', 0)):,.1f}</code>\n"
        f"├ 🌑 Тёмная Мора: <code>{dark_mora_val:,.0f}</code>\n"
        f"└ 📦 Предметы:\n{items_str}\n\n"
        f"⚙️ <b>Настройки:</b>\n"
        f"├ 🔢 Лимит: <code>{'∞' if max_uses == 0 else max_uses}</code>\n"
        f"├ 📅 Начало: <code>{vf}</code>\n"
        f"├ 📅 Конец: <code>{vu}</code>\n"
        f"├ 👤 Пользователи: <code>{users_str}</code>\n"
        f"└ 💬 Чаты: <code>{chats_str}</code>\n\n"
        f"<b>Создаём промокод?</b>"
    )
    await message.answer(summary, reply_markup=_confirm_keyboard(), parse_mode="HTML")
