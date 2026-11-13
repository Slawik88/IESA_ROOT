"""Пульт и настройки бота в переписках (S29a). Всё это живёт в личке игрока с ботом: собеседник пульт не видит.

Пульт приходит по слову «бот» в переписке. Кнопка пульта отправляет в переписку карточку (игра, кубик, визитка…).
Настройки: «бизнес» в личке — общие для всех переписок; «⚙️ Эта переписка» в пульте — для одной (как в общих → вкл → выкл).
Кнопки пульта нажимает только владелец связи: номер пульта проверяется по нему (services/business.remote).
"""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Chat, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.chat import business as chat
from bot.chat.framework import Ctx, registry
from core import business_settings as features
from core import pair_games as game_rules
from core.miniapp_links import miniapp_url
from services import business as service
from services import pair_games

router = Router(name="chat_business_remote")

ACTIONS = ("games", "dice", "compat", "card", "invite")
LABELS = {"games": "🎮 Сыграть", "dice": "🎲 Кубик", "compat": "💞 Совместимость", "card": "🪪 Визитка", "invite": "🔮 Позвать в игру"}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _name(chat_obj: Chat) -> str:
    return f"@{chat_obj.username}" if chat_obj.username else (chat_obj.full_name or "собеседник")


async def send_remote(bot, db, connection: dict, partner: Chat, *, screen: str = "main") -> None:
    """Пульт переписки — в личку игрока."""
    rid = await service.remote_for(db, connection["id"], partner.id, _name(partner))
    found = await service.remote(db, rid, connection["user_id"])
    text, markup = await (_games_view(db, found) if screen == "games" else _main_view(db, found))
    await chat.to_owner(bot, connection, text, reply_markup=markup)


async def _main_view(db, found: dict) -> tuple[str, InlineKeyboardMarkup]:
    connection, chat_id, rid = found["connection"], found["chat_id"], found["remote_id"]
    name = html.escape(found["partner_name"])
    head = f"🎛 <b>Пульт переписки с {name}</b>"
    if not await service.chat_enabled(db, connection["id"], chat_id):
        return (f"{head}\nЗдесь я выключен и молчу.",
                InlineKeyboardMarkup(inline_keyboard=[[_btn("✅ Включить здесь", f"bp:{rid}:on")],
                                                      [_btn("⚙️ Общие настройки", f"bp:{rid}:glob")]]))
    declines = await service.partner_declines_offers(db, chat_id)
    player = await service.is_player(db, chat_id)
    allowed = []
    for action in ACTIONS:
        if not await service.feature_on(db, connection, chat_id, features.ACTION_FEATURE[action]):
            continue
        if declines and action in features.OFFER_ACTIONS:
            continue
        allowed.append(action)
    ordered = await service.action_order(db, connection["user_id"], allowed)
    if not player and "invite" in ordered:   # друг ещё не играет — позвать его важнее всего
        ordered = ["invite"] + [a for a in ordered if a != "invite"]
    lines = [head, "Жми кнопку — карточка придёт в вашу переписку."]
    if declines:
        lines.append(f"🙅 {name} попросил не предлагать ему игры и приглашения — их здесь нет.")
    elif not player:
        lines.append(f"{name} пока не играет в Предвестник: на жетоны с ним не сыграть, но можно просто так или позвать его.")
    buttons = [_btn(LABELS[a], f"bp:{rid}:{a}") for a in ordered]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([_btn("⚙️ Эта переписка", f"bp:{rid}:cfg"), _btn("⏻ Выключить здесь", f"bp:{rid}:off")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _games_view(db, found: dict) -> tuple[str, InlineKeyboardMarkup]:
    rid = found["remote_id"]
    rows = [[_btn(title, f"bp:{rid}:g:{kind}")] for kind, title in game_rules.KINDS.items()]
    rows.append([_btn("‹ Пульт", f"bp:{rid}:main")])
    return f"🎮 <b>Во что играем с {html.escape(found['partner_name'])}?</b>", InlineKeyboardMarkup(inline_keyboard=rows)


async def _stake_view(db, found: dict, kind: str) -> tuple[str, InlineKeyboardMarkup]:
    connection, chat_id, rid = found["connection"], found["chat_id"], found["remote_id"]
    rows = [[_btn("🤝 Просто так", f"bp:{rid}:s:{kind}:-:0")]]
    lines = [f"{game_rules.KINDS[kind]}", "На что играем?"]
    if await service.feature_on(db, connection, chat_id, "bets") and await service.is_player(db, chat_id):
        have = await pair_games.chip_balance(db, connection["user_id"])
        lines.append(f"У тебя: 🎁 {have['bonus']} бесплатных и 💰 {have['redeemable']} купленных жетонов.")
        lines.append("Победитель забирает обе ставки. Бесплатные выигрываются бесплатными, купленные — купленными.")
        rows.append([_btn(f"🎁 {n}", f"bp:{rid}:s:{kind}:b:{n}") for n in game_rules.STAKES])
        rows.append([_btn(f"💰 {n}", f"bp:{rid}:s:{kind}:r:{n}") for n in game_rules.STAKES])
        rows.append([InlineKeyboardButton(text="🛒 Жетоны — в Зале Фортуны", url=miniapp_url("games"))])
    rows.append([_btn("‹ Игры", f"bp:{rid}:games")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _chat_settings_view(db, found: dict) -> tuple[str, InlineKeyboardMarkup]:
    connection, chat_id, rid = found["connection"], found["chat_id"], found["remote_id"]
    own = await service.chat_overrides(db, connection["id"], chat_id)
    common = await service.global_settings(db, connection["user_id"])
    rows = []
    for key in features.ORDER:
        state = ("вкл" if own[key] else "выкл") if key in own else f"как в общих ({'вкл' if common[key] else 'выкл'})"
        rows.append([_btn(f"{features.FEATURES[key][0]}: {state}", f"bp:{rid}:c:{key}")])
    rows.append([_btn("‹ Пульт", f"bp:{rid}:main")])
    return (f"⚙️ <b>Переписка с {html.escape(found['partner_name'])}</b>\n"
            "Нажимай, чтобы менять: как в общих → вкл → выкл. Общие настройки — команда <code>бизнес</code>."), \
        InlineKeyboardMarkup(inline_keyboard=rows)


def _global_view(values: dict[str, bool]) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["💼 <b>Бот в переписках: что мне можно</b>",
             "Это общие настройки для всех твоих переписок. Для одной переписки — «⚙️ Эта переписка» в её пульте.", ""]
    rows = []
    for key in features.ORDER:
        title, hint, _ = features.FEATURES[key]
        lines.append(f"{'✅' if values[key] else '▫️'} {title} — {hint}")
        rows.append([_btn(f"{'✅' if values[key] else '▫️'} {title}", f"bs:{key}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit(message: Message, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


# ── кнопки пульта ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bp:"))
async def on_remote(call: CallbackQuery, bot, db) -> None:
    parts = (call.data or "").split(":")
    msg = call.message
    if len(parts) < 3 or not parts[1].isdigit() or not isinstance(msg, Message):
        await call.answer()
        return
    found = await service.remote(db, int(parts[1]), call.from_user.id)
    if found is None or msg.chat.id != found["connection"]["user_chat_id"]:
        await call.answer("Этот пульт больше не работает: напиши «бот» в переписке, придёт новый.", show_alert=True)
        return
    if await service.switched_off(db) or not await service.owner_may_act(db, call.from_user.id):
        await call.answer("Бот в переписках сейчас выключен.", show_alert=True)
        return
    connection, chat_id, action = found["connection"], found["chat_id"], parts[2]
    if action == "main":
        await _edit(msg, *(await _main_view(db, found)))
    elif action == "on":
        if not connection["can_reply"]:
            await call.answer("Сначала дай мне право отвечать: «Настройки → Telegram для бизнеса → Чат-боты».", show_alert=True)
            return
        await service.set_chat(db, connection["id"], chat_id, True)
        await _edit(msg, *(await _main_view(db, found)))
    elif action == "off":
        await service.set_chat(db, connection["id"], chat_id, False)
        await _edit(msg, *(await _main_view(db, found)))
    elif action == "cfg":
        await _edit(msg, *(await _chat_settings_view(db, found)))
    elif action == "c" and len(parts) == 4 and parts[3] in features.FEATURES:
        await service.cycle_chat(db, connection["id"], chat_id, parts[3])
        await _edit(msg, *(await _chat_settings_view(db, found)))
    elif action == "glob":
        text, markup = _global_view(await service.global_settings(db, connection["user_id"]))
        await chat.to_owner(bot, connection, text, reply_markup=markup)
    elif not await service.chat_enabled(db, connection["id"], chat_id):
        await call.answer("В этой переписке я выключен.", show_alert=True)
        return
    elif action == "games":
        if not await _allowed(db, call, connection, chat_id, "games"):
            return
        await _edit(msg, *(await _games_view(db, found)))
    elif action == "g" and len(parts) == 4 and parts[3] in game_rules.KINDS:
        if not await _allowed(db, call, connection, chat_id, "games"):
            return
        await _edit(msg, *(await _stake_view(db, found, parts[3])))
    elif action == "s" and len(parts) == 6:
        if not await _allowed(db, call, connection, chat_id, "games"):
            return
        await _start_game(call, bot, db, found, kind=parts[3], fund=parts[4], stake=parts[5])
        return
    elif action in ("dice", "compat", "card", "invite"):
        if not await _allowed(db, call, connection, chat_id, action):
            return
        await service.count_use(db, connection["user_id"], action)
        if action == "dice":
            await chat.send_dice(bot, db, connection, chat_id)
        elif action == "compat":
            await chat.send_compat(bot, db, connection, chat_id)
        elif action == "card":
            owner = call.from_user
            await chat.send_card(bot, db, connection, chat_id, owner.id, owner.username, owner.full_name)
        else:
            await chat.send_invite(bot, db, connection, chat_id)
        await call.answer("Отправил в переписку.")
        return
    await call.answer()


async def _allowed(db, call: CallbackQuery, connection: dict, chat_id: int, action: str) -> bool:
    if not await service.feature_on(db, connection, chat_id, features.ACTION_FEATURE[action]):
        await call.answer("Это выключено в настройках этой переписки.", show_alert=True)
        return False
    if action in features.OFFER_ACTIONS and await service.partner_declines_offers(db, chat_id):
        await call.answer("Собеседник попросил не предлагать ему игры и приглашения.", show_alert=True)
        return False
    return True


async def _start_game(call: CallbackQuery, bot, db, found: dict, *, kind: str, fund: str, stake: str) -> None:
    from bot.chat import pair_cards
    connection, chat_id = found["connection"], found["chat_id"]
    funds = {"b": "bonus", "r": "redeemable"}.get(fund)
    amount = int(stake) if stake.isdigit() else -1
    if kind not in game_rules.KINDS or amount < 0 or (amount and funds is None):
        await call.answer()
        return
    if amount and not (await service.feature_on(db, connection, chat_id, "bets") and await service.is_player(db, chat_id)):
        await call.answer("Игры на жетоны здесь недоступны.", show_alert=True)
        return
    names = {"owner": call.from_user.full_name or "Игрок", "partner": found["partner_name"]}
    try:
        from bot.chat import settings
        game = await pair_games.invite(db, connection_id=connection["id"], chat_id=chat_id, owner_id=connection["user_id"],
                                       partner_id=chat_id, kind=kind, stake=amount, funds=funds, names=names,
                                       mora_transferable="mora" in await settings.transferable(db))
    except pair_games.MoveError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await service.count_use(db, connection["user_id"], "games")
    if not await pair_cards.post(bot, db, connection, game):
        await pair_games.cancel(db, game["id"], "cancelled")
        await call.answer("Не получилось отправить карточку — я написал почему.", show_alert=True)
        return
    await _edit(call.message, f"✅ Позвал {html.escape(found['partner_name'])}: {game_rules.KINDS[kind]}. Карточка — в вашей переписке.",
                InlineKeyboardMarkup(inline_keyboard=[[_btn("‹ Пульт", f"bp:{found['remote_id']}:main")]]))
    await call.answer("Карточка в переписке.")


# ── общие настройки ─────────────────────────────────────────────────────────

@registry.command("бизнес", aliases=("бот в переписках", "настройки бизнеса"), section="basic",
                  summary="Бот в твоих переписках (Telegram для бизнеса): что ему можно делать.", usage="бот бизнес", example="бот бизнес")
async def cmd_business(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private":
        await ctx.reply("💼 Настройки бота в переписках — в личке со мной: напиши там «бизнес».")
        return
    text, markup = _global_view(await service.global_settings(ctx.db, ctx.user_id))
    await ctx.message.answer(text + "\n\nПодключить меня к своим перепискам: «Настройки Telegram → Telegram для бизнеса → Чат-боты» "
                                    "(нужен Telegram Premium).", parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("bs:"))
async def on_global_setting(call: CallbackQuery, db) -> None:
    key = (call.data or "")[3:]
    msg = call.message
    if key not in features.FEATURES or not isinstance(msg, Message) or msg.chat.id != call.from_user.id:
        await call.answer()
        return
    value = await service.toggle_global(db, call.from_user.id, key)
    text, markup = _global_view(await service.global_settings(db, call.from_user.id))
    await _edit(msg, text, markup)
    await call.answer("Включено." if value else "Выключено.")


# ── «Не предлагать мне» — выбор собеседника ─────────────────────────────────

@router.callback_query(F.data.startswith("bz:no:"))
async def on_partner_optout(call: CallbackQuery, db) -> None:
    owner = (call.data or "").split(":")[2]
    if owner.isdigit() and int(owner) == call.from_user.id:
        await call.answer("Эта кнопка — для собеседника: так он может попросить не предлагать ему игры.", show_alert=True)
        return
    await service.set_partner_optout(db, call.from_user.id, True)
    await call.answer("Хорошо: тебе больше не будут предлагать игры и приглашения через бота Предвестника. "
                      "Передумаешь — напиши боту «предлагать мне».", show_alert=True)


@registry.command("предлагать мне", aliases=("не предлагать мне",), section="basic",
                  summary="Разрешить или запретить предлагать тебе игры через бота в личных переписках.",
                  usage="предлагать мне / не предлагать мне", example="предлагать мне")
async def cmd_offers(ctx: Ctx) -> None:
    refuse = ctx.message.text and "не предлагать" in ctx.message.text.lower()
    await service.set_partner_optout(ctx.db, ctx.user_id, bool(refuse))
    await ctx.reply("🙅 Готово: игры и приглашения через бота тебе больше не предлагают. Вернуть: «предлагать мне»." if refuse
                    else "🤝 Готово: друзья снова могут звать тебя в игры через бота. Запретить: «не предлагать мне».")
