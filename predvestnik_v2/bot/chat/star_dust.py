"""Daily starfall and owner-bound dust shop, shared by groups and private chats."""
from html import escape
from datetime import datetime, timezone
from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from bot.chat.framework import registry
from core.star_dust import DustError
from infrastructure.repositories import pet_chat
from services import star_dust as service

router = Router(name='chat_star_dust')

def num_fraction(value):return f'{value:.2f}'.rstrip('0').rstrip('.').replace('.',',')


async def available(db, uid, chat, command='пыль'):
    async with db.execute('SELECT deleted_at FROM users WHERE user_tg_id=?', (uid,)) as c:
        row = await c.fetchone()
    if not row or row[0] is not None: return False
    async with db.execute('SELECT 1 FROM bot_user_blocks WHERE user_id=? AND (until IS NULL OR until>NOW())', (uid,)) as c:
        if await c.fetchone(): return False
    chat_id = chat.id if chat.type in ('group', 'supergroup') else 0
    async with db.execute('SELECT feature FROM bot_feature_switches WHERE chat_id IN (0,?)', (chat_id,)) as c:
        keys = {'all', 'section:stars', 'group:star_dust', 'cmd:'+command}
        if any(r[0] in keys for r in await c.fetchall()): return False
    return await service.enabled(db)


async def render(db, uid, chat_id, data=None):
    data = data or {}
    v = await service.overview(db, uid)
    vip = v['vip']; rows = []
    async def button(label, **payload):
        token = await pet_chat.save(db, uid, chat_id, {'scope':'star_dust', **payload})
        return InlineKeyboardButton(text=label, callback_data='sd:'+token)
    text = (f"🌠 <b>Звёздная пыль</b>\n\nВ запасе: <b>{v['balance']}</b>\n"
            f"От питомцев сегодня: {v['pet_today']}\n\n"
            '<code>бот звездопад</code> — поймать звёзды раз в день. Иногда небо остаётся тихим.\n'
            'Пока отряд в походе или экспедиции, общий звёздный след собирает 2 пыли в час. '
            'Дозор собирает медленнее: 1 пыль за 5 часов. Пересекающиеся пути не умножают пыль, дробная часть сохраняется.\n\n'
            f"<b>VIP: {vip['day_cost']} пыли за день</b>\n"
            'Любой срок по запасу пыли, без календарных ограничений. Пыль личная: её нельзя передать или обменять на Мору.\n'
            '<code>бот вип за пыль 10</code> — выбрать свой срок.')
    if vip.get('active') and vip.get('expires_at'):
        until=datetime.fromisoformat(vip['expires_at']).astimezone(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')
        text+=f'\n\n✨ VIP активен до {until}.'
    else:text+='\n\nVIP пока не активен.'
    fraction=int(float(v.get('pet_fraction',0))*100)/100
    if fraction>0:text+=f"\nВ звёздном следе сохранено ещё {num_fraction(fraction)} пыли."
    if data.get('screen') == 'confirm':
        days = int(data['days']); cost = int(data['cost'])
        text = f'🌠 <b>Подтвердить обмен</b>\n\nVIP на {days} дн. за <b>{cost} пыли</b>.\nТекущий VIP будет продлён.\nВ запасе: {v["balance"]}.'
        if days>vip['max_days']:
            text+=f"\nНе хватает {max(0,cost-v['balance'])} пыли."
        else:rows.append([await button(f'Обменять {cost} пыли', do='vip', days=days, cost=cost)])
        rows.append([await button('‹ Назад')])
    else:
        buttons = [await button(f'{d} дн. · {d*vip["day_cost"]} 🌠', screen='confirm', days=d, cost=d*vip['day_cost'])
                   for d in sorted({d for d in (1,2,3,7,vip['max_days']) if 0<d<=vip['max_days']})]
        rows.extend(buttons[i:i+2] for i in range(0,len(buttons),2))
        if not buttons: text += '\n\nПока обмен недоступен: накопи ещё пыль.'
        rows.append([await button('Обновить')])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def open_menu(ctx, days=None):
    try:
        if not await available(ctx.db, ctx.user_id, ctx.message.chat, ctx.command.name):
            await ctx.reply('⛔ Звёздная пыль сейчас недоступна.'); return
        await pet_chat.expire(ctx.db, ctx.user_id)
        if days is not None and days<1:raise DustError('Укажи положительное число дней.')
        text, kb = await render(ctx.db, ctx.user_id, ctx.message.chat.id, {'screen':'confirm','days':days,'cost':days*100} if days is not None else {})
        await ctx.reply(text, reply_markup=kb)
    except DustError as exc:await ctx.reply(escape(str(exc)))
    except Exception:
        logger.exception('dust menu unavailable')
        await ctx.reply('Не удалось открыть звёздную пыль. Попробуй позже.')


@registry.command('звездопад', aliases=('звёздопад',), section='stars', group='star_dust', summary='Поймать случайную звёздную пыль раз в день.', usage='бот звездопад')
async def starfall(ctx):
    try:
        if not await available(ctx.db, ctx.user_id, ctx.message.chat, ctx.command.name):
            await ctx.reply('⛔ Звездопад сейчас недоступен.'); return
        r = await service.search(ctx.db, user_id=ctx.user_id)
        luck = r['luck']; stars = '★'*luck['stars']+'☆'*(5-luck['stars'])
        text = f"🌠 <b>{escape(luck['title'])}</b>\n{stars}\n\n{escape(luck['text'])}\n"
        text += f"Поймано: <b>{r['amount']} пыли</b> · запас {r['balance']}."
        if r['already_claimed']: text += '\nЭто твой сегодняшний результат — звёзды уже пойманы.'
        text += '\nСледующая попытка — после 00:00 UTC.\n<code>бот пыль</code> — обмен на VIP.'
        token=await pet_chat.save(ctx.db,ctx.user_id,ctx.message.chat.id,{'scope':'star_dust'})
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🌠 Моя пыль · VIP за игру',callback_data='sd:'+token)]])
        await ctx.reply(text,reply_markup=kb)
    except DustError as exc: await ctx.reply(escape(str(exc)))
    except Exception:
        logger.exception('starfall failed')
        await ctx.reply('Небо пока недоступно. Попробуй ещё раз: сегодняшняя находка сохранится.')


@registry.command('пыль', aliases=('звездная пыль','звёздная пыль'), section='stars', group='star_dust', summary='Запас пыли, источники и обмен на VIP.', usage='бот пыль')
async def dust(ctx): await open_menu(ctx)


@registry.command('вип за пыль', aliases=('пыль вип',), section='stars', group='star_dust', summary='Выбрать и подтвердить VIP за звёздную пыль.', usage='бот вип за пыль [дней]')
async def vip(ctx):
    value=ctx.args.strip()
    if value and (not value.isdigit() or len(value)>9):
        await ctx.reply('Напиши число дней, например: <code>бот вип за пыль 2</code>.');return
    await open_menu(ctx,int(value) if value else None)


@router.callback_query(F.data.startswith('sd:'))
async def on_dust(call, db):
    try:
        if call.message is None:
            await call.answer('Открой «бот пыль».', show_alert=True); return
        b = await pet_chat.get(db, call.data[3:])
        if not b or not b['valid'] or b['payload'].get('scope') != 'star_dust':
            await call.answer('Меню устарело. Открой «бот пыль».', show_alert=True); return
        if b['user_id'] != call.from_user.id or b['chat_id'] != call.message.chat.id:
            await call.answer('Это меню другого игрока или чата.', show_alert=True); return
        if not await available(db, call.from_user.id, call.message.chat, 'вип за пыль' if b['payload'].get('do')=='vip' or b['payload'].get('screen')=='confirm' else 'пыль'):
            await call.answer('⛔ Звёздная пыль сейчас недоступна.', show_alert=True); return
        data = b['payload']; notice = ''
        if data.get('do') == 'vip':
            r = await service.buy_vip(db, user_id=call.from_user.id, days=data['days'], expected_cost=data['cost'], action_id='chat:'+b['token'])
            notice = f"✨ <b>VIP продлён на {r['days']} дн.</b>\nСписано {r['cost']} пыли.\n\n"
            data = {}
        text, kb = await render(db, call.from_user.id, call.message.chat.id, data)
        await call.message.edit_text(notice+text, parse_mode='HTML', reply_markup=kb)
        await call.answer()
    except DustError as exc: await call.answer(str(exc)[:190], show_alert=True)
    except Exception as exc:
        if 'message is not modified' in str(exc):
            await call.answer(); return
        logger.exception('dust callback failed; keep original receipt token')
        await call.answer('Повтори эту же кнопку: обмен не оплатится дважды.', show_alert=True)
