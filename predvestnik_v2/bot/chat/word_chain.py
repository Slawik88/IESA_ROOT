"""Addressed one-word turns and confirmed spelling suggestions for the shared game."""
import hashlib
import hmac
import html
from bisect import bisect_left

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyParameters

from bot.chat.framework import Ctx, Parsed, Unknown, parse, registry
from bot.chat import ranks
from core import word_chain as rules
from services import feature_switches, global_moderation
from services import word_chain as game

router = Router(name="word_chain")
HELP = ("🔤 <b>Слова</b> — игра против бота, одному или вместе.\n\n"
        "1. Начни: <code>бот слова</code>.\n"
        "2. Telegram откроет ответ боту. Напиши только существительное на нужную букву — без команды.\n"
        "3. После моего хода ответ откроется снова. Остальные могут присоединиться, один раз ответив на сообщение игры.\n\n"
        "Если ответ закрылся, снова выбери «Ответить» на моём слове. Обычная переписка без ответа игре ходом не считается.\n\n"
        "Ё = Е. В конце пропускаем Ь, Ъ, Ы и Й. Слова партии не повторяем. Между своими ходами — 3 секунды.\n"
        "При опечатке предложу близкие слова: выбери своё кнопкой.\n\n"
        "Твои сообщения идут в обычную норму; ответы бота и кнопки новых сообщений нормы не дают.\n\n"
        "<code>бот слова, подсказка</code> · <code>бот слова, счёт</code> · <code>бот слова, стоп</code>\n"
        "После суток без ходов можно начать заново. В каждой теме своя партия.")
REACTIONS = ("Мой ответ готов!", "Хорошее слово, продолжаем!", "Принимаю! Теперь мой ход.",
             "Есть такое! Лови следующее.", "Цепочка растёт!", "А я отвечу вот так.")


def prompt(state: dict) -> str:
    word = state.get("bot_word") or state.get("last_word") or ""
    if state.get("paused"):
        return f"🔤 Партия на паузе: чат закрыт или идёт Мафия.\nПоследнее слово: <b>{html.escape(word)}</b>.\nСлова и счёт сохранятся."
    if state.get("word"):
        phrase = REACTIONS[(state["turns"]+sum(map(ord,state["word"]))) % len(REACTIONS)]
        opening = f"{phrase}\nТвоё <b>{html.escape(state['word'])}</b> → моё <b>{html.escape(word)}</b>."
    else:
        opening = ("Играем!" if state.get("created") else "Продолжаем!")+f" Моё слово: <b>{html.escape(word)}</b>."
    tail = f"В цепочке уже {state['turns']} слов игроков!" if state["turns"] and state["turns"] % 10 == 0 else f"Ходов: {state['turns']}"
    ending = f"\nВ конце «{word[-1].upper()}» пропускаем." if word and word[-1] in rules.SKIP_ENDINGS else ""
    return (f"🔤 {opening}{ending}\nТеперь тебе на <b>{state['letter'].upper()}</b>.\n"
            f"Напиши одно слово в открытом ответе.\n<i>{tail}</i>")


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
        signature = _signature(bot,":".join(fields.values()),message.from_user.id,message.chat.id,message.message_thread_id or 0,word)
        buttons.append([InlineKeyboardButton(text=word,callback_data=WordFixCB(**fields,s=signature).pack())])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def error_reply(db, message, bot, value: str, error: Exception) -> tuple[str, ForceReply | InlineKeyboardMarkup | None]:
    state = await game.spelling_help(db,chat_id=message.chat.id,topic_id=message.message_thread_id or 0,value=value)
    text = "🔤 "+html.escape(str(error))
    if state["candidates"]:
        return text+"\n\nВозможно, опечатка? Выбери своё слово ниже. Ход будет от твоего исходного сообщения.",correction_keyboard(state,message,bot)
    if state["active"]:
        return text+"\n\n"+prompt(state),word_input(state)
    return text,None


@registry.command("слова", aliases=("игра в слова",), private=False, section="games",
                  usage="бот слова [правила | счёт | подсказка | стоп]",
                  summary="Слова против бота: дальше отвечай одним словом, без повторения команды.")
async def command(ctx: Ctx) -> None:
    scope = dict(chat_id=ctx.message.chat.id,topic_id=ctx.message.message_thread_id or 0)
    arg = rules.normalize(ctx.args)
    try:
        if arg in {"правила","помощь"}:
            await ctx.reply(HELP)
            return
        if arg in {"стоп","закончить","завершить"}:
            state = await game.stop(ctx.db,**scope,actor=ctx.user_id,can_moderate=await ranks.can(ctx.db,scope["chat_id"],ctx.user_id,"write_closed"))
            await ctx.reply(f"🔤 Партия завершена · принято слов: {state['turns']}\n"+score(state))
            return
        if arg in {"счет","статус","подсказка"}:
            state = await game.status(ctx.db,**scope,hint=arg=="подсказка")
            if not state["active"]:
                text = f"Последняя партия · принято слов: {state['turns']}\n"+score(state) if state.get("last_round") else "Игра сейчас не идёт."
                await ctx.reply("🔤 "+text+"\nНачать: <code>бот слова</code>.")
                return
            text = prompt(state)+"\n\n<b>Счёт этой партии</b>\n"+score(state)
            if arg=="подсказка":
                text += "\n\nМожно: "+", ".join(state["hints"])
            await ctx.reply(text,reply_markup=word_input(state))
            return
        if arg and arg not in {"начать","старт"}:
            await ctx.reply(HELP)
            return
        state = await game.start(ctx.db,**scope,actor=ctx.user_id)
        await ctx.reply(prompt(state),reply_markup=word_input(state))
    except game.WordChainError as error:
        await ctx.reply("🔤 "+html.escape(str(error)))


@registry.command("слово", private=False, section="games", usage="бот слово, арбуз",
                  summary="Ход в словах. Удобнее написать одно слово в открытом ответе боту.")
async def word(ctx: Ctx) -> None:
    await play_message(ctx.db,ctx.bot,ctx.message,ctx.args)


def turn_reply(state: dict) -> tuple[str, ForceReply | None]:
    if state["finished"]:
        return (f"🔤 Вот это цепочка! Принято слов: {state['turns']}.\n"+score(state)+"\nНовая партия: <code>бот слова</code>.",None)
    return prompt(state),word_input(state)


async def play_message(db, bot, message, value: str) -> None:
    try:
        state = await game.play(db,chat_id=message.chat.id,topic_id=message.message_thread_id or 0,
                               actor=message.from_user.id,message_id=message.message_id,value=value)
        if state["replayed"]:
            return
        text,markup = turn_reply(state)
    except game.WordChainError as error:
        text,markup = await error_reply(db,message,bot,value,error)
    await message.reply(text,parse_mode="HTML",reply_markup=markup)


def is_reply(bot, message) -> bool:
    reply = message.reply_to_message
    return bool(reply and reply.from_user and message.from_user and not message.from_user.is_bot
                and reply.from_user.id == bot.id and (reply.text or "").startswith("🔤")
                and message.text is not None)


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
    if not isinstance(cb.message,Message) or cb.message.chat.id >= 0:
        await cb.answer("Открой подсказку в исходном чате.",show_alert=True)
        return
    cid,topic,actor = cb.message.chat.id,cb.message.message_thread_id or 0,cb.from_user.id
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
        text,markup = turn_reply(state)
        await cb.answer("Исправление принято!")
    except game.WordChainError as error:
        text,markup = await error_reply(db,original,bot,word,error)
        await cb.answer("Цепочка обновилась — смотри текущую букву.")
    mention = f'<a href="tg://user?id={actor}">{html.escape(cb.from_user.first_name)}</a>'
    await cb.message.answer(text.replace("🔤 ",f"🔤 {mention}, ",1),parse_mode="HTML",reply_markup=markup,
                            reply_parameters=ReplyParameters(message_id=mid,allow_sending_without_reply=True))
