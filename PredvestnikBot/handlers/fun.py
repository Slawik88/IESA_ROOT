"""
Весёлые команды: действия + система браков (с приглашениями).
"""
import html
import random
import time
from datetime import date  # noqa: F401 — may be used by proposal timeout checks

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import MARRIAGE_PROPOSAL_TIMEOUT
from database.db import create_marriage, delete_marriage, get_gifts_summary, get_marriage, get_mora, get_pet, get_user
from filters.bot_command import BotCommand, PlainCommand
from utils.helpers import format_duration, not_your_button, resolve_target, user_mention

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())


# ─── Тексты действий ──────────────────────────────────────────────────────────

_KICK = [
    "{a} пнул(а) {b} прямо в пятую точку! 👟",
    "{a} нанёс(ла) мощный пинок {b}! 🥾",
    "{a} разогнался(ась) и пнул(а) {b} со всей силы! 🏃💨",
    "{a} пнул(а) {b}... и, кажется, пожалел(а) об этом. 👟",
    "{a} метил(а) в {b}, но промахнулся(ась). {b} всё равно обиделся(ась). 👟",
]

_BITE = [
    "{a} укусил(а) {b}! 🦷",
    "{a} вцепился(ась) зубами в {b}! 😬",
    "{a} решил(а), что {b} выглядит вкусно, и укусил(а)! 🦷",
    "{a} тихонько цапнул(а) {b} за ухо. 😈",
    "АУЧ! {a} укусил(а) {b} без предупреждения! 🦷💥",
]

_HUG = [
    "{a} крепко обнял(а) {b}! 🤗",
    "{a} бросился(ась) обнимать {b}! 🤗✨",
    "Нежные объятия от {a} для {b}~ 💞",
    "{a} стиснул(а) {b} в медвежьих объятиях! 🐻",
    "{a} обнял(а) {b} и не хочет отпускать. 🤗💕",
]

_SLAP = [
    "{a} отвесил(а) {b} знатную пощёчину! 👋",
    "{a} шлёпнул(а) {b} газетой по голове. 📰",
    "{a} смачно приложил(а) {b}! 💥",
    "{a} влепил(а) {b} такую пощёчину, что в чате послышалось эхо. 👋",
]

_LICK = [
    "{a} лизнул(а) {b}! 👅",
    "{a} облизал(а) {b} от уха до уха. 😜",
    "{a} тихонько лизнул(а) {b} в щёчку. 👅",
    "{a}: *нямс* И что, {b}? Вкусный/ая! 😋",
]

_PAT = [
    "{a} погладил(а) {b} по голове. 🥹",
    "{a} потрепал(а) {b} по макушке. ✋",
    "{a}: *гладит {b}* 🫶",
    "{a} нежно потрепал(а) {b} по волосам. ☺️",
]

_THROW = [
    "{a} бросил(а) в {b} подушкой! 🛏",
    "{a} запустил(а) в {b} носком! 🧦",
    "{a} швырнул(а) в {b} печеньем. 🍪",
    "{a} метнул(а) в {b} банановую кожуру! 🍌",
]

_BONK = [
    "{a} ударил(а) {b} битой! 💥",
    "{a} нанёс(ла) мощный удар битой {b}! 🏏",
    "{a} забил(а) {b} по голове роликовыми коньками! ⛸️",
]

_POKE = [
    "{a} ткнул(а) {b} пальцем в грудь! 👉",
    "{a} тихонько ткнул(а) {b} в бок. 👉",
    "{a} провёл(а) пальцем по лицу {b}. 👉",
]

_KISS = [
    "{a} поцеловал(а) {b}! 💋",
    "{a} украл(а) поцелуй у {b}! 😘",
    "{a} нежно поцеловал(а) {b} в щёчку. 💕",
]

_HEAL = [
    "{a} исцелил(а) {b} светлой магией! ✨",
    "{a} наложил(а) исцеляющее заклинание на {b}! 🌟",
    "{a} вернул(а) {b} здоровье волшебством! 💚",
]

_SHOOT = [
    "{a} выстрелил(а) в {b} пистолетом (водяным)! 💦",
    "{a} запустил(а) в {b} арбалетом... с помидорами! 🍅",
    "{a} пролетел(а) над {b} на летающем ковре-самолёте и ударил(а) посохом! 🧙",
]


async def _action(
    message: Message,
    cmd_args: str,
    phrases: list[str],
    self_msg: str,
):
    uid, name, remaining = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return
    if uid == message.from_user.id:
        await message.answer(self_msg)
        return
    actor = user_mention(message.from_user.id, message.from_user.full_name)
    target = user_mention(uid, name)
    text = random.choice(phrases).format(a=actor, b=target)
    if remaining and remaining.strip():
        text += f'\n\n💬 <i>«{html.escape(remaining.strip())}»</i>'
    await message.answer(
        text,
        parse_mode="HTML",
    )


# ─── Команды действий ─────────────────────────────────────────────────────────

_BOT_ALIVE_PHRASES = [
    "👀 Да, я тут. Никуда не делся — сижу, наблюдаю...",
    "🫡 Здесь! Готов к бою. Ну или к выдаче моры, что в общем-то то же самое.",
    "💤 ...Буду тут. Никуда не ухожу. Просто дремал немного. В фоне.",
    "🤖 Онлайн. Перегрев CPU: 0%. Скучаю: 100%.",
    "🎩 О, вы написали «бот»! Блестяще. Продолжайте в том же духе.",
    "🦜 КТО? Я? ТУТ? Конечно тут. А ты как думал?",
    "⚡ Пинг — понг. Ответил быстрее, чем ты моргнул.",
    "🧠 Уже думаю над ответом. Подожди... подожди... Вот, придумал: «Я здесь».",
    "🏃 Никуда не ушёл. Хотя мог бы. Но не ушёл. Вот такой я.",
    "😤 Ты вообще в курсе, сколько дел я сейчас обрабатываю? Много. Но тебе всё равно отвечу.",
    "🕹 Нажми «бот» снова, ничего не произойдёт. Проверено. Я всё ещё тут.",
    "🥱 Зевал, но не ушёл. Дисциплина — мой средний класс.",
]

@router.message(F.text & F.text.lower() == "бот")
async def cmd_bot_ping(message: Message):
    await message.answer(random.choice(_BOT_ALIVE_PHRASES))


@router.message(PlainCommand("пни", "пнуть", "пинок"))
async def cmd_kick_fun(message: Message, cmd_args: str):
    await _action(message, cmd_args, _KICK, "❌ Себя пинать — больно и бесполезно!")


@router.message(PlainCommand("укуси", "укусить", "кусь"))
async def cmd_bite(message: Message, cmd_args: str):
    await _action(message, cmd_args, _BITE, "🦷 Кусать себя — это уже что-то новенькое...")


@router.message(PlainCommand("обними", "обнять", "hug"))
async def cmd_hug(message: Message, cmd_args: str):
    await _action(message, cmd_args, _HUG, "🤗 Ты обнял(а) самого себя. Всё норм, бывает!")


@router.message(PlainCommand("шлёпни", "шлепнуть", "шлёп"))
async def cmd_slap(message: Message, cmd_args: str):
    await _action(message, cmd_args, _SLAP, "😶 Шлёпать себя — это уже экстрим.")


@router.message(PlainCommand("лизни", "лизнуть", "лизь"))
async def cmd_lick(message: Message, cmd_args: str):
    await _action(message, cmd_args, _LICK, "😶 Себя лизать... нет.")


@router.message(PlainCommand("погладь", "погладить", "гладить"))
async def cmd_pat(message: Message, cmd_args: str):
    await _action(message, cmd_args, _PAT, "🥹 Ты погладил(а) себя по голове. Ну и молодец!")


@router.message(PlainCommand("кинь", "бросить", "кинуть"))
async def cmd_throw(message: Message, cmd_args: str):
    await _action(message, cmd_args, _THROW, "🤔 Бросаться в себя? Интересный выбор.")


@router.message(PlainCommand("бонк", "бить", "ударить"))
async def cmd_bonk(message: Message, cmd_args: str):
    await _action(message, cmd_args, _BONK, "🏏 Ударить себя битой? Может, позже...")


@router.message(PlainCommand("ткни", "ткнуть", "тыкать"))
async def cmd_poke(message: Message, cmd_args: str):
    await _action(message, cmd_args, _POKE, "👉 Тыкаешь себе в грудь? Странно.")


@router.message(PlainCommand("поцелуй", "целовать", "целоваться"))
async def cmd_kiss(message: Message, cmd_args: str):
    await _action(message, cmd_args, _KISS, "😶 Целовать себя? Скромничаешь?")


@router.message(PlainCommand("вылечи", "исцелить", "heal"))
async def cmd_heal(message: Message, cmd_args: str):
    await _action(message, cmd_args, _HEAL, "💚 Исцелил(а) себя! Молодец, забота о здоровье!")


@router.message(PlainCommand("выстрели", "стрелять", "shoot"))
async def cmd_shoot(message: Message, cmd_args: str):
    await _action(message, cmd_args, _SHOOT, "💦 Выстрелил(а) в себя? Может, нужна помощь?")


# ─── Брак (с приглашениями) ────────────────────────────────────────────────────

# Ожидающие предложения: {(proposer_id, target_id, chat_id): monotonic_timestamp}
_proposals: dict[tuple[int, int, int], float] = {}


@router.message(BotCommand("брак", "жениться", "замуж", "женить", "поженимся", "marry"))
async def cmd_marry(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("💍 Брак доступен только в группах.")
        return
    from filters.feature_flag import feature_enabled
    if not await feature_enabled(message, "marriages"):
        return

    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return
    if uid == message.from_user.id:
        await message.answer("❌ На себе жениться нельзя!")
        return

    me_id = message.from_user.id
    chat_id = message.chat.id

    my_marriage = await get_marriage(me_id, chat_id)
    if my_marriage:
        partner = await get_user(my_marriage["partner_id"])
        p_name = partner["full_name"] if partner else "?"
        await message.answer(
            f"💍 Ты уже состоишь в браке с {user_mention(my_marriage['partner_id'], p_name)}!\n"
            f"Сначала введи <code>бот развод</code>, если хочешь разойтись.",
            parse_mode="HTML",
        )
        return

    their_marriage = await get_marriage(uid, chat_id)
    if their_marriage:
        await message.answer(
            f"💔 {user_mention(uid, name)} уже состоит в браке в этом чате.",
            parse_mode="HTML",
        )
        return

    # Проверяем дублирующее предложение
    key = (me_id, uid, chat_id)
    if key in _proposals and time.monotonic() - _proposals[key] < MARRIAGE_PROPOSAL_TIMEOUT:
        await message.answer("⏳ Ты уже отправил предложение! Подожди ответа.")
        return

    _proposals[key] = time.monotonic()

    actor = user_mention(me_id, message.from_user.full_name)
    target = user_mention(uid, name)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💍 Принять",
                callback_data=f"marry:y:{me_id}:{uid}",
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"marry:n:{me_id}:{uid}",
            ),
        ]
    ])

    await message.answer(
        f"💍 <b>Предложение руки и сердца!</b>\n\n"
        f"{actor} предлагает {target} пожениться! 💕\n\n"
        f"<i>{html.escape(name)}, нажми кнопку ниже чтобы ответить "
        f"(⏳ {MARRIAGE_PROPOSAL_TIMEOUT} сек.)</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("marry:"))
async def on_marry_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("❌ Некорректные данные.", show_alert=True)
        return

    action = parts[1]
    try:
        proposer_id = int(parts[2])
        target_id = int(parts[3])
    except ValueError:
        await callback.answer("❌ Некорректные данные.", show_alert=True)
        return

    chat_id = callback.message.chat.id

    # Только цель может ответить
    if await not_your_button(callback, target_id, "❌ Это предложение не для тебя!"):
        return

    key = (proposer_id, target_id, chat_id)

    # Проверяем истечение
    if key not in _proposals or time.monotonic() - _proposals[key] > MARRIAGE_PROPOSAL_TIMEOUT:
        _proposals.pop(key, None)
        await callback.answer("⏳ Предложение истекло.", show_alert=True)
        try:
            await callback.message.edit_text("⏳ Предложение истекло.")
        except Exception as _e:
            _log.debug("%s", _e)
        return

    _proposals.pop(key, None)

    proposer = await get_user(proposer_id)
    p_name = proposer["full_name"] if proposer else "?"
    target_user = await get_user(target_id)
    t_name = target_user["full_name"] if target_user else callback.from_user.full_name

    if action == "y":
        # Ещё раз проверяем браки (вдруг кто-то женился параллельно)
        if await get_marriage(proposer_id, chat_id) or await get_marriage(target_id, chat_id):
            try:
                await callback.message.edit_text("❌ Один из участников уже состоит в браке.")
            except Exception as _e:
                _log.debug("%s", _e)
            await callback.answer()
            return

        try:
            await create_marriage(proposer_id, target_id, chat_id)
        except Exception as _err:
            import logging as _log
            import traceback as _tb
            _tb_text = _tb.format_exc()
            _log.getLogger(__name__).error("create_marriage failed: %s", _err, exc_info=True)
            try:
                from database.db import log_app_error
                await log_app_error("bot", "on_marry_callback/create_marriage", str(_err), _tb_text,
                                    user_id=target_id, chat_id=chat_id)
            except Exception as _e:
                _log.debug("%s", _e)
            await callback.answer("❌ Произошла ошибка при регистрации брака. Попробуйте снова.", show_alert=True)
            return
        icon = random.choice(["💍", "💒", "🥂", "💖", "🎊"])
        try:
            await callback.message.edit_text(
                f"{icon} <b>Свадьба!</b>\n\n"
                f"{user_mention(proposer_id, p_name)} и {user_mention(target_id, t_name)} "
                f"теперь в браке! 🎉\n"
                f"Желаем счастья и любви! 💕",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e)
    else:
        try:
            await callback.message.edit_text(
                f"💔 {user_mention(target_id, t_name)} отклонил(а) предложение "
                f"{user_mention(proposer_id, p_name)}...\n"
                f"<i>Может быть, в другой раз.</i>",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e)

    await callback.answer()


@router.message(BotCommand("развод", "divorce", "разойтись"))
async def cmd_divorce(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("💔 Эта команда доступна только в группах.")
        return
    from filters.feature_flag import feature_enabled
    if not await feature_enabled(message, "marriages"):
        return

    me_id = message.from_user.id
    chat_id = message.chat.id
    marriage = await get_marriage(me_id, chat_id)
    if not marriage:
        await message.answer("🤷 Ты не состоишь в браке в этом чате.")
        return

    partner = await get_user(marriage["partner_id"])
    p_name = partner["full_name"] if partner else "?"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💔 Да, развестись", callback_data=f"div:y:{me_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"div:n:{me_id}"),
    ]])
    await message.answer(
        f"⚠️ <b>Подтверждение развода</b>\n\n"
        f"Ты уверен(а), что хочешь развестись с {user_mention(marriage['partner_id'], p_name)}?\n"
        f"<i>Это действие нельзя отменить.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(BotCommand("пара", "моя пара", "партнёр", "partner"))
async def cmd_partner(message: Message, cmd_args: str):
    me_id = message.from_user.id
    chat_id = message.chat.id

    marriage = await get_marriage(me_id, chat_id)
    if not marriage:
        await message.answer(
            "💔 Ты не состоишь в браке в этом чате.\n"
            "Найди свою половинку: <code>бот брак @username</code>",
            parse_mode="HTML",
        )
        return

    partner = await get_user(marriage["partner_id"])
    p_name = partner["full_name"] if partner else "?"
    p_id = marriage["partner_id"]
    _mat = marriage["married_at"]
    # married_at may come back as a datetime object from asyncpg; normalise to ISO string
    married_at_iso = _mat.isoformat() if hasattr(_mat, 'isoformat') else str(_mat or "")
    married_at_date = married_at_iso[:10]
    together = format_duration(married_at_iso) if married_at_iso else "?"

    # Check if couple has a pet
    pet = await get_pet(me_id, chat_id)
    pet_info = ""
    if pet:
        pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
        pet_name = pet["name"] if pet.get("name") else "без имени"
        pet_age = format_duration(pet["adopted_at"])
        pet_info = f"\n🐾 Питомец: {pet_emoji} <b>{html.escape(pet_name)}</b> ({pet_age})"

    # Статистика подарков
    gift_count, gift_total = await get_gifts_summary(me_id, p_id, chat_id)
    gift_info = ""
    if gift_count > 0:
        gift_info = f"\n🎁 Подарков: <b>{gift_count}</b> (на {gift_total} 🪙)"

    await message.answer(
        f"💍 <b>Твоя пара</b>\n\n"
        f"❤️ Партнёр: {user_mention(p_id, p_name)}\n"
        f"📅 Вместе с: {married_at_date}\n"
        f"🗓 Вместе: <b>{together}</b>"
        f"{pet_info}"
        f"{gift_info}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤗 Обнять",
                    callback_data=f"act:hug:{p_id}",
                ),
                InlineKeyboardButton(
                    text="🐾 Питомец",
                    callback_data=f"pair:pet:{me_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💔 Развестись",
                    callback_data=f"div:ask:{me_id}",
                ),
            ],
        ]),
    )



@router.callback_query(F.data.startswith("div:"))
async def cb_divorce(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    uid = int(parts[2])

    if await not_your_button(callback, uid, "❌ Это не твой развод!"):
        return

    chat_id = callback.message.chat.id

    if action == "n":
        try:
            await callback.message.edit_text("💕 Развод отменён. Любовь побеждает! ❤️")
        except Exception as _e:
            _log.debug("%s", _e)
        await callback.answer()
        return

    if action == "ask":
        marriage = await get_marriage(uid, chat_id)
        if not marriage:
            await callback.answer("🤷 Ты не в браке.", show_alert=True)
            return
        partner = await get_user(marriage["partner_id"])
        p_name = partner["full_name"] if partner else "?"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💔 Да, развестись", callback_data=f"div:y:{uid}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"div:n:{uid}"),
        ]])
        try:
            await callback.message.edit_text(
                f"⚠️ <b>Подтверждение развода</b>\n\n"
                f"Ты уверен(а), что хочешь развестись с {user_mention(marriage['partner_id'], p_name)}?\n"
                f"<i>Это действие нельзя отменить.</i>",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as _e:
            _log.debug("%s", _e)
        await callback.answer()
        return

    # action == "y"
    marriage = await get_marriage(uid, chat_id)
    if not marriage:
        await callback.answer("🤷 Ты уже не в браке.", show_alert=True)
        try:
            await callback.message.edit_text("🤷 Ты уже не в браке.")
        except Exception as _e:
            _log.debug("%s", _e)
        return

    partner = await get_user(marriage["partner_id"])
    p_name = partner["full_name"] if partner else "?"
    await delete_marriage(uid, chat_id)
    try:
        await callback.message.edit_text(
            f"💔 {user_mention(uid, callback.from_user.full_name)} и "
            f"{user_mention(marriage['partner_id'], p_name)} развелись...\n"
            f"<i>Ничто не вечно.</i>",
            parse_mode="HTML",
        )
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()


@router.callback_query(F.data.startswith("pair:pet:"))
async def cb_pair_pet(callback: CallbackQuery):
    """Show pet status from the couple view."""
    uid = int(callback.data.split(":")[2])
    if await not_your_button(callback, uid, "🚫 Это не твой профиль!"):
        return
    chat_id = callback.message.chat.id
    pet = await get_pet(uid, chat_id)
    if pet:
        from handlers.pets import _PET_EMOJI, _PET_NAME
        from utils.helpers import format_duration
        ptype = pet["pet_type"]
        emoji = _PET_EMOJI.get(ptype, "🐾")
        kind  = _PET_NAME.get(ptype, "Питомец")
        import html as _html
        name  = _html.escape(pet["name"]) if pet.get("name") else "<i>без имени</i>"
        age   = format_duration(pet["adopted_at"])
        await callback.answer(
            f"{emoji} {kind}: {pet.get('name') or 'без имени'}\n🎂 Возраст: {age}",
            show_alert=True,
        )
    else:
        from handlers.pets import PET_MIN_MARRIAGE_DAYS, PET_MORA_SKIP_PRICE, _marriage_age_days
        marriage = await get_marriage(uid, chat_id)
        age_days = _marriage_age_days(marriage["married_at"]) if marriage else 0
        left = max(0, PET_MIN_MARRIAGE_DAYS - age_days)
        if left == 0:
            await callback.answer(
                "🎉 Условия выполнены!\n"
                "Напиши бот завести питомца чтобы выбрать.",
                show_alert=True,
            )
        else:
            mora = await get_mora(uid, chat_id)
            bal = mora["balance"] if mora else 0
            await callback.answer(
                f"🐾 Питомца нет\n"
                f"Брак: {age_days}/{PET_MIN_MARRIAGE_DAYS} дн. (осталось {left} дн.)\n"
                f"Или заплати {PET_MORA_SKIP_PRICE} 🪙 (у тебя {bal} 🪙)\n"
                f"→ напиши бот питомец",
                show_alert=True,
            )


@router.callback_query(F.data.startswith("act:hug:"))
async def cb_hug_partner(callback: CallbackQuery):
    target_id = int(callback.data.split(":")[2])
    user = callback.from_user
    target = await get_user(target_id)
    t_name = target["full_name"] if target else "?"
    phrase = random.choice(_HUG)
    text = phrase.format(
        a=user_mention(user.id, user.full_name),
        b=user_mention(target_id, t_name),
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
