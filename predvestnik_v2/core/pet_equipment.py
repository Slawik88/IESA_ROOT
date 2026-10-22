"""Five functional pet slots and a short, resource-based outing. No I/O."""
from copy import deepcopy

SLOTS = {'tool': 'Инструмент', 'boots': 'Обувь', 'guard': 'Защита', 'charm': 'Оберег', 'pack': 'Сумка'}
# slot, name, icon, stat per tier, bonus per tier, outing speciality
ITEMS = {
    'compass': ('tool', 'Компас троп', '🧭', 'xp', .04, 'navigation'),
    'lens': ('tool', 'Линза находок', '🔍', 'bonus_xp', .15, 'search'),
    'wind_boots': ('boots', 'Ветреные сапожки', '🥾', 'regen', .25, 'crossing'),
    'trail_boots': ('boots', 'Походные сапожки', '🥾', 'energy', 3, 'navigation'),
    'bark_guard': ('guard', 'Кора-доспех', '🛡️', 'resilience', .5, 'crossing'),
    'mist_cloak': ('guard', 'Туманный плащ', '🧥', 'careful', 2, 'stealth'),
    'amber': ('charm', 'Янтарная искра', '🔶', 'xp', .03, 'search'),
    'silver_bell': ('charm', 'Серебряный звон', '🔔', 'resilience', .5, 'stealth'),
    'food_pack': ('pack', 'Сумка припасов', '🎒', 'energy', 3, 'camp'),
    'sample_pack': ('pack', 'Сумка собирателя', '👜', 'treat', .10, 'search'),
}
STARTERS = ('compass', 'wind_boots', 'bark_guard', 'amber', 'food_pack')
CRAFT_COST, UPGRADE_COST = 8, {1: 12, 2: 24}
DAILY_OUTINGS, OUTING_ENERGY, STEPS = 3, 10, 7
STAT_NAMES = {'xp': 'Следов', 'bonus_xp': 'к склонности находить дополнительные Следы', 'regen': 'энергии в час',
              'energy': 'к запасу энергии', 'resilience': 'Выдержки', 'careful': 'п.п. шанса осторожного пути', 'treat': 'к склонности находить лакомства'}


def gear(value=None):
    import json
    if isinstance(value, str): value = json.loads(value)
    value = value or {}
    items = {k: int(v) for k, v in value.get('items', {}).items() if k in ITEMS and type(v) is int and 1 <= v <= 3}
    equipped = {s: k for s, k in value.get('equipped', {}).items() if k in items and ITEMS[k][0] == s}
    return {'items': items, 'equipped': equipped, 'starter_claimed': bool(value.get('starter_claimed')), 'revision': int(value.get('revision',0))}


def active(value=None):
    g = gear(value)
    return tuple((k, g['items'][k]) for k in g['equipped'].values())


def effects(value=()):
    out = {'xp': 1., 'bonus_xp': 1., 'treat': 1., 'regen': 0., 'energy': 0, 'resilience': 0., 'careful': 0.}
    slots = set()
    for key, tier in value:
        if key not in ITEMS or type(tier) is not int or not 1 <= tier <= 3 or ITEMS[key][0] in slots:
            raise ValueError('Некорректная экипировка.')
        slot, _, _, stat, amount, _ = ITEMS[key]; slots.add(slot)
        if stat in ('xp', 'bonus_xp', 'treat'): out[stat] *= 1 + amount * tier
        else: out[stat] += amount * tier
    return out


def catalog():
    return [{'id': k, 'slot': v[0], 'name': v[1], 'icon': v[2], 'speciality': v[5],
             'effects': [f'+{round(v[4]*tier*100) if v[3] in ("xp","bonus_xp","treat") else round(v[4]*tier,2)}'
                         f'{" %" if v[3] in ("xp","bonus_xp","treat") else ""} {STAT_NAMES[v[3]]}' for tier in range(1,4)]}
            for k,v in ITEMS.items()]


# Every encounter offers three concrete actions. Numbers are part of the server
# projection, not duplicated in the UI. (title, speciality, options)
# option: label, chance, cargo gain, HP loss on failure, supply cost, heal, supply gain, cargo cost
EVENTS = (
    ('Мост над расселиной', 'crossing', [('Укрепить мост',100,1,0,1,0,0,0),('Перейти по балкам',75,3,1,0,0,0,0),('Спуститься за обломками',45,6,2,0,0,0,0)]),
    ('Заброшенный привал', 'camp', [('Отдохнуть у огня',100,0,0,0,1,0,2),('Собрать припасы',85,1,1,0,0,2,0),('Разобрать тайник',55,5,2,0,0,0,0)]),
    ('Затопленная тропа', 'navigation', [('Построить настил',100,2,0,1,0,0,0),('Искать сухую тропу',70,3,1,0,0,1,0),('Нырнуть к сундуку',45,6,2,0,0,0,0)]),
    ('Чужие огни', 'stealth', [('Скрыться с припасами',100,1,0,1,0,0,0),('Обойти дозор',80,3,1,0,0,0,0),('Забрать забытый груз',50,5,2,0,0,0,0)]),
    ('Зеркальный грот', 'search', [('Осветить проход',100,2,0,1,0,0,0),('Осмотреть стены',75,3,1,0,0,0,0),('Достать дальний осколок',40,7,2,0,0,0,0)]),
    ('Лесная мастерская', 'camp', [('Починить снаряжение',100,0,0,0,2,0,3),('Пополнить запасы',90,1,1,0,0,2,0),('Разобрать механизм',55,5,2,0,0,0,0)]),
    ('Старая обсерватория', 'search', [('Закрепить лестницу',100,2,0,1,0,0,0),('Проверить нижний ярус',80,3,1,0,0,0,0),('Подняться к линзе',45,6,2,0,0,0,0)]),
    ('Шепчущая роща', 'stealth', [('Поставить метки',100,1,0,1,0,0,0),('Пойти на тихий звон',75,3,1,0,0,1,0),('Открыть дупло',50,5,2,0,0,0,0)]),
    ('Развилка без указателя', 'navigation', [('Свериться с картой',100,2,0,1,0,0,0),('Искать следы',80,3,1,0,0,0,0),('Срезать через осыпь',45,6,2,0,0,0,0)]),
)


def new_outing(deck, equipment):
    return {'version': 1, 'deck': list(deck), 'step': 0, 'hp': 4, 'supplies': 3, 'cargo': 0,
            'equipment': list(equipment), 'status': 'active', 'log': [], 'reward': None}


def choices(state):
    if state['status'] != 'active': return []
    _, speciality, options = EVENTS[state['deck'][state['step']]]
    bonus = min(15, sum(3*tier for k,tier in state['equipment'] if ITEMS[k][5] == speciality))
    return [{'id': i, 'label': o[0], 'chance': min(100 if o[1] == 100 else 95, o[1]+bonus),
             'gain': min(o[2],32-state['cargo']+o[7]), 'damage': o[3], 'supply_cost': o[4], 'heal': min(o[5],4-state['hp']), 'supplies': min(o[6],5-state['supplies']+o[4]), 'cargo_cost': o[7],
             'enabled': state['supplies'] >= o[4] and state['cargo'] >= o[7] and (not o[5] or state['hp']<4),
             'disabled_reason': 'Здоровье полное' if o[5] and state['hp']==4 else 'Не хватает запасов', 'gear_bonus': bonus if o[1] < 100 else 0}
            for i,o in enumerate(options)]


def advance(state, choice, roll):
    s = deepcopy(state)
    if s['status'] != 'active': raise ValueError('Вылазка уже закончилась.')
    if choice == 'leave':
        s.update(status='returned', reward=s['cargo']); return s
    if type(choice) is not int or not 0 <= choice < 3 or not 0 <= roll < 100:
        raise ValueError('Выбери действие на текущей развилке.')
    option = choices(s)[choice]
    if not option['enabled']: raise ValueError(option['disabled_reason'])
    success = roll < option['chance']
    s['supplies'] -= option['supply_cost']; s['cargo'] -= option['cargo_cost']
    if success:
        s['cargo'] = min(32, s['cargo'] + option['gain'])
        s['hp'] = min(4, s['hp'] + option['heal']); s['supplies'] = min(5, s['supplies'] + option['supplies'])
    else: s['hp'] = max(0, s['hp'] - option['damage'])
    s['log'].append({'event': EVENTS[s['deck'][s['step']]][0], 'action': option['label'], 'success': success,
                     'gain': option['gain'] if success else 0, 'damage': 0 if success else min(state['hp'],option['damage']),
                     'heal': option['heal'] if success else 0, 'supplies': option['supplies'] if success else 0,
                     'spent_parts': option['cargo_cost'], 'spent_supplies': option['supply_cost']})
    s['step'] += 1
    if s['hp'] == 0: s.update(status='rescued', reward=s['cargo']//2)
    elif s['step'] == STEPS: s.update(status='completed', reward=min(32, s['cargo']+3))
    return s


def outing_view(row):
    s = row['state']
    return {k: s[k] for k in ('step','hp','supplies','cargo','status','log','reward')} | {
        'id': row['id'], 'pet_id': int(row['pet_id']), 'steps': STEPS, 'choices': choices(s),
        'event': EVENTS[s['deck'][s['step']]][0] if s['status'] == 'active' else None,
        'speciality': EVENTS[s['deck'][s['step']]][1] if s['status'] == 'active' else None}
