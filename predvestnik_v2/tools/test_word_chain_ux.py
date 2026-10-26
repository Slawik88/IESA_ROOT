"""Telegram interaction contracts without a network, plus real offline spelling."""
import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN","123456:local-test")
os.environ.setdefault("DATABASE_URL","postgresql://local/test")
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from aiogram.types import CallbackQuery, ForceReply, Message
from bot.chat import word_chain as ui
from core import word_chain as rules
from core.word_chain.spelling import suggest

BOT = SimpleNamespace(id=999,token="123456:local-test")
STATE = dict(active=True,created=True,round_id=100,turns=0,last_word="ананас",letter="с",leaders=[])
RESULT = dict(active=True,round_id=100,turns=1,word="слон",bot_word="нос",letter="с",finished=False,replayed=False)


def message(*, actor=101, chat=-100, topic=7, text="слон", mid=50, reply=True):
    data={"message_id":mid,"date":1,"chat":{"id":chat,"type":"supergroup"},"from":{"id":actor,"is_bot":actor==999,"first_name":"QA"},"text":text,"message_thread_id":topic}
    if reply:
        data["reply_to_message"]={"message_id":49,"date":1,"chat":data["chat"],"from":{"id":999,"is_bot":True,"first_name":"Bot"},"text":"🔤 Играем"}
    return Message.model_validate(data)


async def run():
    assert "арбуз" in suggest("арбзу","а",set())
    assert "апельсин" in suggest("апилсин","а",set())
    assert "арбуз" not in suggest("арбзу","а",{"арбуз"})
    assert suggest("корова","к",set()) == [], "valid nouns cannot be silently reinterpreted"
    assert suggest("жжжжжжжжжжжжжжжжжжжжжж","ж",set()) == []
    assert suggest("<script>","с",set()) == []
    assert rules.normalize(" ЁЖ! ")=="еж"
    assert ui.word_input({**STATE,"paused":True}) is None
    assert "на паузе" in ui.prompt({**STATE,"paused":True})
    with patch.object(ui.game,"play",AsyncMock(return_value=RESULT)) as play, patch.object(Message,"reply",AsyncMock()) as reply:
        assert not await ui.on_reply(object(),BOT,message(reply=False))
        assert not play.called
        assert await ui.on_reply(object(),BOT,message())
        assert isinstance(reply.call_args.kwargs["reply_markup"],ForceReply)
        assert reply.call_args.kwargs["reply_markup"].selective
        assert "бот слово" not in reply.call_args.args[0]
    with patch.object(ui.game,"play",AsyncMock(side_effect=ui.game.WordChainError("Нужно одно существительное"))), patch.object(ui.game,"spelling_help",AsyncMock(return_value={**STATE,"candidates":[]})), patch.object(Message,"reply",AsyncMock()) as reply:
        assert await ui.on_reply(object(),BOT,message(text="два слова"))
        assert "Нужно одно" in reply.call_args.args[0]
        assert reply.call_args.kwargs["reply_markup"].selective, "explicit invalid replies keep the input loop"
    ctx=SimpleNamespace(args="",db=object(),message=message(text="бот слова"),user_id=101,bot=BOT,reply=AsyncMock())
    with patch.object(ui.game,"start",AsyncMock(return_value=STATE)):
        await ui.command(ctx)
        assert ctx.reply.call_args.kwargs["reply_markup"].selective
    keyboard=ui.correction_keyboard({**STATE,"candidates":["слон","собака"]},message(text="слно"),BOT)
    callback=ui.WordFixCB.unpack(keyboard.inline_keyboard[0][0].callback_data)
    maximum=ui.correction_keyboard({**STATE,"round_id":2**63-1,"turns":rules.MAX_TURNS,"candidates":[rules.SORTED_WORDS[-1]]},message(mid=2**31-1),BOT)
    assert len(maximum.inline_keyboard[0][0].callback_data.encode())<=64
    def cb(actor=101,chat=-100,topic=7):
        return CallbackQuery.model_validate({"id":"qa","from":{"id":actor,"is_bot":False,"first_name":"QA"},"chat_instance":"qa","message":message(actor=999,chat=chat,topic=topic,mid=51,reply=False).model_dump(),"data":callback.pack()})
    with patch.object(ui.global_moderation,"is_blocked",AsyncMock(return_value=False)), patch.object(ui.feature_switches,"disabled",AsyncMock(return_value=None)), patch.object(ui.game,"play",AsyncMock(return_value=RESULT)) as play, patch.object(CallbackQuery,"answer",AsyncMock()) as ack, patch.object(Message,"answer",AsyncMock()) as sent:
        for query,data in [(cb(102),callback),(cb(chat=-101),callback),(cb(topic=8),callback),(cb(),callback.model_copy(update={"s":"0"*16}))]:
            await ui.confirm_spelling(query,data,BOT,object())
        assert not play.called, "actor/chat/topic/tampering must fail before the game writer"
        await ui.confirm_spelling(cb(),callback,BOT,object())
        assert play.call_args.kwargs["message_id"]==50
        assert play.call_args.kwargs["expected_round"]==100 and play.call_args.kwargs["expected_turn"]==0
        assert sent.call_args.kwargs["reply_parameters"].message_id==50
        assert sent.call_args.kwargs["reply_markup"].selective
        sent.reset_mock();play.return_value={**RESULT,"replayed":True}
        await ui.confirm_spelling(cb(),callback,BOT,object())
        assert not sent.called and "уже учтён" in ack.call_args.args[0]
        play.reset_mock()
        with patch.object(ui.feature_switches,"disabled",AsyncMock(return_value=("games","disabled"))):
            await ui.confirm_spelling(cb(),callback,BOT,object())
        assert not play.called, "corrections obey the disabled-game gate"
    assert len({ui.prompt({**RESULT,"turns":i}) for i in range(1,7)})>1
    print("PASS: automatic addressed replies, ordinary-chat isolation, invalid-input recovery, spelling, signed corrections, stale-user/topic/tampering guards, retry, feature gate and callback64-byte limit")


if __name__=="__main__":
    asyncio.run(run())
