"""Shared compact Telegram views for the current pets v2 services."""
from html import escape
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from infrastructure.repositories import pet_chat

ROUTES = {'forest':'Лес','pass':'Перевал','ruins':'Руины','swamp':'Болото','any':'Любой маршрут'}
KINDS = {'trek':'Поход','expedition':'Экспедиция','watch':'Дозор'}
PATHS = {'careful':'Осторожно','steady':'Ровно','bold':'Смело'}
BUILDINGS = {'lounge':'Привал','markers':'Метки','workshop':'Мастерская'}
CALLINGS = {'tracker':'Следопыт','feeder':'Заботливый','guardian':'Хранитель','seeker':'Искатель'}


def e(value): return escape(str(value))
def num(value): return f'{value:g}' if isinstance(value,float) else str(value)
def name(pet):
    from core.chests_v1 import PET_SPECIES
    return str(pet.get('name') or '').strip() or PET_SPECIES.get(pet['species_id'],{}).get('name',pet['species_id'])
def title(pet): return f"{pet.get('icon','🐾')} {e(name(pet))}"
def pet(view, pet_id):
    return next((p for p in view['pets'] if p['id']==int(pet_id)),None)
def draft(p): return {'calling':p['calling'],'traits':list(p['traits']),'talisman_ids':list(p['talismans'])}


class Menu:
    def __init__(self,db,uid,chat): self.db,self.uid,self.chat=db,uid,chat; self.rows=[]
    async def button(self,label,**payload):
        token=await pet_chat.save(self.db,self.uid,self.chat,payload)
        return InlineKeyboardButton(text=label,callback_data='pt:'+token)
    async def row(self,*buttons):
        self.rows.append([await self.button(label,**payload) for label,payload in buttons])
    async def back(self,pet_id=None):
        await self.row(('‹ К питомцу',{'screen':'pet','pet_id':pet_id}) if pet_id else ('‹ Питомцы',{'screen':'home'}))
    @property
    def keyboard(self): return InlineKeyboardMarkup(inline_keyboard=self.rows)


async def home(m,view,screen='home'):
    if not view['pets']:
        from core.miniapp_links import miniapp_url
        url=miniapp_url('chests')
        if url:m.rows.append([InlineKeyboardButton(text='Найти питомца в сундуках',url=url)])
        return '🐾 <b>Питомцы</b>\n\nПока нет питомцев. Найти первого можно в сундуках. После этого всё управление доступно здесь.'
    lines=['🐾 <b>Питомцы</b>',f"В пути: {len(view['activities'])}/{view['slots']} · Следы сегодня {num(view['daily']['credited'])}/{view['daily']['max']}"]
    if view.get('star_dust') and not view['star_dust'].get('disabled'):
        lines.append(f"🌠 Звёздная пыль: {view['star_dust'].get('balance',0)}")
    for run in view['activities']:
        p=pet(view,run['pet_id'])
        label=title(p) if p else 'Питомец'
        lines.append(f"\n{label} · {KINDS[run['kind']]}\n"+('Готов вернуться ✓' if run['ready'] else 'Вернётся '+remaining(view,run['ends_at'])))
        if run['ready']:await m.row(('Вернуть: '+(name(p) if p else 'питомца'),{'screen':'claim','run_id':run['id']}))
    for p in view['pets'][:8]:
        state='Вылазка' if p['outing'] else 'В пути' if p['run_id'] else f"{num(p['energy'])}/{p['energy_max']} сил"
        await m.row((f"{p['icon']} {name(p)} · {state}",{'screen':'pet','pet_id':p['id']}))
    await m.row(('Лагерь',{'screen':'camp'}),('Испытание',{'screen':'trial'}))
    await m.row(('Бестиарий',{'screen':'bestiary'}),('Все питомцы',{'screen':'collection'}))
    if view['equipment']['open']:await m.row(('Продолжить вылазку',{'screen':'outing'}))
    if view['track']['open']:await m.row(('Продолжить поиск',{'screen':'track'}))
    if view.get('star_dust',{} ) and view['star_dust'].get('enabled'):
        token=await pet_chat.save(m.db,m.uid,m.chat,{'scope':'star_dust'})
        m.rows.append([InlineKeyboardButton(text='🌠 Звёздная пыль · VIP за игру',callback_data='sd:'+token)])
    await m.row(('Обновить',{'screen':'home'}),('Как играть',{'screen':'help'}))
    return '\n'.join(lines)


def remaining(view, value):
    from datetime import datetime
    seconds=max(0,int((datetime.fromisoformat(value)-datetime.fromisoformat(view['now'])).total_seconds()))
    hours,minutes=seconds//3600,(seconds%3600)//60
    return f'через {hours} ч {minutes} мин' if hours else f'через {max(1,minutes)} мин'


async def card(m,view,p):
    busy=p['run_id'] or p['outing']
    lines=[f"{title(p)} · <b>{p['level']} ур.</b>",f"<blockquote>Силы {num(p['energy'])}/{p['energy_max']}\nСледы {num(p['xp'])}"+(f"/{p['next_cost']}" if p['next_cost'] else '')+f"\nСвязь {p['bond_days']} дн. · предел {p['ceiling']} ур.\nЛюбимый маршрут: {ROUTES[p['favorite_route']]}</blockquote>"]
    if busy:
        lines.append('Сейчас в пути. Сборку и снаряжение можно менять после возвращения.')
        if p['outing']:await m.row(('Продолжить вылазку',{'screen':'outing'}))
        else:
            run=next(r for r in view['activities'] if r['id']==p['run_id'])
            lines.append('Готов вернуться ✓' if run['ready'] else 'Вернётся '+remaining(view,run['ends_at']))
            if run['ready']:await m.row(('Забрать награду',{'screen':'claim','run_id':run['id']}))
    else:
        await m.row(('Отправить',{'screen':'prepare','pet_id':p['id']}),('Покормить',{'screen':'feed','pet_id':p['id']}))
        await m.row(('Снаряжение',{'screen':'gear','pet_id':p['id']}),('Сборка',{'screen':'build','pet_id':p['id']}))
        await m.row(('Вылазка',{'screen':'outing','pet_id':p['id']}),('Выслеживание',{'screen':'track','pet_id':p['id']}))
    await m.back()
    return '\n\n'.join(lines)


async def prepare(m,view,p,data):
    kind=data.get('kind')
    if not kind:
        for k,label in KINDS.items():await m.row((label,{'screen':'prepare','pet_id':p['id'],'kind':k}))
        await m.back(p['id']);return f'{title(p)}\n\n<b>Куда отправить?</b>\nПоход — спокойная прогулка. Экспедиция — с развилкой при возвращении. Дозор — надолго без выбора маршрута.'
    request={'pet_id':p['id'],'kind':kind}
    if 'hours' not in data:
        for h in view['durations']['watch' if kind=='watch' else 'run']:await m.row((f'{h} часов',{'screen':'prepare',**request,'hours':h}))
        await m.back(p['id']);return f'{title(p)}\n\n<b>{KINDS[kind]} · на сколько?</b>\nСилы {num(p["energy"])}/{p["energy_max"]}'
    request['hours']=data['hours']
    if kind!='watch' and 'route' not in data:
        for r in view['routes']:
            await m.row((ROUTES[r]+(' · любимый' if p['favorite_route']==r else ''),{'screen':'prepare',**request,'route':r}))
        await m.back(p['id']);return f'{title(p)}\n\n<b>Выбери маршрут</b>'
    request['route']=None if kind=='watch' else data['route']
    if kind!='watch' and view['pair']['unlocked'] and 'companion_id' not in data:
        await m.row(('Без спутника',{'screen':'prepare',**request,'companion_id':None}))
        page=max(0,int(data.get('page',0)))
        mates=[mate for mate in view['pets'] if mate['id']!=p['id'] and not mate['run_id'] and not mate['outing']]
        for mate in mates[page*6:page*6+6]:
            if mate['id']!=p['id'] and not mate['run_id'] and not mate['outing']:
                await m.row((f"В паре: {name(mate)}",{'screen':'prepare',**request,'companion_id':mate['id']}))
        if page:await m.row(('‹ Назад',{'screen':'prepare',**request,'page':page-1}))
        if (page+1)*6<len(mates):await m.row(('Дальше ›',{'screen':'prepare',**request,'page':page+1}))
        await m.back(p['id']);return f'{title(p)}\n\n<b>Взять спутника?</b>\nЕго энергия и занятость тоже учитываются.'
    request['companion_id']=data.get('companion_id')
    from services import pets_v2
    quote=await pets_v2.preview_run(m.db,user_id=m.uid,**request)
    text=f"{title(p)}\n\n<b>{KINDS[kind]} · {request['hours']} ч</b>\n"+(ROUTES.get(request['route'],'Дозор')+f" · {quote['energy_cost']} сил\nСледы: {num(quote['min']['credited'])}–{num(quote['max']['credited'])}\n\n"+e(quote['notice']))
    if request['companion_id']:
        mate=pet(view,request['companion_id'])
        text+=f"\n\nСпутник: {title(mate)} · {view['rules']['energy']['pair']} сил."
    if view.get('star_dust'):
        text+='\n\n🌠 Звёздный след общий для отряда: поход и экспедиция — 2 пыли/ч, дозор — 1 за 5 ч. Перекрытия путей не умножают пыль; дробная часть сохраняется.'
    if quote['can_start']:await m.row(('Отправить',{'do':'start',**request}))
    else:text+='\n\n'+e(' '.join(quote['reasons']))
    await m.back(p['id']);return text
