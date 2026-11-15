"""Telegram controls for pets v2. Durable buttons retain the same service receipt on retry."""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger

from bot.chat.framework import Ctx, registry
from bot.chat import pet_menu as ui, pet_details as detail, pet_builds as builds
from core.pets_v2 import PetV2PolicyError
from infrastructure.repositories import pet_chat, system_flags
from services import pets_v2 as service, pet_equipment as equipment

router = Router(name='chat_pets')


async def available(db, user_id, chat, data=None) -> bool:
    """Re-check every button, including private chats, and fail closed on missing schema."""
    async with db.execute('SELECT user_id FROM bot_user_blocks WHERE user_id=? AND (until IS NULL OR until>NOW())', (user_id,)) as cur:
        if await cur.fetchone(): return False
    async with db.execute('SELECT deleted_at FROM users WHERE user_tg_id=?', (user_id,)) as cur:
        account = await cur.fetchone()
    if not account or account[0] is not None: return False
    if not await system_flags.is_enabled(db, 'pets_v2'):
        return False
    async with db.execute("SELECT enabled FROM global_module_toggles WHERE module_key='module_pets'") as cur:
        row = await cur.fetchone()
    if row and not row[0]:
        return False
    chat_id = chat.id if chat.type in ('group', 'supergroup') else None
    if chat_id:
        async with db.execute('SELECT COALESCE(module_pets,1) FROM chat_settings WHERE chat_id=?', (chat_id,)) as cur:
            row = await cur.fetchone()
        if row and not row[0]:
            return False
    keys = ['all', 'section:pets', 'group:pets', 'cmd:pets', 'cmd:питомцы']
    data=data or {}
    route=data.get('do') or (data.get('target') if data.get('screen')=='choose' else data.get('screen'))
    command={'camp':'лагерь','feed':'покормить питомца','feed_confirm':'покормить питомца',
             'start':'отправить питомца','prepare':'отправить питомца',
             'trial':'испытание питомцев','track':'выслеживание','track_start':'выслеживание','track_open':'выслеживание',
             'outing':'вылазка','outing_start':'вылазка','outing_choose':'вылазка','bestiary':'бестиарий'}.get(route)
    if command:keys.append('cmd:'+command)

    # Read the switches directly: a button already shown must stop immediately after revocation.
    async with db.execute('SELECT feature FROM bot_feature_switches WHERE chat_id IN (0,?)', (chat_id or 0,)) as cur:
        if any(row[0] in keys for row in await cur.fetchall()):
            return False
    return True


async def render(db, uid, chat_id, data, result=None):
    view = await service.overview(db, uid)
    m = ui.Menu(db, uid, chat_id)
    screen = data.get('screen', 'home')
    p = ui.pet(view, data['pet_id']) if data.get('pet_id') else None
    if data.get('pet_id') and not p:
        raise PetV2PolicyError('Питомец не найден. Обнови список.')
    if screen == 'home': text = await ui.home(m, view)
    elif screen in ('collection', 'choose'):
        page = max(0, int(data.get('page', 0)))
        target = data.get('target', 'pet')
        if target=='outing' and view['equipment']['open']:
            return await detail.outing(m,view,{},result), m.keyboard
        if target=='track' and view['track']['open']:
            return await detail.track(m,view,{},result), m.keyboard
        for item in view['pets'][page*8:page*8+8]:
            await m.row((ui.name(item), {'screen': target, 'pet_id': item['id']}))
        await pagination(m, data, page, len(view['pets']), 8)
        await m.back()
        text = '🐾 <b>Выбери питомца</b>' if screen == 'choose' else '🐾 <b>Все питомцы</b>'
        if not view['pets']: text += '\n\nПока нет питомцев. Найти первого можно в сундуках.'
    elif screen == 'bestiary':
        from core.chests_v1 import PET_SPECIES
        from core import pets_v2 as rules
        page = max(0, int(data.get('page', 0))); rows = list(PET_SPECIES.items())
        owned = {p['species_id'] for p in view['pets']}
        text = '📖 <b>Бестиарий</b>\n\n' + '\n\n'.join(
            f"{r['icon']} <b>{ui.e(r['name'])}</b> {'✓' if key in owned else '· ещё не найден'}\nЛюбимый маршрут: {ui.ROUTES[rules.SPECIES[key][1]]}"
            for key, r in rows[page*6:page*6+6] if key in rules.SPECIES)
        await pagination(m, data, page, len(rows), 6); await m.back()
    elif screen == 'pet': text = await ui.card(m, view, p)
    elif screen == 'prepare': text = await ui.prepare(m, view, p, data)
    elif screen == 'feed': text = await detail.feed(m, view, p)
    elif screen == 'feed_confirm': text = await detail.feed_confirm(m, view, p, data)
    elif screen == 'claim': text = await detail.claim(m, view, data)
    elif screen == 'camp': text = await detail.camp(m, view, data)
    elif screen == 'trial': text = await detail.trial(m, view, data)
    elif screen == 'track': text = await detail.track(m, view, data, result)
    elif screen == 'outing': text = await detail.outing(m, view, data, result)
    elif screen == 'build': text = await builds.build(m, view, p, data)
    elif screen == 'build_confirm': text = await builds.build_confirm(m, view, p, data)
    elif screen == 'reforge': text = await builds.reforge(m, view, p, data)
    elif screen == 'gear': text = await builds.gear(m, view, p, data)
    elif screen == 'preset_confirm':
        await m.row(('Сохранить набор', {'do':'preset', 'pet_id':p['id'], 'slot':data['slot'], 'draft':data['draft']}))
        await m.back(p['id'])
        text = f"{ui.title(p)}\n\n<b>Сохранить набор {data['slot']}?</b>\nПредыдущий набор в этом слоте будет заменён. Текущая сборка не изменится."
    elif screen == 'help':
        await m.back()
        text = ('🐾 <b>Всё рядом</b>\n\n'
                '<code>бот питомцы</code> — кто дома и кто возвращается.\n'
                '<code>бот отправить питомца</code> — поход, экспедиция или дозор; сначала покажем расход сил и награду.\n'
                '<code>бот покормить питомца</code> — лакомства и восстановление сил.\n'
                '<code>бот лагерь</code> — улучшения за Мору и Эссенцию.\n'
                '<code>бот вылазка</code> — короткое приключение с развилками.\n'
                '<code>бот выслеживание</code> — поиск тайника на поле 3×3.\n'
                '<code>бот испытание питомцев</code> — испытание недели.\n'
                '<code>бот бестиарий</code> — коллекция видов.\n\n'
                'Открой карточку питомца, чтобы настроить снаряжение, призвание, черты, талисманы и три сохранённых набора. '
                'Кнопки работают только для владельца и в этом чате. После обрыва связи повтори ту же кнопку: действие не оплатится дважды.')
    else: raise PetV2PolicyError('Меню устарело. Открой «бот питомцы».')
    return text, m.keyboard


async def pagination(m, data, page, total, size):
    buttons = []
    if page: buttons.append(('‹ Назад', {**data, 'page':page-1}))
    if (page+1)*size < total: buttons.append(('Дальше ›', {**data, 'page':page+1}))
    if buttons: await m.row(*buttons)


async def mutate(db, uid, token, data):
    """Explicit allowlists prevent navigation fields leaking into service arguments."""
    action = data['do']; common = dict(user_id=uid, action_id='chat:'+token)
    async def invoke(fn, *fields):
        return await fn(db, **common, **{k:data[k] for k in fields})
    if action == 'start':
        result = await invoke(service.start_run,'pet_id','kind','hours','route','companion_id')
        return result, {'screen':'pet','pet_id':data['pet_id']}, '✅ Питомец отправился в путь.'
    if action == 'claim':
        result = await invoke(service.claim_run,'run_id','path')
        lines=['🎒 <b>Питомец вернулся</b>',f"Следы: +{ui.num(result.get('xp_credited', result.get('xp_raw',0)))}"]
        names={'mora':'Мора','diamond':'Алмазы','essence':'Эссенция','treat':'Лакомства','talisman':'Талисманы'}
        for key,amount in result.get('finds',{}).items():
            if amount:lines.append(f"{names.get(key,ui.e(key))}: +{amount}")
        if result.get('key'):lines.append(f"Ключи: +{result['key']}")
        dust=result.get('star_dust',{}).get('amount',0)
        if dust:lines.append(f'🌠 +{dust} звёздной пыли')
        elif result.get('star_dust',{}).get('shared_trail'):
            lines.append('🌠 Частица звёздного следа сохранена.' if result['star_dust'].get('new_trail') else '🌠 За это время звёздный след уже собран другим питомцем.')
        if result.get('level_after',0)>result.get('level_before',0):lines.append(f"Новый уровень: {result['level_after']} ✨")
        if result.get('stage_essence'):lines.append(f"Новая ступень: +{result['stage_essence']} Эссенции")
        if result.get('companion'):lines.append(f"Спутник: +{ui.num(result['companion']['xp_credited'])} Следов")
        return result, {'screen':'home'}, '\n'.join(lines)
    if action == 'feed':
        result = await invoke(service.feed_pet,'pet_id','food_id')
        return result, {'screen':'pet','pet_id':data['pet_id']}, '🥕 Лакомство съедено.'
    if action == 'camp':
        result = await invoke(service.camp_upgrade,'building','expected_level')
        return result, {'screen':'camp'}, '🏕 Улучшение лагеря началось.'
    if action == 'build':
        result = await invoke(service.set_build,'pet_id','calling','traits','talisman_ids','expected_essence','expected_build')
        return result, {'screen':'pet','pet_id':data['pet_id']}, '✅ Сборка применена.'
    if action == 'reforge':
        result = await invoke(service.reforge_talisman,'talisman_id','expected_tier')
        return result, {'screen':'build','pet_id':data['return_pet']}, '🧿 Талисман усилен.'
    if action == 'preset':
        result = await service.save_build_preset(db, **common, pet_id=data['pet_id'],slot=data['slot'],name=f"Набор {data['slot']}",
            calling=data['draft']['calling'],traits=data['draft']['traits'],talismans=data['draft']['talisman_ids'])
        return result, {'screen':'build','pet_id':data['pet_id'],'section':'presets'}, '✅ Набор сохранён.'
    if action == 'gear':
        result = await invoke(equipment.change,'pet_id','operation','item','expected_tier')
        return result, {'screen':'gear','pet_id':data['pet_id']}, '✅ Снаряжение обновлено.'
    if action == 'trial':
        result = await invoke(service.submit_trial,'pet_id','difficulty','expected_week')
        return result, {'screen':'trial'}, '🏆 Испытание недели сдано.'
    if action in ('track_start','track_open'):
        result = await (invoke(service.start_track,'pet_id') if action=='track_start' else invoke(service.open_track_cell,'track_id','cell'))
        return result, {'screen':'track'}, ''
    if action in ('outing_start','outing_choose'):
        result = await (invoke(equipment.start,'pet_id') if action=='outing_start' else invoke(equipment.choose,'outing_id','step','choice'))
        return result, {'screen':'outing'}, ''
    raise PetV2PolicyError('Действие устарело. Открой «бот питомцы».')


async def open_menu(ctx, screen='home', **data):
    try:
        if not await available(ctx.db, ctx.user_id, ctx.message.chat, {'screen':screen, **data}):
            await ctx.reply('⛔ Питомцы сейчас недоступны.'); return
        await pet_chat.expire(ctx.db, ctx.user_id)
        text, kb = await render(ctx.db, ctx.user_id, ctx.message.chat.id, {'screen':screen, **data})
        await ctx.reply(text, reply_markup=kb)
    except PetV2PolicyError as exc: await ctx.reply(ui.e(exc))
    except Exception:
        logger.exception('pet chat menu unavailable')
        await ctx.reply('Не удалось открыть питомцев. Попробуй чуть позже.')


@registry.command('питомцы', aliases=('pets','питомец','мои питомцы','вернуть питомца'),section='pets',group='pets',summary='Питомцы, возвращения и всё управление.',usage='бот питомцы')
async def cmd_pets(ctx: Ctx): await open_menu(ctx)


def register_menu(name, screen, summary, aliases=(), target=None):
    async def command(ctx):
        await open_menu(ctx, screen, **({'target':target} if target else {}))
    registry.command(name, aliases=aliases,section='pets',group='pets',summary=summary,example='бот '+name)(command)


register_menu('отправить питомца','choose','Выбрать путь, срок и спутника.',('поход','экспедиция питомца','дозор'), 'prepare')
register_menu('покормить питомца','choose','Выбрать питомца и лакомство.',('кормить питомца',), 'feed')
register_menu('лагерь','camp','Улучшения лагеря.')
register_menu('вылазка','choose','Приключение с развилками.',target='outing')
register_menu('выслеживание','choose','Поиск тайника на поле 3×3.',target='track')
register_menu('испытание питомцев','trial','Испытание недели.',('испытание недели',))
register_menu('бестиарий','bestiary','Коллекция видов питомцев.')


@router.callback_query(F.data.startswith('pt:'))
async def on_pet(call: CallbackQuery, db):
    if call.message is None:
        await call.answer('Открой «бот питомцы».', show_alert=True); return
    try:
        button = await pet_chat.get(db, call.data[3:])
        if not button or not button['valid']:
            await call.answer('Меню устарело. Открой «бот питомцы».', show_alert=True); return
        if button['user_id'] != call.from_user.id or button['chat_id'] != call.message.chat.id:
            await call.answer('Это меню другого игрока или чата.', show_alert=True); return
        if not await available(db, call.from_user.id, call.message.chat, button['payload']):
            await call.answer('⛔ Питомцы сейчас недоступны.', show_alert=True); return
        data = button['payload']; result = None; notice = ''
        if 'do' in data:
            result, data, notice = await mutate(db, call.from_user.id, button['token'], data)
        text, kb = await render(db, call.from_user.id, call.message.chat.id, data, result)
        if notice: text = notice + '\n\n' + text
        # A delivery or post-commit overview failure leaves the original action button intact.
        await call.message.edit_text(text,parse_mode='HTML',reply_markup=kb,disable_web_page_preview=True)
        await call.answer('Готово' if result else '')
    except (PetV2PolicyError, ValueError) as exc:
        await call.answer(str(exc)[:190],show_alert=True)
    except Exception as exc:
        from aiogram.exceptions import TelegramBadRequest
        if isinstance(exc, TelegramBadRequest) and 'message is not modified' in str(exc):
            await call.answer(); return
        logger.exception('pet chat callback failed; retain original retry token')
        await call.answer('Не удалось обновить меню. Повтори эту же кнопку: действие не спишется дважды.',show_alert=True)
