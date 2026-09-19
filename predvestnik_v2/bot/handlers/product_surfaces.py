"""Low-complexity Telegram adapters for product surfaces shared with Mini App.

The adapters deliberately expose only status and safe one-tap preferences.
Inventory management, companion management and clan operations remain in the
Mini App and use the same database state shown here.
"""
from __future__ import annotations

import os

from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import NOTIFICATION_CATEGORIES
from core.registry import ACHIEVEMENTS, PET_SPECIES
from core.companions_v3 import EXPEDITION_DISCOVERY_TEXT
from core.surface_parity import surface
from infrastructure.repositories import achievements as achievements_repo
from infrastructure.repositories import notifications as notifications_repo
from infrastructure.repositories.economy import get_inventory
from services import clans as clans_service
from services import companions_v3 as companions_service
from services import feats_v1 as feats_service
from services import retention_v3 as retention_service
from services import weekly_case_v1 as weekly_case_service
from services import scar_map_v1 as scar_map_service
from services.inventory_resolve import item_display_name
from services.surface_telemetry import record_preference_change, record_surface_open
from services.utils import check_callback_owner, feature_guard, safe_html


router = Router(name="product_surfaces_router")
_BOT = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")


class NotificationCB(CallbackData, prefix="pref"):
    category: str
    enabled: int
    user_id: int


class CompanionCareCB(CallbackData, prefix="care"):
    action: str
    pet_id: int
    user_id: int


class CompanionSkinCB(CallbackData, prefix="cskin"):
    skin_id: str
    user_id: int


class WeeklyPathCB(CallbackData, prefix="wcase"):
    path_id: str
    case_token: str
    step: int
    user_id: int


def _web_button(surface_id: str, text: str = "🚀 Открыть подробнее") -> types.InlineKeyboardMarkup:
    spec = surface(surface_id)
    builder = InlineKeyboardBuilder()
    builder.button(text=text, url=f"https://t.me/{_BOT}?startapp={spec.start_param}")
    return builder.as_markup()


async def _notification_view(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    explicit = await notifications_repo.get_prefs(db, user_id)
    lines = [
        "🔔 <b>УВЕДОМЛЕНИЯ</b>",
        "<i>Настройки общие для чата и Mini App.</i>",
        "",
    ]
    builder = InlineKeyboardBuilder()
    for category, label in NOTIFICATION_CATEGORIES.items():
        enabled = explicit.get(category, True)
        lines.append(f"{'✅' if enabled else '🔕'} {label}")
        builder.button(
            text=f"{'Выключить' if enabled else 'Включить'} · {label}",
            callback_data=NotificationCB(
                category=category, enabled=0 if enabled else 1, user_id=user_id
            ),
        )
    builder.button(
        text="⚙️ Открыть все настройки",
        url=f"https://t.me/{_BOT}?startapp={surface('notifications').start_param}",
    )
    builder.adjust(1)
    return "\n".join(lines), builder.as_markup()


@router.message(TextCmd(list(surface("notifications").aliases)))
async def cmd_notifications(message: types.Message, db):
    text, keyboard = await _notification_view(db, int(message.from_user.id))
    await record_surface_open(db, int(message.from_user.id), "notifications", "telegram_chat")
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(NotificationCB.filter())
async def cb_notification(query: types.CallbackQuery, callback_data: NotificationCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    if callback_data.category not in NOTIFICATION_CATEGORIES:
        return await query.answer("Неизвестная настройка.", show_alert=True)
    if callback_data.enabled not in (0, 1):
        return await query.answer("Некорректное состояние настройки.", show_alert=True)
    enabled = bool(callback_data.enabled)
    await notifications_repo.set_pref(
        db, int(query.from_user.id), callback_data.category, enabled
    )
    await record_preference_change(
        db, int(query.from_user.id), callback_data.category, enabled, "telegram_chat"
    )
    text, keyboard = await _notification_view(db, int(query.from_user.id))
    try:
        await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await query.answer("Включено" if enabled else "Выключено")


@router.message(TextCmd(list(surface("inventory").aliases)))
async def cmd_inventory_summary(message: types.Message, db):
    rows = sorted(await get_inventory(db, int(message.from_user.id)), key=lambda r: (-int(r["quantity"]), str(r["item_id"])))
    total_items = sum(int(row["quantity"]) for row in rows)
    lines = [
        "🎒 <b>ИНВЕНТАРЬ</b>",
        f"Типов предметов: <b>{len(rows)}</b> · Всего: <b>{total_items}</b>",
        "",
    ]
    if rows:
        for row in rows[:8]:
            lines.append(f"• {safe_html(item_display_name(str(row['item_id'])))} ×<b>{int(row['quantity'])}</b>")
        if len(rows) > 8:
            lines.append(f"<i>…и ещё {len(rows) - 8} типов — полный список в Mini App.</i>")
    else:
        lines.append("<i>Пока пусто. Здесь появятся материалы и расходники.</i>")
    lines.append("\nИспользование и управление предметами остаются в Mini App.")
    await record_surface_open(db, int(message.from_user.id), "inventory", "telegram_chat")
    await message.answer("\n".join(lines), reply_markup=_web_button("inventory"), parse_mode="HTML")


@router.message(TextCmd(list(surface("achievements").aliases)))
async def cmd_achievement_summary(message: types.Message, db):
    chronicle = await feats_service.get_user_feats(db, int(message.from_user.id))
    saved = await achievements_repo.get_all_achievements(db, int(message.from_user.id))
    ranked = []
    for achievement_id, meta in ACHIEVEMENTS.items():
        state = saved.get(achievement_id, {"level": 0, "progress": 0})
        level = int(state.get("level") or 0)
        thresholds = meta["thresholds"]
        target = thresholds[level] if level < len(thresholds) else None
        ranked.append((level, float(state.get("progress") or 0), achievement_id, meta, target))
    ranked.sort(key=lambda row: (-row[0], row[4] is None, -(row[1] / row[4] if row[4] else 1)))
    unlocked = sum(1 for level, *_ in ranked if level > 0)
    lines = [
        "▤ <b>ХРОНИКА ПОДВИГОВ</b>",
        f"Открыто: <b>{chronicle['completed']}/{chronicle['total']}</b>",
        "<i>Подвиги отмечают путь и мастерство; валюты, силы и рейтинга за них нет.</i>",
        "",
    ]
    feats = sorted(chronicle["feats"], key=lambda item: (item["completed"], -item["pct"], item["order"]))
    for feat in feats[:5]:
        status = "готово" if feat["completed"] else f"{feat['progress']}/{feat['target']}"
        lines.append(f"{feat['icon']} {safe_html(feat['name'])} · <b>{status}</b>")
    lines.extend([
        "",
        f"🏆 Старый архив: <b>{unlocked}/{len(ACHIEVEMENTS)}</b>",
        "<i>Он сохранён как история и больше не растёт.</i>",
    ])
    await record_surface_open(db, int(message.from_user.id), "achievements", "telegram_chat")
    await message.answer("\n".join(lines), reply_markup=_web_button("achievements", "▤ Открыть Хронику"), parse_mode="HTML")


async def _rhythm_view(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    rhythm = await retention_service.overview(db, user_id)
    case = await weekly_case_service.overview(db, user_id)
    scar = await scar_map_service.overview(db, user_id, source="telegram_chat")
    selected = rhythm.get("selected_contract")
    lines = [
        "◌ <b>РИТМ</b>",
        (
            f"Сегодня: <b>{safe_html(str(selected['name']))}</b> · "
            f"{int(rhythm.get('progress') or 0)}/{int(rhythm.get('target') or 0)}"
            if selected else "Сегодняшнее намерение ещё не выбрано."
        ),
        "",
        f"▤ <b>{safe_html(str(case['title']))}</b> · {int(case['progress_days'])}/{int(case['target_days'])}",
        f"Архив дел: <b>{int((case.get('archive') or {}).get('completed_count') or 0)}/{int((case.get('archive') or {}).get('total') or 0)}</b>",
        "",
        f"✦ <b>Карта Шрамов</b> · {int(scar['unlocked_count'])}/{int(scar['final_required'])}",
        "Любые 9 из 12 узлов за 28 дней; Stars не ускоряют прогресс.",
    ]
    if case.get("catalog_completed"):
        latest = case.get("latest_completed") or {}
        if latest.get("finale"):
            lines.append(f"Последний финал: <b>{safe_html(str(latest['finale']['name']))}</b>")
    elif case.get("completed"):
        lines.append(f"Финал: <b>{safe_html(str(case['finale']['name']))}</b>")
    elif case.get("path_id"):
        path = next(item for item in case["paths"] if item["id"] == case["path_id"])
        lines.append(f"Путь: <b>{safe_html(str(path['name']))}</b>")
    else:
        lines.append("Выбери один из двух путей. Перед необратимым решением бот попросит подтверждение.")
    lines.append("<i>Дело не сгорает на границе недели; Stars не покупают прогресс.</i>")
    builder = InlineKeyboardBuilder()
    if not case.get("path_id"):
        for path in case["paths"]:
            builder.button(
                text=str(path["name"]),
                callback_data=WeeklyPathCB(path_id=str(path["id"]), case_token=str(case["case_token"]), step=0, user_id=user_id),
            )
    builder.button(text="◌ Открыть Ритм", url=f"https://t.me/{_BOT}?startapp={surface('rhythm').start_param}")
    builder.adjust(1)
    return "\n".join(lines), builder.as_markup()


@router.message(TextCmd(list(surface("rhythm").aliases)))
async def cmd_rhythm_summary(message: types.Message, db):
    text, keyboard = await _rhythm_view(db, int(message.from_user.id))
    await record_surface_open(db, int(message.from_user.id), "rhythm", "telegram_chat")
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(WeeklyPathCB.filter())
async def cb_weekly_path(query: types.CallbackQuery, callback_data: WeeklyPathCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    current = await weekly_case_service.overview(db, int(query.from_user.id))
    if str(current.get("case_token") or "") != callback_data.case_token:
        return await query.answer("Карточка устарела. Открой Ритм заново.", show_alert=True)
    if callback_data.path_id not in {str(item["id"]) for item in current.get("paths", [])}:
        return await query.answer("Неизвестный путь текущего Дела.", show_alert=True)
    if callback_data.step == 0:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="Подтвердить путь",
            callback_data=WeeklyPathCB(
                path_id=callback_data.path_id, case_token=callback_data.case_token,
                step=1, user_id=callback_data.user_id,
            ),
        )
        builder.button(
            text="Отмена",
            callback_data=WeeklyPathCB(
                path_id=callback_data.path_id, case_token=callback_data.case_token,
                step=-1, user_id=callback_data.user_id,
            ),
        )
        builder.adjust(1)
        await query.message.edit_reply_markup(reply_markup=builder.as_markup())
        return await query.answer("Путь необратим для этого Дела. Подтверди выбор.")
    if callback_data.step == 1:
        try:
            await weekly_case_service.choose_path(
                db, int(query.from_user.id), str(current["case_id"]), callback_data.path_id, source="telegram_chat"
            )
        except weekly_case_service.WeeklyCaseError as exc:
            return await query.answer(str(exc), show_alert=True)
        await query.answer("Путь сохранён")
    text, keyboard = await _rhythm_view(db, int(query.from_user.id))
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _companion_snapshot(db, user_id: int) -> dict:
    """Read the same v3 source used by Mini App, never the retired zoo tables."""
    return await companions_service.overview(db, user_id)


@router.message(TextCmd(list(surface("companions").aliases)))
async def cmd_companion_summary(message: types.Message, db):
    # Historical pet state stays in the database for the pre-release audit, but
    # no chat command may materialise or alter the retired system.
    del db
    await message.answer(
        "🐾 <b>ПИТОМЦЫ</b>\n\nНовая система питомцев ещё проектируется. "
        "Прежняя коллекция сохранена для будущей компенсации, но старый уход, роли и походы закрыты.",
        parse_mode="HTML",
    )
    return
    snapshot = await _companion_snapshot(db, int(message.from_user.id))
    pets = snapshot.get("pets") or []
    expedition_view = snapshot.get("expeditions") or {}
    expeditions = expedition_view.get("contracts") or []
    legacy_active = expedition_view.get("legacy_active") or []
    active = [pet for pet in pets if pet.get("active_companion")]
    lines = ["🐾 <b>СПУТНИКИ</b>", f"В коллекции: <b>{len(pets)}</b> · В походе: <b>{len(expeditions) + len(legacy_active)}</b>", ""]
    builder = InlineKeyboardBuilder()
    if active:
        pet = active[0]
        species = PET_SPECIES.get(str(pet.get("species_id")), {})
        lines.append(f"Активный: <b>{safe_html(str(pet.get('name') or species.get('name') or 'Спутник'))}</b>")
        legacy = pet.get("legacy") or {}
        lines.append(f"Уровень <b>{int(legacy.get('level') or 1)}</b> · {safe_html(str(species.get('rarity', pet.get('rarity', ''))))}")
        if int(pet.get("care_bank", 0)) > 0:
            for action in ("feed", "play", "groom"):
                label = {"feed": "🍖 Покормить", "play": "🎲 Поиграть", "groom": "🧽 Ухаживать"}[action]
                builder.button(text=label, callback_data=CompanionCareCB(action=action, pet_id=int(pet["id"]), user_id=int(message.from_user.id)))
        skins = snapshot.get("skins") or []
        selected_skin_id = str(snapshot.get("selected_skin_id") or "natural")
        selected_skin = next((item for item in skins if item.get("id") == selected_skin_id), None)
        if selected_skin:
            lines.append(f"Облик: <b>{safe_html(str(selected_skin.get('name') or 'Верный облик'))}</b>")
        for skin in skins:
            if skin.get("unlocked") and str(skin.get("id")) != selected_skin_id:
                builder.button(
                    text=f"{skin.get('mark') or '◌'} {skin.get('name')}",
                    callback_data=CompanionSkinCB(
                        skin_id=str(skin["id"]), user_id=int(message.from_user.id)
                    ),
                )
    elif pets:
        lines.append("<i>Активный спутник не выбран.</i>")
    else:
        lines.append("<i>Спутников пока нет.</i>")
    lines.append("\nКормление, размещение и развитие — в Mini App.")
    await record_surface_open(db, int(message.from_user.id), "companions", "telegram_chat")
    builder.button(text="🐾 Управлять спутниками", url=f"https://t.me/{_BOT}?startapp={surface('companions').start_param}")
    builder.adjust(1)
    await message.answer("\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(CompanionCareCB.filter())
async def cb_companion_care(query: types.CallbackQuery, callback_data: CompanionCareCB, db):
    del callback_data, db
    await query.answer("Старый уход за питомцами закрыт.", show_alert=True)
    return
    if not await check_callback_owner(query, callback_data.user_id):
        return
    try:
        result = await companions_service.care(
            db, int(query.from_user.id), int(callback_data.pet_id),
            callback_data.action,
            f"telegram:care:{query.message.chat.id}:{query.message.message_id}:{callback_data.pet_id}:{callback_data.action}"[:96],
            source="telegram_chat",
        )
    except companions_service.CompanionError as exc:
        return await query.answer(str(exc), show_alert=True)
    await query.answer(result.get("scene_text") or result.get("scene_hint") or "Связь выросла")
    snapshot = await _companion_snapshot(db, int(query.from_user.id))
    pets = snapshot.get("pets") or []
    expedition_view = snapshot.get("expeditions") or {}
    expeditions = expedition_view.get("contracts") or []
    legacy_active = expedition_view.get("legacy_active") or []
    active = [pet for pet in pets if pet.get("active_companion")]
    lines = ["🐾 <b>СПУТНИКИ</b>", f"В коллекции: <b>{len(pets)}</b> · В походе: <b>{len(expeditions) + len(legacy_active)}</b>", ""]
    if active:
        pet = active[0]
        lines.append(f"Активный: <b>{safe_html(str(pet.get('name') or 'Спутник'))}</b>")
    lines.append(f"✨ {safe_html(str(result.get('scene_text') or result.get('scene_hint') or 'Связь стала крепче.'))}")
    await query.message.edit_text("\n".join(lines), reply_markup=_web_button("companions", "🐾 Открыть спутников"), parse_mode="HTML")


@router.callback_query(CompanionSkinCB.filter())
async def cb_companion_skin(query: types.CallbackQuery, callback_data: CompanionSkinCB, db):
    del callback_data, db
    await query.answer("Старые облики питомцев закрыты.", show_alert=True)
    return
    if not await check_callback_owner(query, callback_data.user_id):
        return
    try:
        snapshot = await companions_service.select_skin(
            db, int(query.from_user.id), callback_data.skin_id, source="telegram_chat"
        )
    except companions_service.CompanionError as exc:
        return await query.answer(str(exc), show_alert=True)
    selected = next(
        (item for item in snapshot.get("skins") or [] if item.get("id") == snapshot.get("selected_skin_id")),
        None,
    )
    await query.answer("Облик выбран")
    await query.message.edit_text(
        "🐾 <b>СПУТНИКИ</b>\n\n"
        f"Облик активного спутника: <b>{safe_html(str((selected or {}).get('name') or 'Верный облик'))}</b>.\n"
        "Он не меняет характеристики или награды.",
        reply_markup=_web_button("companions", "🐾 Открыть спутников"),
        parse_mode="HTML",
    )


@router.message(TextCmd(list(surface("expeditions").aliases)))
async def cmd_expedition_summary(message: types.Message, db):
    del db
    await message.answer(
        "🗺 <b>ПОХОДЫ</b>\n\nСтарая система походов закрыта. Новые Походы и Экспедиции появятся вместе с утверждённой системой питомцев.",
        parse_mode="HTML",
    )
    return
    snapshot = await _companion_snapshot(db, int(message.from_user.id))
    expedition_view = snapshot.get("expeditions") or {}
    archive = snapshot.get("archive") or {}
    expeditions = expedition_view.get("contracts") or []
    legacy_active = expedition_view.get("legacy_active") or []
    lines = ["🗺 <b>ПОХОДЫ СПУТНИКОВ</b>", ""]
    if not expeditions and not legacy_active:
        lines.append("<i>Сейчас никто не в походе.</i>")
    for expedition in expeditions[:5]:
        remaining = int(expedition.get("remaining_sec") or 0)
        state = str(expedition.get("status") or "active")
        if state == "claimed":
            status = "📜 получено"
        elif state == "ready" or (state == "active" and remaining <= 0):
            status = "✅ готово"
        else:
            status = f"ещё {remaining // 3600}ч {(remaining % 3600) // 60}м"
        name = expedition.get("name") or PET_SPECIES.get(str(expedition.get("species_id")), {}).get("name", "Спутник")
        lines.append(f"• <b>{safe_html(str(name))}</b> — {status}")
        if state == "claimed":
            clue = EXPEDITION_DISCOVERY_TEXT.get(str(expedition.get("discovery_id")))
            if clue:
                lines.append(f"  <i>{safe_html(clue)}</i>")
    if legacy_active:
        lines.append("• <i>Старый поход сохраняется по прежнему договору; управление — в Mini App.</i>")
    if archive:
        lines.append(f"\n▤ <b>Архив находок: {int(archive.get('found') or 0)}/{int(archive.get('total') or 12)}</b>")
        for story_set in archive.get("sets") or []:
            marker = "✅" if story_set.get("completed") else "·"
            lines.append(
                f"{marker} {safe_html(str(story_set.get('name') or 'Набор'))}: "
                f"<b>{int(story_set.get('progress') or 0)}/{int(story_set.get('target') or 4)}</b>"
            )
    lines.append("\nЗапуск похода, раскрытие находки и полный Архив — в Mini App.")
    await record_surface_open(db, int(message.from_user.id), "expeditions", "telegram_chat")
    await message.answer("\n".join(lines), reply_markup=_web_button("expeditions", "🗺 Открыть походы"), parse_mode="HTML")


@router.message(TextCmd(list(surface("clans").aliases)))
async def cmd_clan_summary(message: types.Message, db):
    overview = await clans_service.get_overview(db, int(message.from_user.id))
    mine = overview.get("my_clan")
    lines = ["🛡 <b>КЛАНЫ</b>", ""]
    if mine:
        lines.extend([
            f"{mine.get('emblem', '🛡')} <b>{safe_html(str(mine['name']))}</b> [{safe_html(str(mine['tag']))}]",
            f"Уровень <b>{int(mine.get('level') or 1)}</b> · Участников <b>{len(mine.get('members') or [])}/{int(mine.get('effective_max') or overview.get('max_members') or 0)}</b>",
            f"Основание: <b>{int(mine.get('foundation_score') or 0)}</b>",
        ])
    else:
        lines.append("<i>Ты пока не в клане.</i>")
        top = overview.get("top") or []
        if top:
            lines.append("\n<b>Топ кланов:</b>")
            for index, clan in enumerate(top[:5], 1):
                lines.append(f"{index}. {safe_html(str(clan['name']))} [{safe_html(str(clan['tag']))}] · ур.{int(clan.get('level') or 1)}")
    lines.append("\nВступление, выход, создание и Бездна клана — в Mini App, чтобы исключить случайные действия в групповом чате.")
    await record_surface_open(db, int(message.from_user.id), "clans", "telegram_chat")
    await message.answer("\n".join(lines), reply_markup=_web_button("clans", "🛡 Открыть кланы"), parse_mode="HTML")
