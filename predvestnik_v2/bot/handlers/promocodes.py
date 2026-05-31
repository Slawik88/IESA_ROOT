"""
bot/handlers/promocodes.py
Promo code system:
  User: бот промокод, CODE  → activation with loot animation
  Dev:  бот dev промокод     → management panel (FSM creation wizard)
"""
import asyncio
import json
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
    items = State()
    max_uses = State()
    valid_from = State()
    valid_until = State()


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
    max_str = f"{p['activations_count']}/{p['max_activations']}" if p["max_activations"] > 0 else f"{p['activations_count']}/∞"
    return f"{prefix} {status} <code>{p['code']}</code> — {max_str} активаций{exp}"


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

    # Loading animation
    msg = await message.answer(
        "⏳ <i>Проверяю промокод...</i>",
        parse_mode="HTML",
    )

    try:
        reward = await activate_promocode(db, user_id, code, chat_id)
    except PromoError as e:
        await msg.edit_text(str(e), parse_mode="HTML")
        return

    # Animation step 1
    await asyncio.sleep(0.5)
    await msg.edit_text(
        f"🎁 <b>Промокод <code>{reward['code']}</code> принят!</b>\n\n"
        f"✨ <i>Считаем награду...</i>",
        parse_mode="HTML",
    )

    await asyncio.sleep(0.8)

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
    await message.answer("\n".join(lines), parse_mode="HTML")


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
        try:
            await query.message.edit_text("\n".join(lines), parse_mode="HTML",
                                          reply_markup=_promo_admin_keyboard())
        except Exception:
            pass
        return await query.answer()

    if action == "create":
        await state.set_state(PromoCreate.code)
        try:
            await query.message.edit_text(
                "📝 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
                "Шаг 1/8 — <b>Код промокода</b>\n"
                "<i>Только латиница, цифры, дефис. Будет преобразован в ВЕРХНИЙ РЕГИСТР.</i>\n\n"
                "Напиши код:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return await query.answer()

    if action == "deactivate_prompt":
        await state.set_state(None)
        try:
            await query.message.edit_text(
                "🔴 <b>Деактивировать промокод</b>\n\n"
                "Напиши код промокода для деактивации:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        await state.set_state(PromoCreate.code)
        await state.update_data(wizard_mode="deactivate")
        return await query.answer()

    if action == "activate_prompt":
        try:
            await query.message.edit_text(
                "🟢 <b>Активировать промокод</b>\n\n"
                "Напиши код промокода для повторной активации:",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        await state.set_state(PromoCreate.code)
        await state.update_data(wizard_mode="activate")
        return await query.answer()

    if action == "delete_prompt":
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
        await state.set_state(PromoCreate.code)
        await state.update_data(wizard_mode="delete")
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
            items_json=data.get("items_json", "{}"),
            max_activations=int(data.get("max_uses", 0)),
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
            created_by=query.from_user.id,
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
        if ok:
            await message.answer(f"🔴 Промокод <code>{code}</code> деактивирован.", parse_mode="HTML")
        else:
            await message.answer(f"❌ Промокод <code>{code}</code> не найден.", parse_mode="HTML")
        return

    if wizard_mode == "activate":
        ok = await promo_repo.activate_promocode_record(db, code)
        await state.clear()
        if ok:
            await message.answer(f"🟢 Промокод <code>{code}</code> активирован.", parse_mode="HTML")
        else:
            await message.answer(f"❌ Промокод <code>{code}</code> не найден.", parse_mode="HTML")
        return

    if wizard_mode == "delete":
        ok = await promo_repo.delete_promocode(db, code)
        await state.clear()
        if ok:
            await message.answer(f"🗑 Промокод <code>{code}</code> удалён.", parse_mode="HTML")
        else:
            await message.answer(f"❌ Промокод <code>{code}</code> не найден.", parse_mode="HTML")
        return

    # Create mode — validate code format
    import re
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
        f"Шаг 2/8 — <b>Описание</b>\n"
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
    data = await state.get_data()
    await message.answer(
        f"📝 Описание: <i>{safe_html(desc) or 'нет'}</i>\n\n"
        f"Шаг 3/8 — <b>Награда: Мора 🪙</b>\n"
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
        f"🪙 Мора: <code>{mora:,.2f}</code>\n\n"
        f"Шаг 4/8 — <b>Награда: Алмазы 💎</b>\n"
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
    await state.set_state(PromoCreate.items)
    items_example = ", ".join(f"<code>{k}</code>" for k in list(ITEMS_REGISTRY.keys())[:5])
    await message.answer(
        f"💎 Алмазы: <code>{diamonds:,.2f}</code>\n\n"
        f"Шаг 5/8 — <b>Предметы 📦</b>\n"
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
        import re
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
        f"Шаг 6/8 — <b>Лимит активаций</b>\n"
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
        f"Шаг 7/8 — <b>Дата начала</b>\n"
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
        f"Шаг 8/8 — <b>Дата окончания</b>\n"
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
    await state.update_data(valid_until=valid_until, wizard_mode="confirm")
    data = await state.get_data()

    items: dict = json.loads(data.get("items_json", "{}"))
    items_str = "\n".join(
        f"    ├ {ITEMS_REGISTRY.get(k, {}).get('name', k)} ×{v}" for k, v in items.items()
    ) if items else "    └ <i>нет</i>"
    if items and not items_str.endswith("</i>"):
        lines = items_str.split("\n")
        lines[-1] = lines[-1].replace("├", "└", 1)
        items_str = "\n".join(lines)

    max_uses = int(data.get("max_uses", 0))
    vf = data.get("valid_from") or "сразу"
    vu = valid_until or "бессрочно"

    summary = (
        f"📋 <b>ПОДТВЕРЖДЕНИЕ ПРОМОКОДА</b>\n\n"
        f"🎫 Код: <code>{data['code']}</code>\n"
        f"📝 Описание: <i>{safe_html(data.get('description', '')) or 'нет'}</i>\n\n"
        f"💰 <b>Награды:</b>\n"
        f"├ 🪙 Мора: <code>{float(data.get('mora', 0)):,.2f}</code>\n"
        f"├ 💎 Алмазы: <code>{float(data.get('diamonds', 0)):,.2f}</code>\n"
        f"└ 📦 Предметы:\n{items_str}\n\n"
        f"⚙️ <b>Настройки:</b>\n"
        f"├ 🔢 Лимит: <code>{'∞' if max_uses == 0 else max_uses}</code>\n"
        f"├ 📅 Начало: <code>{vf}</code>\n"
        f"└ 📅 Конец: <code>{vu}</code>\n\n"
        f"<b>Создаём промокод?</b>"
    )
    await message.answer(summary, reply_markup=_confirm_keyboard(), parse_mode="HTML")
