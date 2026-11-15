"""Addressed one-word turns and confirmed spelling suggestions for the shared game."""
import hashlib
import hmac
import html
from bisect import bisect_left

from aiogram import Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from loguru import logger
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyParameters

from bot.chat.framework import Ctx, Parsed, Unknown, parse, registry, topic_of
from bot.chat import ranks
from core import word_chain as rules
from services import feature_switches, global_moderation
from services import word_chain as game
from infrastructure.repositories import word_chain as repo

router = Router(name="word_chain")
HELP = ("🔤 <b>Слова</b> — игра против бота, одному или вместе.\n\n"
        "1. Начни: <code>бот слова</code>.\n"
        "2. Ход: <code>бот слово, арбуз</code> — замени «арбуз» словом на нужную букву.\n"
        "3. Или ответь на моё сообщение одним словом. Играть можно одному и вместе.\n\n"
        "Обычная переписка без команды или ответа игре ходом не считается.\n\n"
        "Ё = Е. В конце пропускаем Ь, Ъ, Ы и Й. Слова партии не повторяем. Между своими ходами — 3 секунды.\n"
        "При опечатке предложу близкие слова: выбери своё кнопкой.\n\n"
        "Принимаю настоящие русские слова и их формы.\n\n"
        "Твои сообщения идут в обычную норму; ответы бота и кнопки новых сообщений нормы не дают.\n\n"
        "<code>бот слова, подсказка</code> · <code>бот слова, счёт</code> · <code>бот слова, стоп</code>\n"
        "Без ходов 15 минут — партия завершится. В чате остаются 7 последних сообщений игры от бота. В каждой теме своя партия.")


SOLO_HELP = ("🔤 <b>Слова один на один</b> — ты и я, без чата.\n\n"
             "1. Начни: <code>слова</code>.\n"
             "2. Ход: просто напиши слово на нужную букву. Или ответь на моё сообщение — как удобнее.\n"
             "3. Если я промолчу на слово, напиши <code>бот слово, арбуз</code>.\n\n"
             "Ё = Е. В конце пропускаем Ь, Ъ, Ы и Й. Слова партии не повторяем. Между своими ходами — 3 секунды.\n"
             "При опечатке предложу близкие слова: выбери своё кнопкой.\n\n"
             "<code>бот слова, подсказка</code> · <code>бот слова, счёт</code> · <code>бот слова, стоп</code>\n"
             "Без ходов 15 минут — партия завершится. Остаются 7 последних сообщений игры от бота. Очков и наград игра не даёт.")


def prompt(state: dict, private: bool = False) -> str:
    word = state.get("bot_word") or state.get("last_word") or ""
    if state.get("paused"):
        return f"🔤 Партия на паузе: чат закрыт или идёт Мафия.\nПоследнее слово: <b>{html.escape(word)}</b>.\nСлова и счёт сохранятся."
    text = f"🔤 <b>{html.escape(word)}</b>\nТебе на <b>{state['letter'].upper()}</b>."
    if state.get("created"):
        how = "Напиши слово." if private else "Ответь словом или напиши <code>бот слово, СЛОВО</code>."
        text += f"\n{how}\nБез ходов 15 минут — конец игры. Оставляю 7 своих сообщений."
    return text


async def clean_messages(db, bot, *, chat_id: int | None = None, topic_id: int = 0) -> None:
    for chat_id, topic_id, message_id in await repo.stale_messages(db, chat_id, topic_id):
        release = getattr(db, "release_if_idle", None)
        if release:
            await release()
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest as error:
            if not any(reason in error.message.lower() for reason in ("message to delete not found", "message can't be deleted")):
                logger.warning("Word game deletion refused: chat={} message={} error={}", chat_id, message_id, error.message)
                continue
        except TelegramAPIError as error:
            logger.warning("Word game deletion will retry: chat={} message={} error={}", chat_id, message_id, type(error).__name__)
            continue
        await repo.forget_message(db, chat_id, topic_id, message_id)


async def remember_reply(db, bot, sent) -> None:
    await game.remember_message(db, chat_id=sent.chat.id, topic_id=topic_of(sent) or 0, message_id=sent.message_id)
    await clean_messages(db, bot, chat_id=sent.chat.id, topic_id=topic_of(sent) or 0)


async def reply(ctx: Ctx, text: str, **kwargs) -> None:
    sent = await ctx.reply(text, **kwargs)
    await remember_reply(ctx.db, ctx.bot, sent)


def word_input(state: dict) -> ForceReply | None:
    if state.get("paused"):
        return None
    return ForceReply(selective=True, input_field_placeholder=f"Одно слово на «{state['letter'].upper()}» — без команды")


def score(state: dict) -> str:
    return "\n".join(f"{i}. {html.escape(p['name'])} — {p['score']}" for i,p in enumerate(state.get("leaders",[]),1)) or "Пока нет принятых слов."


class WordFixCB(CallbackData, prefix="wf"):
    r: str
    t: str
    m: str
    w: str
    s: str


def _signature(bot, payload: str, actor: int, chat_id: int, topic_id: int, word: str) -> str:
    context = f"{payload}:{actor}:{chat_id}:{topic_id}:{word}".encode()
    return hmac.new(bot.token.encode(),context,hashlib.sha256).hexdigest()[:16]


def correction_keyboard(state: dict, message, bot) -> InlineKeyboardMarkup:
    buttons = []
    for word in state["candidates"]:
        fields = dict(r=f"{state['round_id']:x}",t=f"{state['turns']:x}",m=f"{message.message_id:x}",
                      w=f"{bisect_left(rules.SORTED_WORDS,word):x}")
        signature = _signature(bot,":".join(fields.values()),message.from_user.id,message.chat.id,topic_of(message) or 0,word)
        buttons.append([InlineKeyboardButton(text=word,callback_data=WordFixCB(**fields,s=signature).pack())])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def error_reply(db, message, bot, value: str, error: Exception) -> tuple[str, ForceReply | InlineKeyboardMarkup | None]:
    state = await game.spelling_help(db,chat_id=message.chat.id,topic_id=topic_of(message) or 0,value=value)
    text = "🔤 "+html.escape(str(error))
    if state["candidates"]:
        return text+"\nВыбери исправление:",correction_keyboard(state,message,bot)
    if state["active"]:
        return text+f"\nТебе на <b>{state['letter'].upper()}</b>.",word_input(state)
    return text,None


@registry.command("слова", aliases=("игра в слова",), private=True, section="games",
                  usage="бот слова [правила | счёт | подсказка | стоп]",
                  summary="Слова против бота: ход командой «бот слово, арбуз» или ответом на сообщение игры.")
async def command(ctx: Ctx) -> None:
    scope = dict(chat_id=ctx.message.chat.id,topic_id=topic_of(ctx.message) or 0)
    solo = is_solo(ctx.message)
    arg = rules.normalize(ctx.args)
    try:
        if arg in {"правила","помощь"}:
            await reply(ctx,SOLO_HELP if solo else HELP)
            return
        if arg in {"стоп","закончить","завершить"}:
            can_moderate = solo or await ranks.can(ctx.db,scope["chat_id"],ctx.user_id,"write_closed")
            state = await game.stop(ctx.db,**scope,actor=ctx.user_id,can_moderate=can_moderate)
            await reply(ctx,f"🔤 Партия завершена · принято слов: {state['turns']}\n"+score(state))
            return
        if arg in {"счет","статус","подсказка"}:
            state = await game.status(ctx.db,**scope,hint=arg=="подсказка")
            if not state["active"]:
                text = f"Последняя партия · принято слов: {state['turns']}\n"+score(state) if state.get("last_round") else "Игра сейчас не идёт."
                await reply(ctx,"🔤 "+text+"\nНачать: <code>бот слова</code>.")
                return
            text = prompt(state,solo)
            if arg=="подсказка":
                text += "\nМожно: "+", ".join(state["hints"])
            else:
                text += "\n\n<b>Счёт</b>\n"+score(state)
            await reply(ctx,text,reply_markup=word_input(state))
            return
        if arg and arg not in {"начать","старт"}:
            await reply(ctx,SOLO_HELP if solo else HELP)
            return
        state = await game.start(ctx.db,**scope,actor=ctx.user_id)
        await reply(ctx,prompt(state,solo),reply_markup=word_input(state))
    except game.WordChainError as error:
        await reply(ctx,"🔤 "+html.escape(str(error)))


@registry.command("слово", private=True, section="games", usage="бот слово, арбуз",
                  summary="Ход в словах: бот слово, арбуз. Можно и одним словом в ответ на сообщение игры.")
async def word(ctx: Ctx) -> None:
    await play_message(ctx.db,ctx.bot,ctx.message,ctx.args)


def is_solo(message) -> bool:
    """Личка с ботом: играет один человек, партия — его собственная."""
    return getattr(message.chat, "type", "") == "private"


def turn_reply(state: dict, solo: bool = False) -> tuple[str, ForceReply | None]:
    if state["finished"]:
        again = "<code>слова</code>" if solo else "<code>бот слова</code>"
        return (f"🔤 Вот это цепочка! Принято слов: {state['turns']}.\n"+score(state)+f"\nНовая партия: {again}.",None)
    return prompt(state,solo),word_input(state)


async def play_message(db, bot, message, value: str) -> None:
    try:
        state = await game.play(db,chat_id=message.chat.id,topic_id=topic_of(message) or 0,
                               actor=message.from_user.id,message_id=message.message_id,value=value)
        if state["replayed"]:
            return
        text,markup = turn_reply(state,is_solo(message))
    except game.WordChainError as error:
        text,markup = await error_reply(db,message,bot,value,error)
    sent = await message.reply(text,parse_mode="HTML",reply_markup=markup)
    await remember_reply(db, bot, sent)


def is_reply(bot, message) -> bool:
    reply = message.reply_to_message
    return bool(reply and reply.from_user and message.from_user and not message.from_user.is_bot
                and reply.from_user.id == bot.id and (reply.text or "").startswith("🔤")
                and message.text is not None)


async def on_plain_word(db, bot, message) -> bool:
    """Личка: в партии, где только что ходили, просто слово — это ход. Названия команд («баланс», «помощь») ходом не считаются."""
    text = (message.text or "").strip()
    if not is_solo(message) or not text or not message.from_user or message.from_user.is_bot:
        return False
    if not rules.WORD_RE.fullmatch(rules.normalize(text)):
        return False
    me = await bot.me()
    if parse(registry, text, me.username, True) is not None:
        return False
    try:
        if not await game.solo_turn_open(db,chat_id=message.chat.id,topic_id=topic_of(message) or 0):
            return False
    except game.WordChainError:
        return False
    if await feature_switches.disabled(db, feature_switches.command_features("слово", "games", None), message.chat.id) is not None:
        return True
    await play_message(db, bot, message, text)
    return True


async def on_reply(db, bot, message) -> bool:
    if not is_reply(bot, message):
        return False
    me = await bot.me()
    parsed = parse(registry, message.text, me.username)
    if isinstance(parsed, Unknown) or isinstance(parsed, Parsed) and parsed.prefixed:
        return False
    if await feature_switches.disabled(db, feature_switches.command_features("слово", "games", None), message.chat.id) is not None:
        return True
    await play_message(db, bot, message, message.text)
    return True


@router.callback_query(WordFixCB.filter())
async def confirm_spelling(cb: CallbackQuery, callback_data: WordFixCB, bot, db) -> None:
    if not isinstance(cb.message,Message) or cb.message.chat.id == 0:
        await cb.answer("Открой подсказку в исходном чате.",show_alert=True)
        return
    cid,topic,actor = cb.message.chat.id,topic_of(cb.message) or 0,cb.from_user.id
    fields = [callback_data.r,callback_data.t,callback_data.m,callback_data.w]
    try:
        rid,turn,mid,index = [int(part,16) for part in fields]
        if not (0<rid<2**63 and 0<=turn<=rules.MAX_TURNS and 0<mid<2**31 and 0<=index<len(rules.SORTED_WORDS)):
            raise ValueError("invalid correction scope")
        word = rules.SORTED_WORDS[index]
        expected = _signature(bot,":".join(fields),actor,cid,topic,word)
        if not hmac.compare_digest(callback_data.s,expected):
            raise ValueError("invalid correction signature")
    except (ValueError,TypeError):
        await cb.answer("Это подсказка для другого игрока или она устарела. Ответь своим словом на сообщение игры.",show_alert=True)
        return
    if (await global_moderation.is_blocked(db,actor)
            or await feature_switches.disabled(db,feature_switches.command_features("слово","games",None),cid) is not None):
        await cb.answer("Игра сейчас недоступна.",show_alert=True)
        return
    original = cb.message.model_copy(update={"message_id":mid,"from_user":cb.from_user})
    try:
        state = await game.play(db,chat_id=cid,topic_id=topic,actor=actor,message_id=mid,value=word,
                               expected_round=rid,expected_turn=turn)
        if state["replayed"]:
            await cb.answer("Этот ход уже учтён.")
            return
        text,markup = turn_reply(state,is_solo(cb.message))
        await cb.answer("Исправление принято!")
    except game.WordChainError as error:
        text,markup = await error_reply(db,original,bot,word,error)
        await cb.answer("Цепочка обновилась — смотри текущую букву.")
    mention = f'<a href="tg://user?id={actor}">{html.escape(cb.from_user.first_name)}</a>'
    sent = await cb.message.answer(text.replace("🔤 ",f"🔤 {mention}, ",1),parse_mode="HTML",reply_markup=markup,
                            reply_parameters=ReplyParameters(message_id=mid,allow_sending_without_reply=True))
    await remember_reply(db, bot, sent)
