# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import DUEL_MIN_BET, DUEL_MAX_BET
from core.registry import PET_SPECIES
from infrastructure.repositories import zoo as zoo_db
from infrastructure.repositories.moderation import get_chat_settings
from infrastructure.repositories.chat import get_chat_stats
from services import global_moderation
from services.duel import create_challenge, accept_duel, decline_duel
from services.utils import safe_html, resolve_target, resolve_display_name
from services.achievements import increment_metric
from bot.keyboards.cta import answer_group_only

router = Router(name="duel_router")


class DuelCB(CallbackData, prefix="duel"):
    action: str   # "accept" | "decline"
    duel_id: int


@router.message(TextCmd(["дуэль", "дuel", "pvp"]))
async def cmd_duel(message: types.Message, db, text_args: str = None,
                    user_restricted: dict | None = None, chat_restricted: dict | None = None):
    if message.chat.type == "private":
        return await answer_group_only(message)

    restriction = user_restricted or chat_restricted
    if restriction:
        return await message.answer(global_moderation.restriction_message(restriction))

    challenger_id = message.from_user.id
    chat_id = message.chat.id

    settings = await get_chat_settings(db, chat_id)
    rank_required = settings.get("rank_duel", 0)
    if rank_required > 0:
        u_stats = await get_chat_stats(db, challenger_id, chat_id)
        if u_stats.get("local_rank", 0) < rank_required:
            from services import roles as _roles
            rname = _roles.LOCAL_RANKS_MAP.get(rank_required, f"Ранг {rank_required}")
            return await message.answer(
                f"❌ Дуэли в этом чате доступны с ранга <b>{rname}</b> ({rank_required}+).",
                parse_mode="HTML",
            )

    # Parse: "@target, stake" or "stake, @target"
    raw = text_args or ""
    parts = [p.strip() for p in raw.split(",")]
    target_arg = None
    stake_arg = None
    for p in parts:
        if p.startswith("@") or p.isdigit():
            target_arg = p
        else:
            try:
                float(p); stake_arg = p
            except ValueError:
                if not target_arg:
                    target_arg = p

    if not stake_arg:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот дуэль, @юзер, [ставка]</code>\n"
            f"<i>Ставка обязательна: от {int(DUEL_MIN_BET)} до {int(DUEL_MAX_BET)} Моры.</i>",
            parse_mode="HTML",
        )

    try:
        stake = float(stake_arg)
    except ValueError:
        return await message.answer("❌ Ставка должна быть числом.", parse_mode="HTML")

    if stake < DUEL_MIN_BET:
        return await message.answer(f"❌ Минимальная ставка: <code>{int(DUEL_MIN_BET)} 🪙</code>.", parse_mode="HTML")
    if stake > DUEL_MAX_BET:
        return await message.answer(f"❌ Максимальная ставка: <code>{int(DUEL_MAX_BET)} 🪙</code>.", parse_mode="HTML")

    # Resolve target
    target_id, target_name, _ = await resolve_target(message, db, target_arg)
    if not target_id:
        return await message.answer("❌ Укажите цель или ответьте на сообщение.", parse_mode="HTML")
    if target_id == challenger_id:
        return await message.answer("❌ Нельзя вызвать себя на дуэль.", parse_mode="HTML")

    # Anti-abuse: both players must have at least 50 messages in this chat
    async with db.execute(
        "SELECT user_messages_count_all_time FROM user_chat_stats "
        "WHERE user_tg_id = ? AND chat_tg_id = ?",
        (challenger_id, chat_id),
    ) as c:
        row = await c.fetchone()
    if not row or row[0] < 50:
        return await message.answer(
            "❌ Для дуэли нужно написать не менее 50 сообщений в этом чате.",
            parse_mode="HTML",
        )
    async with db.execute(
        "SELECT user_messages_count_all_time FROM user_chat_stats "
        "WHERE user_tg_id = ? AND chat_tg_id = ?",
        (target_id, chat_id),
    ) as c:
        row = await c.fetchone()
    if not row or row[0] < 50:
        return await message.answer(
            f"❌ {safe_html(target_name)} должен(а) написать не менее 50 сообщений в этом чате.",
            parse_mode="HTML",
        )

    # Check active pet for challenger
    challenger_pet_rows = await zoo_db.get_user_pets(db, challenger_id, placement="active")
    if not challenger_pet_rows:
        return await message.answer("❌ Нет активного питомца! Назначьте его через <code>бот зоопарк</code>.", parse_mode="HTML")
    challenger_pet = challenger_pet_rows[0]

    ok, result = await create_challenge(db, challenger_id, target_id, chat_id, stake, challenger_pet)
    if not ok:
        return await message.answer(f"❌ {result}", parse_mode="HTML")

    duel_id = result["duel_id"]
    challenger_name = await resolve_display_name(db, challenger_id, chat_id, message.from_user.first_name)
    target_disp = await resolve_display_name(db, target_id, chat_id, target_name)

    pet_sp = PET_SPECIES.get(challenger_pet.get("species_id", ""), {})
    pet_name_str = f"{pet_sp.get('name', '?')} Lv{challenger_pet.get('pet_level') or 1}"

    b = InlineKeyboardBuilder()
    b.button(text="✅ Принять", callback_data=DuelCB(action="accept", duel_id=duel_id))
    b.button(text="❌ Отказаться", callback_data=DuelCB(action="decline", duel_id=duel_id))
    b.adjust(2)

    await message.answer(
        f"⚔️ <b>ВЫЗОВ НА ДУЭЛЬ!</b>\n\n"
        f"<b>{challenger_name}</b> вызывает <b>{target_disp}</b>!\n\n"
        f"├ 🐾 Питомец: <b>{pet_name_str}</b>\n"
        f"├ 💰 Ставка: <code>{stake:.0f} 🪙</code> с каждого\n"
        f"└ ⏳ Ответить в течение 60 сек\n\n"
        f"<i>{target_disp}, принять вызов?</i>",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(DuelCB.filter(F.action == "accept"))
async def cb_duel_accept(query: types.CallbackQuery, callback_data: DuelCB, db):
    user_id = query.from_user.id
    duel_id = callback_data.duel_id

    from infrastructure.repositories.duel import get_duel
    duel = await get_duel(db, duel_id)
    if not duel:
        await query.answer()
        return await query.message.edit_text("❌ Вызов не найден или истёк.", parse_mode="HTML")
    if duel["status"] != "pending":
        await query.answer()
        return await query.message.edit_text("❌ Вызов уже завершён.", parse_mode="HTML")
    if duel["challenged_id"] != user_id:
        # L7: фидбэк вместо «мёртвой кнопки» при клике не тем игроком
        return await query.answer("❌ Этот вызов адресован не вам.", show_alert=True)
    await query.answer()

    # Check active pet for challenged
    challenged_pet_rows = await zoo_db.get_user_pets(db, user_id, placement="active")
    if not challenged_pet_rows:
        return await query.message.edit_text(
            "❌ У вас нет активного питомца! Назначьте его через <code>бот зоопарк</code>.",
            parse_mode="HTML",
        )
    challenged_pet = challenged_pet_rows[0]

    ok, result = await accept_duel(db, duel_id, challenged_pet)
    if not ok:
        return await query.message.edit_text(f"❌ {result}", parse_mode="HTML")

    chat_id = duel["chat_id"]
    w_name = await resolve_display_name(db, result["winner_id"], chat_id, f"ID{result['winner_id']}")

    ch_id = duel["challenger_id"]
    cd_id = duel["challenged_id"]
    ch_name = await resolve_display_name(db, ch_id, chat_id, f"ID{ch_id}")
    cd_name = await resolve_display_name(db, cd_id, chat_id, f"ID{cd_id}")

    async def _pet_str(pet_rows, user_id):
        pets = await zoo_db.get_user_pets(db, user_id, placement="active")
        if not pets:
            return "?"
        p = pets[0]
        sp = PET_SPECIES.get(p.get("species_id", ""), {})
        lvl = p.get("pet_level") or 1
        return f"{sp.get('name', '?')} Lv{lvl}"

    ch_pet_str = await _pet_str(None, ch_id)
    cd_pet_str = challenged_pet.get("species_id", "?")
    sp = PET_SPECIES.get(challenged_pet.get("species_id", ""), {})
    cd_pet_str = f"{sp.get('name', '?')} Lv{challenged_pet.get('pet_level') or 1}"

    # Wire achievements
    await increment_metric(db, result["winner_id"], "duel_wins", delta=1.0)
    await db.commit()

    text = (
        f"⚔️ <b>РЕЗУЛЬТАТЫ ДУЭЛИ!</b>\n\n"
        f"├ <b>{ch_name}</b>: 🐾 {ch_pet_str} · сила <code>{result['challenger_power']:.1f}</code>\n"
        f"├ <b>{cd_name}</b>: 🐾 {cd_pet_str} · сила <code>{result['challenged_power']:.1f}</code>\n\n"
        f"🏆 Победитель: <b>{w_name}</b>!\n"
        f"└ +<code>{result['winner_gain']:.0f} 🪙</code> (комиссия {result['commission']:.0f} 🪙)"
    )
    await query.message.edit_text(text, parse_mode="HTML")


@router.callback_query(DuelCB.filter(F.action == "decline"))
async def cb_duel_decline(query: types.CallbackQuery, callback_data: DuelCB, db):
    user_id = query.from_user.id

    from infrastructure.repositories.duel import get_duel
    duel = await get_duel(db, callback_data.duel_id)
    if not duel or duel["status"] != "pending":
        await query.answer()
        return await query.message.edit_text("❌ Вызов уже завершён.", parse_mode="HTML")

    if duel["challenged_id"] != user_id and duel["challenger_id"] != user_id:
        # L7: фидбэк вместо «мёртвой кнопки»
        return await query.answer("❌ Это не ваша дуэль.", show_alert=True)
    await query.answer()

    await decline_duel(db, callback_data.duel_id)
    decliner_name = await resolve_display_name(db, user_id, duel["chat_id"], f"ID{user_id}")
    await query.message.edit_text(
        f"❌ <b>{decliner_name}</b> отказался(ась) от дуэли. Ставки возвращены.",
        parse_mode="HTML",
    )
