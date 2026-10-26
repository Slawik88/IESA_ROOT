"""Telegram adapter for the persistent word game; never mints activity."""
import html

from bot.chat.framework import Ctx, registry
from bot.chat import ranks
from core import word_chain as rules
from services import word_chain as game

HELP = ("🔤 <b>Слова</b> — игра против бота, одному или вместе.\n\n"
        "1. Начни: <code>бот слова</code>.\n"
        "2. Отправь существительное на последнюю букву слова бота: <code>бот слово, арбуз</code>. "
        "Можно ответить словом на сообщение игры.\n"
        "3. Бот продолжит цепочку. Присоединиться может каждый.\n\n"
        "Ё считается как Е. В конце пропускаем Ь, Ъ, Ы и Й. "
        "Повторять слова этой партии нельзя. Между своими ходами — 3 секунды.\n\n"
        "Твои сообщения учитываются в норме как обычные сообщения; ответы бота очков нормы не дают. "
        "Валюты, ставок и платных подсказок нет.\n\n"
        "<code>бот слова, счёт</code> · <code>бот слова, подсказка</code> · <code>бот слова, стоп</code>\n"
        "После суток без ходов можно начать новую партию. В каждой теме группы своя игра.")


def prompt(state: dict) -> str:
    word = html.escape(state.get("bot_word") or state.get("last_word") or "")
    return (f"🔤 <b>Слова · ходов {state['turns']}</b>\n"
            f"Моё слово: <b>{word}</b>\nТебе на <b>{state['letter'].upper()}</b>.\n"
            "Ответь на это сообщение словом или напиши <code>бот слово, …</code>.\n"
            "Помощь: <code>бот слова, правила</code>")


def score(state: dict) -> str:
    rows = state.get("leaders",[])
    return "\n".join(f"{i}. {html.escape(p['name'])} — {p['score']}" for i,p in enumerate(rows,1)) or "Пока нет принятых слов."


@registry.command("слова", aliases=("игра в слова",), private=False, section="games",
                  usage="бот слова [правила | счёт | подсказка | стоп]",
                  summary="Слова против бота: играй один или вместе, сообщения идут в обычный учёт нормы.")
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
                if state.get("last_round"):
                    await ctx.reply(f"🔤 Последняя партия · принято слов: {state['turns']}\n"+score(state)+"\nНачать новую: <code>бот слова</code>.")
                else:
                    await ctx.reply("🔤 Игра сейчас не идёт. Начать: <code>бот слова</code>.")
                return
            text = prompt(state)+"\n\n<b>Счёт этой партии</b>\n"+score(state)
            if arg=="подсказка":
                text += "\n\nМожно: "+", ".join(state["hints"])
            await ctx.reply(text)
            return
        if arg and arg not in {"начать","старт"}:
            await ctx.reply(HELP)
            return
        state = await game.start(ctx.db,**scope,actor=ctx.user_id)
        await ctx.reply(prompt(state))
    except game.WordChainError as error:
        await ctx.reply("🔤 "+html.escape(str(error)))


@registry.command("слово", private=False, section="games", usage="бот слово, арбуз",
                  summary="Сделать ход в игре в слова. Можно ответить словом на сообщение игры.")
async def word(ctx: Ctx) -> None:
    await play_message(ctx.db,ctx.message,ctx.args)


async def play_message(db, message, value: str) -> None:
    try:
        state = await game.play(db,chat_id=message.chat.id,topic_id=message.message_thread_id or 0,
                               actor=message.from_user.id,message_id=message.message_id,value=value)
        if state["replayed"]:
            return
        text = (f"🔤 <b>Цепочка завершена!</b> Принято слов: {state['turns']}.\n"
                "Начни новую: <code>бот слова</code>.\n"+score(state)) if state["finished"] else prompt(state)
        await message.reply(text,parse_mode="HTML")
    except game.WordChainError as error:
        await message.reply("🔤 "+html.escape(str(error)),parse_mode="HTML")


async def on_reply(db, bot, message) -> bool:
    reply = message.reply_to_message
    if not reply or not reply.from_user or not message.from_user or message.from_user.is_bot:
        return False
    if reply.from_user.id != bot.id or not (reply.text or "").startswith("🔤"):
        return False
    value = message.text or ""
    if not rules.WORD_RE.fullmatch(rules.normalize(value)):
        return False
    await play_message(db,message,value)
    return True
