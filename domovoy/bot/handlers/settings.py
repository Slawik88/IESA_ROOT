"""
bot/handlers/settings.py — настройки дома, персональные уведомления, права,
категории, привязка чата, ссылка-приглашение.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import cb, keyboards as kb
from bot.states import CategoryAdd
from bot.util import guard, resolve_house, safe_edit
from core import settings_registry as reg
from services import households, money
from services import settings as settings_service

router = Router(name="settings")


async def _house_of(tg_id: int):
    return await resolve_house(tg_id)


# ── Корень настроек ──────────────────────────────────────────────────────────

@router.callback_query(F.data == cb.settings_root())
@guard
async def settings_root(cbq: CallbackQuery, state: FSMContext = None):
    if state is not None:
        await state.clear()
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    is_owner = await households.can(house["id"], cbq.from_user.id, "manage_house_settings")
    await safe_edit(cbq, "⚙️ Настройки",
                    kb.settings_root_keyboard(is_owner, chat_bound=house["chat_id"] is not None))
    await cbq.answer()


# ── Настройки дома (генерируются из реестра) ─────────────────────────────────

@router.callback_query(F.data == cb.settings_house())
@guard
async def settings_house(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_house_settings")
    values = await settings_service.house_settings(house["id"])
    await safe_edit(cbq, "🏠 Настройки дома — нажмите, чтобы изменить:",
                    kb.house_settings_keyboard(values))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^st_h:([a-z_]+)$"))
@guard
async def settings_house_tap(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_house_settings")
    key = cb.parse(cbq.data)[1]
    definition = reg.HOUSE_SETTING_BY_KEY[key]
    value = await settings_service.house_setting(house["id"], key)
    if definition.kind == "bool":
        await settings_service.set_house_setting(house["id"], key, not value)
        values = await settings_service.house_settings(house["id"])
        await safe_edit(cbq, "🏠 Настройки дома — нажмите, чтобы изменить:",
                        kb.house_settings_keyboard(values))
        await cbq.answer("Сохранено")
        return
    await safe_edit(cbq, f"{definition.label} — выберите значение:",
                    kb.house_setting_choices_keyboard(key, definition.choices))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^st_hv:([a-z_]+):(-?\d+)$"))
@guard
async def settings_house_value(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_house_settings")
    parts = cb.parse(cbq.data)
    key, index = parts[1], int(parts[2])
    definition = reg.HOUSE_SETTING_BY_KEY[key]
    await settings_service.set_house_setting(house["id"], key, definition.choices[index])
    values = await settings_service.house_settings(house["id"])
    await safe_edit(cbq, "🏠 Настройки дома — нажмите, чтобы изменить:",
                    kb.house_settings_keyboard(values))
    await cbq.answer("Сохранено")


# ── Персональные уведомления ─────────────────────────────────────────────────

@router.callback_query(F.data == cb.settings_notify())
@guard
async def settings_notify(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    is_owner = await households.can(house["id"], cbq.from_user.id, "manage_house_settings")
    values = await settings_service.notify_settings(house["id"], cbq.from_user.id)
    await safe_edit(cbq, "🔔 Ваши уведомления — нажмите, чтобы переключить личка → чат → выкл:",
                    kb.notify_settings_keyboard(values, is_owner))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^st_n:([a-z_]+)$"))
@guard
async def settings_notify_cycle(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    key = cb.parse(cbq.data)[1]
    values = await settings_service.notify_settings(house["id"], cbq.from_user.id)
    current = values[key]
    next_channel = reg.NOTIFY_CHANNELS[(reg.NOTIFY_CHANNELS.index(current) + 1) % len(reg.NOTIFY_CHANNELS)]
    await settings_service.set_notify_setting(house["id"], cbq.from_user.id, key, next_channel)
    values = await settings_service.notify_settings(house["id"], cbq.from_user.id)
    is_owner = await households.can(house["id"], cbq.from_user.id, "manage_house_settings")
    await safe_edit(cbq, "🔔 Ваши уведомления — нажмите, чтобы переключить личка → чат → выкл:",
                    kb.notify_settings_keyboard(values, is_owner))
    await cbq.answer(reg.channel_label(next_channel))


# ── Права участников ─────────────────────────────────────────────────────────

@router.callback_query(F.data == cb.settings_perms())
@guard
async def settings_perms(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_members")
    candidates = await households.grantor_candidates(house["id"], cbq.from_user.id)
    text = ("Выберите участника и выдайте ему права.\n"
            "Владельцу права не нужны — у него всё и так есть.")
    if not candidates:
        text = "Пока некого назначать: в доме только вы."
    await safe_edit(cbq, text, kb.perm_members_keyboard(candidates))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^st_perm_m:(\d+)$"))
@guard
async def settings_perm_member(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_members")
    tg_id = int(cb.parse(cbq.data)[1])
    member = await households.membership(house["id"], tg_id)
    if member is None:
        await cbq.answer("Участник не найден", show_alert=True)
        return
    grants = await households.grants_of(house["id"], tg_id)
    await safe_edit(cbq, f"Права участника «{member['display_name']}»:",
                    kb.perm_toggle_keyboard(member, grants))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^st_perm_t:(\d+):([a-z_]+)$"))
@guard
async def settings_perm_toggle(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_members")
    parts = cb.parse(cbq.data)
    tg_id, code = int(parts[1]), parts[2]
    grants = await households.grants_of(house["id"], tg_id)
    await households.set_grant(house["id"], tg_id, code, code not in grants)
    member = await households.membership(house["id"], tg_id)
    grants = await households.grants_of(house["id"], tg_id)
    await safe_edit(cbq, f"Права участника «{member['display_name']}»:",
                    kb.perm_toggle_keyboard(member, grants))
    await cbq.answer("Сохранено")


# ── Категории ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == cb.settings_categories())
@guard
async def settings_categories(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_categories")
    categories = await money.categories(house["id"])
    await safe_edit(cbq, "🏷 Категории трат. 🗑 — удалить (нельзя, если есть траты):",
                    kb.categories_manage_keyboard(categories))
    await cbq.answer()


@router.callback_query(F.data == cb.category_add())
@guard
async def category_add_start(cbq: CallbackQuery, state: FSMContext):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_categories")
    await state.set_state(CategoryAdd.waiting_name)
    await state.update_data(house_id=house["id"])
    await cbq.message.answer("Название новой категории:")
    await cbq.answer()


@router.message(CategoryAdd.waiting_name, F.text)
@guard
async def category_add_named(message: Message, state: FSMContext):
    data = await state.get_data()
    house = await households.get_house(data["house_id"])
    await money.add_category(house["id"], message.text)
    await state.clear()
    await message.answer(f"Категория «{message.text.strip()}» добавлена.",
                         reply_markup=kb.back_to_menu())


@router.callback_query(F.data.regexp(r"^st_cat_del:(\d+)$"))
@guard
async def category_delete(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_categories")
    category_id = int(cb.parse(cbq.data)[1])
    await money.remove_category(house["id"], category_id)
    categories = await money.categories(house["id"])
    await safe_edit(cbq, "🏷 Категории трат. 🗑 — удалить (нельзя, если есть траты):",
                    kb.categories_manage_keyboard(categories))
    await cbq.answer("Удалено")


# ── Привязка чата и приглашение ──────────────────────────────────────────────

@router.callback_query(F.data == cb.settings_bind_chat())
@guard
async def bind_chat(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_house_settings")
    if cbq.message.chat.type == "private":
        await cbq.answer("Привязать можно только чат, где есть бот: откройте эту кнопку "
                         "внутри группы.", show_alert=True)
        return
    await households.set_chat_id(house["id"], cbq.message.chat.id)
    await cbq.answer("Чат привязан к дому!", show_alert=True)
    await settings_root(cbq, None)


@router.callback_query(F.data == cb.settings_invite())
@guard
async def show_invite(cbq: CallbackQuery):
    house = await _house_of(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_members")
    me = await cbq.bot.me()
    link = households.invite_link(house, me.username)
    await safe_edit(cbq,
                    f"💌 Ссылка-приглашение в «{house['name']}»:\n{link}\n\n"
                    "Перешлите её жильцам. Устаревшую ссылку можно заменить кнопкой ниже.",
                    kb.invite_keyboard(link))
    await cbq.answer()
