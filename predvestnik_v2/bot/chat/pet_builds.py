"""Build and equipment controls. Each confirmation freezes full IDs, price and prior build."""
from bot.chat.pet_menu import e,name,title,draft,CALLINGS
TRAITS={'night_walk':'Ночной ход','sprinter':'Скороход','reckless':'Азартный','careful':'Осторожный','picky':'Привередливый','hoarder':'Запасливый','piggybank':'Копилка','meticulous':'Скрупулёзный','hardy':'Выносливый','nose':'Нюх','lunatic':'Лунатик','loner':'Одиночка'}
TALISMANS={'forest_fang':'Лесной клык','pass_stone':'Каменный перевал','ruin_lens':'Линза руин','swamp_lamp':'Болотный фонарь'}


def cost(p,d,view):
    swap=view['rules']['swap'];value=0
    if p['calling'] and d['calling']!=p['calling'] and not p['swap_free']['calling']:value+=swap['calling']
    removed=set(p['traits'])-set(d['traits'])
    if removed and not p['swap_free']['traits']:value+=swap['trait']*len(removed)
    return value


def talisman_summary(view,p,ids):
    catalog={t['id']:t for t in view['talismans']}
    owners={other['id']:other for other in view['pets']}
    lines=[]
    for key in ids:
        t=catalog.get(key)
        if not t:
            lines.append('• Талисман больше недоступен. Выбери другой.');continue
        label=TALISMANS.get(t['kind'],t['kind'])+f" · {t['tier']} ур."
        owner=owners.get(t['pet_id'])
        if owner and owner['id']!=p['id']:label+=' · снимется с '+name(owner)
        lines.append('• '+e(label))
    return '\n'.join(lines) or 'не выбраны'


async def build(m,view,p,data):
    d=data.get('draft') or draft(p);base=data.get('base') or draft(p)
    page=data.get('page',0);section=data.get('section')
    common={'screen':'build','pet_id':p['id'],'draft':d,'base':base}
    if section=='calling':
        for key in [None,*view['callings']]:
            changed={**d,'calling':key}
            if key is None or p['level']>=view['rules']['calling_min_level']:
                await m.row((('✓ ' if d['calling']==key else '')+CALLINGS.get(key,'Без призвания'),{**common,'draft':changed}))
        text='Призвание: '+str(view['rules']['calling_min_level'])+' ур.\n'+ '\n'.join(f"• {CALLINGS[k]}: {e(' / '.join(str(x) for x in view['rules']['calling_texts'][k] if x))}" for k in view['callings'])
    elif section=='traits':
        for key in view['traits']:
            selected=key in d['traits'];changed=[t for t in d['traits'] if t!=key] if selected else [*d['traits'],key]
            if selected or len(changed)<=p['trait_slots']:
                await m.row((('✓ ' if selected else '')+TRAITS.get(key,key),{**common,'section':'traits','draft':{**d,'traits':changed}}))
        text=f"Черты: {len(d['traits'])}/{p['trait_slots']}\n"+'\n'.join(f"• {TRAITS[k]}: {e(' / '.join(view['rules']['traits'][k]))}" for k in view['traits'])
    elif section=='talismans':
        talismans=view['talismans'];start=page*6
        for t in talismans[start:start+6]:
            selected=t['id'] in d['talisman_ids'];changed=[i for i in d['talisman_ids'] if i!=t['id']] if selected else [*d['talisman_ids'],t['id']]
            if selected or len(changed)<=view['rules']['talisman_slots']:
                await m.row((('✓ ' if selected else '')+TALISMANS.get(t['kind'],t['kind'])+f" {t['tier']}",{**common,'section':'talismans','page':page,'draft':{**d,'talisman_ids':changed}}))
            if t['tier']<3:await m.row(('Усилить '+TALISMANS.get(t['kind'],t['kind']),{'screen':'reforge','pet_id':p['id'],'talisman_id':t['id']}))
        if page:await m.row(('‹ Назад', {**common,'section':'talismans','page':page-1}))
        if start+6<len(talismans):await m.row(('Дальше ›', {**common,'section':'talismans','page':page+1}))
        text='Талисманы · выбери до двух.\nПеренос с другого свободного питомца снимет талисман с него.' if talismans else 'Талисманов пока нет. Они находятся в путешествиях.'
    elif section=='presets':
        mine={r['slot']:r for r in view['build_presets'] if r['pet_id']==p['id']}
        for slot in (1,2,3):
            row=mine.get(slot)
            if row:
                loaded={'calling':row['build']['calling'],'traits':row['build']['traits'],'talisman_ids':row['build']['talismans']}
                await m.row(('Загрузить '+row['name'],{**common,'draft':loaded}))
            await m.row((f'Сохранить в набор {slot}',{'screen':'preset_confirm','pet_id':p['id'],'slot':slot,'draft':d}))
        text='Три сохранённых набора. Загрузка только меняет черновик; применение подтверждается отдельно.'
    else:
        await m.row(('Призвание', {**common,'section':'calling'}),('Черты', {**common,'section':'traits'}))
        await m.row(('Талисманы', {**common,'section':'talismans'}),('Наборы', {**common,'section':'presets'}))
        if d!=base:await m.row(('Проверить изменения', {**common,'screen':'build_confirm'}))
        text=f"Призвание: {CALLINGS.get(d['calling'],'не выбрано')}\nЧерты: "+(', '.join(TRAITS.get(t,t) for t in d['traits']) or 'не выбраны')+f"\nТалисманы: {len(d['talisman_ids'])}/2\n"+talisman_summary(view,p,d['talisman_ids'])+f"\n\nВыбор пока не применён. Текущая цена замены: {cost(p,d,view)} Эссенции."
    if section:await m.row(('‹ К черновику',common))
    await m.back(p['id']);return f'{title(p)}\n\n<b>Сборка</b>\n'+text


async def build_confirm(m,view,p,data):
    d=data['draft'];price=cost(p,d,view)
    await m.row((f'Применить · {price} Эссенции',{'do':'build','pet_id':p['id'],**d,'expected_essence':price,'expected_build':data['base']}))
    await m.row(('‹ К черновику',{**data,'screen':'build'}));await m.back(p['id'])
    return f'{title(p)}\n\n<b>Применить сборку?</b>\nПризвание: '+CALLINGS.get(d['calling'],'не выбрано')+'\nЧерты: '+(', '.join(TRAITS.get(t,t) for t in d['traits']) or 'нет')+f"\nТалисманы: {len(d['talisman_ids'])}/2\n"+talisman_summary(view,p,d['talisman_ids'])+f"\nЦена: {price} Эссенции. Если сборка или цена уже изменились, оплата не пройдёт."


async def reforge(m,view,p,data):
    t=next((t for t in view['talismans'] if t['id']==data['talisman_id']),None)
    if not t:raise ValueError('Талисман не найден.')
    amount=view['rules']['reforge'].get(str(t['tier']))
    if amount:await m.row((f'Усилить · {amount} Эссенции',{'do':'reforge','talisman_id':t['id'],'expected_tier':t['tier'],'return_pet':p['id']}))
    await m.back(p['id'])
    return f"🧿 <b>{e(TALISMANS.get(t['kind'],t['kind']))} · {t['tier']}</b>\n\n"+(f"Усиление до {t['tier']+1}: {amount} Эссенции. Нужна подходящая мастерская и свободный владелец талисмана." if amount else 'Максимальное усиление.')


async def gear(m,view,p,data):
    g=p['equipment'];key=data.get('item');catalog={i['id']:i for i in view['equipment']['catalog']}
    if not key:
        lines=[title(p),'',f"<b>Снаряжение</b> · деталей {view['equipment']['parts']}"]
        if not g['starter_claimed']:await m.row(('Получить начальный набор',{'do':'gear','pet_id':p['id'],'operation':'starter','item':None,'expected_tier':None}))
        for item in catalog.values():
            tier=g['items'].get(item['id'],0);on=item['id'] in g['equipped'].values()
            await m.row((('✓ ' if on else '')+item['name']+f' · {tier}/3',{'screen':'gear','pet_id':p['id'],'item':item['id']}))
        await m.back(p['id']);return '\n'.join(lines)
    item=catalog.get(key)
    if not item:raise ValueError('Предмет не найден.')
    tier=g['items'].get(key,0);on=key in g['equipped'].values();operation=data.get('operation')
    price=view['equipment']['craft_cost'] if not tier else view['equipment']['upgrade_cost'].get(tier,view['equipment']['upgrade_cost'].get(str(tier)))
    if operation:
        await m.row((f'Подтвердить · {price} деталей',{'do':'gear','pet_id':p['id'],'operation':operation,'item':key,'expected_tier':tier}))
    else:
        if tier:await m.row(('Снять' if on else 'Надеть',{'do':'gear','pet_id':p['id'],'operation':'unequip' if on else 'equip','item':key,'expected_tier':None}))
        if price is not None:await m.row((('Изготовить' if not tier else 'Улучшить')+f' · {price} деталей',{'screen':'gear','pet_id':p['id'],'item':key,'operation':'craft' if not tier else 'upgrade'}))
    await m.row(('‹ Снаряжение',{'screen':'gear','pet_id':p['id']}))
    return f"{item['icon']} <b>{e(item['name'])} · {tier}/3</b>\n\n"+e('\n'.join(f"{i+1}: {effect}" for i,effect in enumerate(item['effects'])))+f"\n\nДеталей: {view['equipment']['parts']}"+('\nБудет потрачено '+str(price)+' деталей.' if operation else '')
