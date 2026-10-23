"""Activity, feeding, camp and short-game screens, all driven by current server projections."""
from bot.chat.pet_menu import e,num,name,title,pet,ROUTES,KINDS,PATHS,BUILDINGS,remaining


async def feed(m,view,p):
    rows=[]
    for food in view['foods']:
        favorite=food['id']==p['favorite_food']
        if favorite: rows.append(f"Любимое: {e(food['name'])} · {'уже ел сегодня' if p['fed_favorite'] else '+Выдержка'}")
        if food['quantity']:
            await m.row((f"{food['icon']} {food['name']} · {food['quantity']} шт.",{'screen':'feed_confirm','pet_id':p['id'],'food_id':food['id']}))
    if not any(f['quantity'] for f in view['foods']):rows.append('Еды пока нет. Лакомства находятся в путешествиях и сундуках.')
    await m.back(p['id'])
    return f"{title(p)}\n\n<b>Покормить</b> · силы {num(p['energy'])}/{p['energy_max']}\n"+'\n'.join(rows)


async def feed_confirm(m,view,p,data):
    food=next((f for f in view['foods'] if f['id']==data['food_id']),None)
    if not food:raise ValueError('Еда не найдена.')
    if food['quantity']:
        await m.row(('Дать лакомство',{'do':'feed','pet_id':p['id'],'food_id':food['id']}))
    await m.back(p['id'])
    restored=min(food['restore'],max(0,p['energy_max']-p['energy']))
    lines=[title(p),'',f"<b>{e(food['name'])}</b> · 1 шт.",
           f"Сейчас восстановит {num(restored)} сил: {num(p['energy'])} → {num(min(p['energy_max'],p['energy']+restored))}/{p['energy_max']}.",
           f"Осталось {food['quantity']} шт."]
    if not restored:lines.append('Силы уже полные. Лакомство всё равно расходуется.')
    elif restored<food['restore']:lines.append('Часть восстановления не поместится в запас сил.')
    if food['id']==p['favorite_food']:
        lines.append('Любимый вкус: бонус Выдержки сегодня уже действует.' if p['fed_favorite'] else 'Любимый вкус: даст бонус Выдержки на сегодня.')
    lines.append('Кормление расходует одно лакомство.' if food['quantity'] else 'Это лакомство уже закончилось. Выбери другое.')
    return '\n'.join(lines)


async def claim(m,view,data):
    run=next((r for r in view['activities'] if r['id']==data['run_id']),None)
    if not run:await m.back();return 'Путешествие уже завершено. Обнови список питомцев.'
    p=pet(view,run['pet_id'])
    if not run['ready']:await m.back(p['id']);return f"{title(p)}\n\nВернётся {remaining(view,run['ends_at'])}."
    if run['kind']=='expedition':
        hints=run.get('decision',{}).get('paths',{})
        rows=[]
        for path,label in PATHS.items():
            hint=hints.get(path,{})
            chance=f"{hint['chance']}%" if 'chance' in hint else '–'.join(map(str,hint['range']))+'%' if 'range' in hint else hint.get('sign','')
            rewards=view['rules']['paths'][path]['reward']
            rows.append(f"{label}: {e(chance)} · награда ×{rewards[0]} / ×{rewards[1]} / ×{rewards[2]}")
            await m.row((label,{'do':'claim','run_id':run['id'],'path':path}))
        text=f'{title(p)}\n\n<b>Развилка экспедиции</b>\n'+'\n'.join(rows)+'\n\nМножители: успех / частично / неудача. Выбор завершит экспедицию.'
    else:
        await m.row(('Забрать награду',{'do':'claim','run_id':run['id'],'path':None}))
        text=f"{title(p)}\n\n<b>{KINDS[run['kind']]} завершён</b>\nМожно забрать находки и освободить питомца."
    await m.back(p['id']);return text


async def camp(m,view,data):
    camp=view['camp'];job=camp['job'];building=data.get('building')
    if building:
        cost=camp['next_costs'][building]
        if cost and not (job and not job['done']):
            await m.row(('Начать улучшение',{'do':'camp','building':building,'expected_level':camp['levels'][building]}))
        await m.row(('‹ Лагерь',{'screen':'camp'}))
        return f"🏕 <b>{BUILDINGS[building]} · {camp['levels'][building]} → {camp['levels'][building]+1}</b>\n\n"+(f"Цена: {cost['mora']} Моры + {cost['essence']} Эссенции\nВремя: {cost.get('hours',0)} ч.\nОплата при начале улучшения." if cost else 'Достигнут максимальный уровень.')
    lines=['🏕 <b>Лагерь</b>']
    if job:lines.append(f"{BUILDINGS[job['building']]} → {job['to_level']} · "+('готово ✓' if job['done'] else remaining(view,job['ends_at'])))
    for b,label in BUILDINGS.items():
        lines.append(f"{label}: {camp['levels'][b]}/5")
        if camp['next_costs'][b] and not (job and not job['done']):await m.row((f'Улучшить {label.lower()}',{'screen':'camp','building':b}))
    lines.append('\nПривал помогает восстанавливать силы; метки смягчают повтор маршрута; мастерская открывает усиление талисманов.')
    await m.back();return '\n'.join(lines)


async def trial(m,view,data):
    t=view['trial'];tags=t['tags'];p=pet(view,data['pet_id']) if data.get('pet_id') else None
    lines=['🏆 <b>Испытание недели</b>',f"{ROUTES[tags['route']]} · {tags['tempo']} ч · {PATHS[tags['style']]}" ]
    if t['done']:lines.append('Испытание этой недели уже сдано ✓')
    elif p:
        lines.append(f"\n{title(p)} · совпадений {p['trial']['matches']}/3")
        for difficulty in (1,2,3):
            if p['trial']['matches']>=difficulty:
                if data.get('difficulty')==difficulty:
                    lines.append(f"\nПодтвердить сложность {difficulty}? Доступна одна сдача за неделю.")
                    await m.row(('Сдать испытание',{'do':'trial','pet_id':p['id'],'difficulty':difficulty,'expected_week':t['week']}))
                elif 'difficulty' not in data:
                    reward=t['essence'].get(str(difficulty),t['essence'].get(difficulty,0))
                    await m.row((f'Сложность {difficulty} · {reward} Эссенции',{'screen':'trial','pet_id':p['id'],'difficulty':difficulty}))
    else:
        page=max(0,int(data.get('page',0)))
        for p in view['pets'][page*8:page*8+8]:
            await m.row((f"{name(p)} · {p['trial']['matches']}/3",{'screen':'trial','pet_id':p['id']}))
        if page:await m.row(('‹ Назад',{'screen':'trial','page':page-1}))
        if (page+1)*8<len(view['pets']):await m.row(('Дальше ›',{'screen':'trial','page':page+1}))
    await m.back();return '\n'.join(lines)


async def track(m,view,data,result=None):
    t=view['track']['open'] or (result or {}).get('track');p=pet(view,data['pet_id']) if data.get('pet_id') else None
    if not t:
        if p and view['track']['attempts_left']:await m.row(('Начать поиск',{'do':'track_start','pet_id':p['id']}))
        await m.back(p['id'] if p else None)
        return '🔎 <b>Выслеживание</b>\n\nНайди тайник на поле 3×3. Три открытые клетки подскажут: тепло — рядом, холодно — дальше.\n'+f"Попыток сегодня: {view['track']['attempts_left']}"+('\nСначала выбери питомца: бот выслеживание.' if not p else '')
    opened={o['cell']:o['heat'] for o in t['opened']};icons={'warm':'♨','cold':'❄','found':'🎁'}
    for row in range(3):
        buttons=[]
        for col in range(3):
            cell=row*3+col;label=icons.get(opened.get(cell),str(cell+1))
            payload={'do':'track_open','track_id':t['id'],'cell':cell} if cell not in opened and t['status']=='open' else {'screen':'track'}
            buttons.append((label,payload))
        await m.row(*buttons)
    await m.back()
    return '🔎 <b>Выслеживание</b>\n\n'+(f"Ходов осталось: {t['points']}\n♨ — рядом · ❄ — дальше" if t['status']=='open' else 'Тайник найден ✓' if t['status']=='won' else 'Поиск завершён. В следующий раз пригодятся подсказки.')


async def outing(m,view,data,result=None):
    o=view['equipment']['open'] or (result or {}).get('outing');p=pet(view,data['pet_id']) if data.get('pet_id') else None
    if not o:
        if p and view['equipment']['attempts_left']:await m.row(('Начать вылазку',{'do':'outing_start','pet_id':p['id']}))
        await m.back(p['id'] if p else None)
        return f"🗺 <b>Вылазка</b>\n\nСемь развилок прямо в чате. Нужны силы: {view['equipment']['energy']}.\nПопыток сегодня: {view['equipment']['attempts_left']}.\nВернуться с грузом можно в любой момент."
    if o['status']=='active':
        for c in o['choices']:
            if c['enabled']:await m.row((f"{c['label']} · {c['chance']}%",{'do':'outing_choose','outing_id':o['id'],'step':o['step'],'choice':c['id']}))
        await m.row(('Вернуться с грузом',{'do':'outing_choose','outing_id':o['id'],'step':o['step'],'choice':'leave'}))
        choices='\n'.join(f"• {e(c['label'])}: +{c['gain']} груза"+(f", −{c['supply_cost']} запасов" if c['supply_cost'] else '')+(f", риск −{c['damage']} здоровья" if c['damage'] else '')+(f" · {e(c['disabled_reason'])}" if not c['enabled'] else '') for c in o['choices'])
        text=f"🗺 <b>{e(o['event'])}</b> · {o['step']+1}/{o['steps']}\n<blockquote>Здоровье {o['hp']}/4\nЗапасы {o['supplies']}/5\nГруз {o['cargo']}/32</blockquote>\n{choices}"
    else:text=f"🗺 <b>Вылазка закончилась</b>\n\nПолучено деталей: {o['reward'] or 0}. Ими можно изготовить и улучшить снаряжение."
    await m.back();return text
