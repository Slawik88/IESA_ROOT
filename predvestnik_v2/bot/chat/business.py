"""Бот в личных переписках игрока (Telegram Business): подключение и команды «бот …» владельца в его переписках.

Правила и проверки — в services/business.py: команду выполняет только сам игрок, подключивший бота, и только в переписке,
где он включил бота («бот вкл»), и только если эта функция включена в его настройках (S29a). Сообщения собеседника не
разбираются и не сохраняются; в журнал не пишется текст сообщений. Ответ бота в переписке Telegram показывает собеседнику
как сообщение от игрока. Деньги из переписки не списываются: перевод присылает игроку в личку обычную заявку с кнопками.
Пульт, настройки и игры вдвоём — bot/chat/business_remote.py и bot/chat/pair_cards.py.
"""
from __future__ import annotations

import html
import random

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, BusinessConnection, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from core import business as rules
from core import business_settings as features
from core.miniapp_links import miniapp_url
from core.economy_contract import CURRENCY_SPECS
from services import business as service

router = Router(name="chat_business")

HELP = ("💼 <b>Бот в твоих переписках</b>\n"
        "Пиши в переписке с другом своим сообщением. Собеседник команды не запустит.\n\n"
        "<b>Главное</b>\n"
        "<code>бот</code> — пульт этой переписки придёт сюда, в личку\n"
        "<code>бот вкл</code> / <code>бот выкл</code> — включить или выключить меня в этой переписке\n\n"
        "<b>Что умею</b>\n"
        "<code>бот сыграть</code> — игры вдвоём, можно на жетоны\n"
        "<code>бот кубик</code>, <code>бот выбери чай или кофе</code>, <code>бот совместимость</code>\n"
        "<code>бот визитка</code> — твоя карточка с образом\n"
        "<code>бот пригласить</code> — ссылка на игру для друга\n"
        "<code>бот перевод 100</code> — перевести другу; подтвердишь здесь, в личке\n\n"
        "Что можно, а что нет, решаешь ты: <code>бизнес</code> — общие настройки, «⚙️ Эта переписка» в пульте — для одной.\n"
        "Сообщения собеседника я не читаю и не храню.")

WELCOME = ("💼 <b>Я подключён к твоему аккаунту</b>\n"
           "Теперь я могу помогать в твоих личных переписках. Сам я там молчу.\n\n"
           "<b>Как включить</b>\n"
           "Открой переписку с другом и напиши своим сообщением <code>бот вкл</code>.\n\n"
           "<b>Что дальше</b>\n"
           "Напиши там <code>бот</code> — сюда придёт пульт: игры, кубик, визитка и другое. "
           "Что мне можно, настраивается командой <code>бизнес</code> здесь.\n\n"
           "Сообщения собеседников я не читаю и не храню. Отвечаю только на твои команды. "
           "Отключить меня совсем: «Настройки → Telegram для бизнеса → Чат-боты».")

NO_REPLY_RIGHT = ("💼 Мне нельзя писать в твоих переписках: при подключении не дано право отвечать.\n"
                  "Включи его: «Настройки → Telegram для бизнеса → Чат-боты» → я → «Управлять сообщениями».")

WINDOW = ("💼 Telegram не дал мне ответить в этой переписке.\n"
          "Я могу писать только там, где собеседник писал тебе за последние сутки. Попробуй, когда он ответит.")

FEATURE_OFF = "💼 Это выключено в твоих настройках для этой переписки. Включить: напиши там <code>бот</code> → «⚙️ Эта переписка»."
PARTNER_DECLINES = "🙅 Собеседник попросил не предлагать ему игры и приглашения через бота. Я уважаю его выбор."


@router.business_connection()
async def on_connection(connection: BusinessConnection, bot, db) -> None:
    """Игрок подключил, перенастроил или отключил бота. При отключении всё про эту связь удаляется."""
    can_reply = bool(connection.rights.can_reply) if connection.rights else bool(connection.can_reply)
    state = await service.remember_connection(db, connection_id=connection.id, user_id=connection.user.id,
                                              user_chat_id=connection.user_chat_id, enabled=connection.is_enabled,
                                              can_reply=can_reply)
    logger.info(f"business connection {state} for user {connection.user.id} (can_reply={can_reply})")
    if state != "new" or await service.switched_off(db) or not await service.owner_may_act(db, connection.user.id):
        return
    try:
        await bot.send_message(connection.user_chat_id, WELCOME if can_reply else WELCOME + "\n\n" + NO_REPLY_RIGHT, parse_mode="HTML")
    except TelegramAPIError as exc:   # игрок ещё не открывал личку с ботом: приветствие подождёт его первой команды
        logger.info(f"business welcome to {connection.user.id} not delivered: {exc}")


async def _connection(db, bot, connection_id: str) -> dict | None:
    """Связь из базы; если её нет (подключили до выпуска S24), спросить у Telegram и запомнить."""
    found = await service.owner_of(db, connection_id)
    if found is not None:
        return found
    try:
        live = await bot.get_business_connection(connection_id)
    except Exception as exc:   # Telegram не знает связь или недоступен: команду просто не выполняем
        logger.info(f"business connection {connection_id[:6]}… not loaded: {type(exc).__name__}: {exc}")
        return None
    await on_connection(live, bot, db)
    return await service.owner_of(db, connection_id)


@router.business_message()
async def on_business_message(message: Message, bot, db) -> None:
    """Сообщение из личной переписки игрока. Всё, что не команда самого игрока, пропускается без следа."""
    if not message.business_connection_id or message.from_user is None or not (message.text or "").lower().startswith(rules.PREFIX):
        return
    if await service.switched_off(db):
        return
    connection = await _connection(db, bot, message.business_connection_id)
    if connection is None or message.from_user.id != connection["user_id"] or not await service.owner_may_act(db, connection["user_id"]):
        return
    found = await service.command_for(db, connection=connection, sender_id=message.from_user.id, chat_id=message.chat.id,
                                      message_id=message.message_id, text=message.text,
                                      sent_by_bot=message.sender_business_bot is not None)
    if found is None:
        return
    action, args = found
    logger.info(f"business command {action} by {connection['user_id']}")   # без текста сообщения
    feature = features.ACTION_FEATURE.get(action)
    if feature and not await service.feature_on(db, connection, message.chat.id, feature):
        await to_owner(bot, connection, FEATURE_OFF)
        return
    if action in features.OFFER_ACTIONS and await service.partner_declines_offers(db, message.chat.id):
        await to_owner(bot, connection, PARTNER_DECLINES)
        return
    await _ACTIONS[action](bot, db, connection, message, args)


# ── ответы ──────────────────────────────────────────────────────────────────

async def to_owner(bot, connection: dict, text: str, **extra) -> bool:
    try:
        await bot.send_message(connection["user_chat_id"], text, parse_mode="HTML", **extra)
        return True
    except TelegramAPIError as exc:
        logger.info(f"business: owner DM {connection['user_id']} not delivered: {exc}")
        return False


async def in_chat(bot, connection: dict, chat_id: int, send):
    """Отправить в переписку от имени игрока; вернуть отправленное сообщение или None.
    Нет права или окно в сутки закрыто — объяснить игроку в личке."""
    if not connection["can_reply"]:
        await to_owner(bot, connection, NO_REPLY_RIGHT)
        return None
    try:
        return await send(chat_id=chat_id, business_connection_id=connection["id"])
    except TelegramAPIError as exc:
        logger.info(f"business reply in a chat of {connection['user_id']} failed: {exc}")
        await to_owner(bot, connection, WINDOW)
        return None


async def footer(db, connection: dict, chat_id: int, rows: list | None = None, *, offer_owner: int | None = None) -> InlineKeyboardMarkup | None:
    """Кнопки под карточкой: свои строки, «🙅 Не предлагать мне» (для предложений собеседнику) и «🔮 Предвестник»,
    если игрок не выключил эту кнопку."""
    rows = list(rows or [])
    if offer_owner is not None:
        rows.append([InlineKeyboardButton(text="🙅 Не предлагать мне", callback_data=f"bz:no:{int(offer_owner)}")])
    if await service.feature_on(db, connection, chat_id, "footer"):
        rows.append([InlineKeyboardButton(text="🔮 Предвестник", url=miniapp_url())])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def text_in_chat(bot, db, connection: dict, chat_id: int, text: str, *, offer: bool = False):
    markup = await footer(db, connection, chat_id, offer_owner=connection["user_id"] if offer else None)
    return await in_chat(bot, connection, chat_id, lambda **kw: bot.send_message(text=text, parse_mode="HTML", reply_markup=markup, **kw))


async def act_on(bot, db, connection, message, args) -> None:
    if not connection["can_reply"]:
        await to_owner(bot, connection, NO_REPLY_RIGHT)
        return
    if await service.set_chat(db, connection["id"], message.chat.id, True):
        await text_in_chat(bot, db, connection, message.chat.id, "💼 Бот Предвестника включён в этой переписке.")
    else:
        await to_owner(bot, connection, "💼 В той переписке я уже включён. Пульт — напиши там <code>бот</code>.")


async def act_off(bot, db, connection, message, args) -> None:
    if await service.set_chat(db, connection["id"], message.chat.id, False):
        await to_owner(bot, connection, "💼 В той переписке я выключен и снова молчу. Включить: <code>бот вкл</code> там же.")


async def act_help(bot, db, connection, message, args) -> None:
    """Подсказка уходит в личку игрока: в переписке её увидел бы собеседник."""
    enabled = await service.chat_enabled(db, connection["id"], message.chat.id)
    state = "В этой переписке я включён." if enabled else "В этой переписке я выключен: напиши там <code>бот вкл</code>."
    await to_owner(bot, connection, HELP + "\n\n" + state)


async def act_remote(bot, db, connection, message, args) -> None:
    from bot.chat import business_remote
    await business_remote.send_remote(bot, db, connection, message.chat)


async def act_games(bot, db, connection, message, args) -> None:
    from bot.chat import business_remote
    await business_remote.send_remote(bot, db, connection, message.chat, screen="games")


async def act_dice(bot, db, connection, message, args) -> None:
    await send_dice(bot, db, connection, message.chat.id)


async def send_dice(bot, db, connection: dict, chat_id: int) -> None:
    markup = await footer(db, connection, chat_id)
    await in_chat(bot, connection, chat_id, lambda **kw: bot.send_dice(emoji="🎲", reply_markup=markup, **kw))


async def act_choose(bot, db, connection, message, args) -> None:
    options = rules.choices(args)
    if not options:
        await to_owner(bot, connection, "💼 Напиши варианты через «или»: <code>бот выбери чай или кофе</code>.")
        return
    await text_in_chat(bot, db, connection, message.chat.id, f"🎯 Выбираю: <b>{html.escape(random.choice(options))}</b>")


async def act_compat(bot, db, connection, message, args) -> None:
    await send_compat(bot, db, connection, message.chat.id)


async def send_compat(bot, db, connection: dict, chat_id: int) -> None:
    from bot.chat.ship import _verdict_line
    from core import ship
    if await service.command_switched_off(db, "шипирить", "social", "ship"):
        await to_owner(bot, connection, "💞 Совместимость сейчас выключена администрацией.")
        return
    if await service.partner_opted_out_of_pairs(db, chat_id):   # собеседник попросил «не шипирить меня»: его выбор действует и здесь
        await to_owner(bot, connection, "💞 Собеседник попросил не выбирать его в пары, поэтому совместимость с ним я не считаю.")
        return
    low, high = sorted((int(connection["user_id"]), int(chat_id)))
    await text_in_chat(bot, db, connection, chat_id, _verdict_line(low, high, ship.compatibility_percent(low, high)), offer=True)


async def act_card(bot, db, connection, message, args) -> None:
    owner = message.from_user
    await send_card(bot, db, connection, message.chat.id, owner.id, owner.username, owner.full_name)


async def send_card(bot, db, connection: dict, chat_id: int, user_id: int, username: str | None, name: str) -> None:
    from bot.chat.profile import CAPTION_LIMIT, caption_len, visiting_card
    from bot.chat.targets import Target
    text, media = await visiting_card(db, Target(user_id, username, name))
    if media is None or caption_len(text) > CAPTION_LIMIT:
        await text_in_chat(bot, db, connection, chat_id, text)
        return
    kind, data, filename = media
    file = BufferedInputFile(data, filename=filename)
    method = bot.send_animation if kind == "animation" else bot.send_photo
    field = "animation" if kind == "animation" else "photo"
    markup = await footer(db, connection, chat_id)
    await in_chat(bot, connection, chat_id, lambda **kw: method(**{field: file}, caption=text, parse_mode="HTML", reply_markup=markup, **kw))


async def act_invite(bot, db, connection, message, args) -> None:
    await send_invite(bot, db, connection, message.chat.id)


async def send_invite(bot, db, connection: dict, chat_id: int) -> None:
    rows = [[InlineKeyboardButton(text="🎮 Открыть Предвестник", url=miniapp_url())]]
    await in_chat(bot, connection, chat_id, lambda **kw: bot.send_message(
        text="🔮 Играем вместе в Предвестник: ритм, сапёр, питомцы и образы прямо в Telegram.\n"
             f'Открыть игру: <a href="{html.escape(miniapp_url(), quote=True)}">Предвестник</a>',
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows + [[InlineKeyboardButton(
            text="🙅 Не предлагать мне", callback_data=f"bz:no:{int(connection['user_id'])}")]]), **kw))


async def act_transfer(bot, db, connection, message, args) -> None:
    """Заявка на перевод собеседнику. Деньги не трогаем: игрок выбирает валюту и подтверждает в личке с ботом."""
    from bot.chat import settings
    from bot.chat.transfer import TransferCB, fmt, parse_amount
    if await service.command_switched_off(db, "перевод", "profile"):
        await to_owner(bot, connection, "⛔ Переводы сейчас отключены.")
        return
    amount = parse_amount(args)
    if amount is None:
        await to_owner(bot, connection, "💸 Напиши сумму: <code>бот перевод 100</code> в переписке с другом.")
        return
    partner = message.chat
    who = html.escape(f"@{partner.username}" if partner.username else (partner.full_name or "собеседник"))
    status = await service.transfer_target(db, partner.id)
    if status == "stranger":
        await to_owner(bot, connection, f"💸 {who} ещё не играет в Предвестник: переводить некуда. "
                                        "Позови его в игру командой <code>бот пригласить</code> в переписке с ним.")
        return
    if status == "deleting":
        await to_owner(bot, connection, "⛔ Этот игрок удаляет аккаунт: переводить ему нельзя.")
        return
    codes = [c for c in await settings.transferable(db) if c in CURRENCY_SPECS]
    if not codes:
        await to_owner(bot, connection, "⛔ Переводы сейчас отключены.")
        return
    owner = int(connection["user_id"])
    buttons = [InlineKeyboardButton(text=f"{CURRENCY_SPECS[c].icon} {CURRENCY_SPECS[c].label}",
                                    callback_data=TransferCB(uid=owner, to=partner.id, amount=str(amount), cur=c).pack()) for c in codes]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data=TransferCB(uid=owner, to=partner.id, amount=str(amount), cur="x").pack())])
    asked = await to_owner(bot, connection,
                           f"💸 Перевод {who}: <b>{fmt(amount)}</b>\nЗаявка из вашей переписки. Деньги уйдут, только когда "
                           "выберешь валюту здесь. Какую валюту отправить?",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    if not asked:   # личка с ботом закрыта: подтвердить негде, сказать можно только в переписке
        await text_in_chat(bot, db, connection, partner.id, "💸 Перевод подтверждается в личке с ботом Предвестника: открой её и нажми «Старт».")


_ACTIONS = {"on": act_on, "off": act_off, "help": act_help, "remote": act_remote, "remote_here": act_remote, "games": act_games, "dice": act_dice,
            "choose": act_choose, "compat": act_compat, "card": act_card, "invite": act_invite, "transfer": act_transfer}
