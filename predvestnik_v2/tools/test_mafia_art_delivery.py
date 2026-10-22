"""Real role-card delivery boundary: images enhance one DM, never delay actions."""
import asyncio
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendPhoto
from aiogram.types import FSInputFile
from aiogram.types import Message, Chat
from bot.chat import mafia_dm as dm
from bot.chat import mafia_play as play
from bot.chat.mafia_cb import MafiaActionCB


async def check_selection():
    players=[dict(user_id=1,join_order=1,display_name='Доктор',alive=True,role='doctor'),
             dict(user_id=2,join_order=2,display_name='Игрок',alive=True,role='citizen')]
    view=dict(role='doctor',players=players)
    data=MafiaActionCB(match_id=10,phase_number=1,action='doctor_save',target_user_id=2)
    async def check(caption, *, photo=True):
        fields=dict(message_id=77,date=datetime.now(timezone.utc),chat=Chat(id=1,type='private'))
        if photo:fields.update(caption=caption,photo=[dict(file_id='x',file_unique_id='x',width=64,height=64)])
        else:fields.update(text=caption)
        query=SimpleNamespace(message=Message(**fields),from_user=SimpleNamespace(id=1))
        with patch.object(play.private,'private_view',new=AsyncMock(return_value=view)), \
             patch.object(Message,'edit_caption',new=AsyncMock()) as edit_caption, \
             patch.object(Message,'edit_text',new=AsyncMock()) as edit_text, \
             patch.object(Message,'edit_reply_markup',new=AsyncMock()) as edit_markup:
            await play._edit_chosen(query,None,data,2)
            return edit_caption,edit_text,edit_markup
    caption,text,markup=await check('Твоя роль: Доктор'+play.CHOSEN_MARK+': старый выбор')
    assert caption.await_count==1 and not text.await_count and not markup.await_count
    result=caption.call_args.kwargs
    assert 'Твоя роль: Доктор' in result['caption'] and 'старый выбор' not in result['caption']
    assert result['caption'].count(play.CHOSEN_MARK)==1 and '#2 Игрок' in result['caption']
    assert any('✓' in b.text or '✅' in b.text for row in result['reply_markup'].inline_keyboard for b in row)
    caption,text,markup=await check('🙂'*450+play.CHOSEN_MARK+': старый выбор')
    if caption.call_args.kwargs['caption'].endswith('старый выбор'):
        raise AssertionError('previous choice must never remain on photo')
    players[1]['display_name']='&'*100
    caption,text,markup=await check('🙂'*450+play.CHOSEN_MARK+': старый выбор')
    assert caption.await_count==1 and not text.await_count and not markup.await_count
    assert caption.call_args.kwargs['caption']=='🙂'*450
    caption,text,markup=await check('Твоя роль: Доктор',photo=False)
    assert text.await_count==1 and not caption.await_count and not markup.await_count


class Bot:
    id=991100
    def __init__(self,error=None):self.photos=[];self.texts=[];self.error=error
    async def send_photo(self,chat_id,**kw):
        self.photos.append((chat_id,kw))
        if self.error:raise self.error
        return SimpleNamespace(message_id=77,photo=[SimpleNamespace(file_id='cached-fictional-role')])
    async def send_message(self,chat_id,text,**kw):
        self.texts.append((chat_id,text,kw));return SimpleNamespace(message_id=78)


async def run():
    dm._PHOTO_IDS.clear();b=Bot();markup=object()
    sent=await dm.send_dm(b,1,'Твоя роль: Доктор',markup,art_role='doctor')
    assert sent.message_id==77 and len(b.photos)==1 and not b.texts
    assert isinstance(b.photos[0][1]['photo'],FSInputFile) and b.photos[0][1]['reply_markup'] is markup
    await dm.send_dm(b,2,'Твоя роль: Доктор',markup,art_role='doctor')
    assert b.photos[1][1]['photo']=='cached-fictional-role'
    await dm.send_dm(b,1,'Ночной ход',markup)
    assert len(b.photos)==2 and len(b.texts)==1
    await dm.send_dm(b,1,'🙂'*500,markup,art_role='doctor')
    assert len(b.photos)==2 and len(b.texts)==2, 'oversized UTF16 caption falls back to full text'
    await dm.send_dm(b,1,'Роль',markup,art_role='unknown')
    assert len(b.photos)==2 and len(b.texts)==3
    bad=Bot(TelegramBadRequest(method=SendPhoto(chat_id=1,photo='x'),message='invalid media'))
    await dm.send_dm(bad,1,'Твоя роль: Доктор',markup,art_role='doctor')
    assert len(bad.texts)==1 and bad.texts[0][2]['reply_markup'] is markup
    network=Bot(TelegramNetworkError(method=SendPhoto(chat_id=1,photo='x'),message='offline'))
    try:await dm.send_dm(network,1,'Твоя роль: Доктор',markup,art_role='doctor')
    except dm.RetryLater:pass
    else:raise AssertionError('network uncertainty must retry through existing delivery queue')
    assert not network.texts
    await check_selection()
    print('PASS: illustrated private role card, cached file id, unchanged buttons, plain prompts, long caption/media fallback and network retry')


asyncio.run(run())
