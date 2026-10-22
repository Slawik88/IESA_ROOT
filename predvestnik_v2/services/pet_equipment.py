"""One user lock and action receipt for equipment, outing choices and rewards."""
import random
from uuid import uuid4
from core import pet_equipment as rules, pets_v2 as pets
from infrastructure.repositories import pet_equipment as repo, pets_v2 as pr


async def busy_ids(db, user_id):
    runs = await pr.open_runs(db, user_id)
    ids = {int(p) for r in runs for p in (r['pet_id'],r['companion_id']) if p is not None}
    outing = await repo.active_outing(db,user_id)
    if outing: ids.add(int(outing['pet_id']))
    return ids


async def summary(db, user_id, day):
    row = await repo.active_outing(db,user_id)
    last = await repo.latest_closed(db,user_id)
    return {'parts': await repo.parts(db,user_id), 'attempts_left': max(0,rules.DAILY_OUTINGS-await repo.outings_today(db,user_id,day)),
            'open': rules.outing_view(row) if row else None, 'last': rules.outing_view(last) if last else None, 'daily':rules.DAILY_OUTINGS, 'energy':rules.OUTING_ENERGY,
            'slots':rules.SLOTS, 'catalog':rules.catalog(), 'craft_cost':rules.CRAFT_COST, 'upgrade_cost':rules.UPGRADE_COST}


async def _replay(db,user_id,action_id,request):
    row=await pr.cached_action(db,user_id,action_id)
    if row:
        if row['request']!=request: raise pets.PetV2PolicyError('action_id уже использован для другого действия.')
        return row['response'] | {'idempotent_replay':True}


async def _pet(db,user_id,pet_id):
    from services import pets_v2 as service
    pet=await pr.get_owned_pet(db,user_id,pet_id)
    if not pet: raise pets.PetV2PolicyError('Питомец не найден или принадлежит другому игроку.')
    service._species_row(pet)
    if pet_id in await busy_ids(db,user_id): raise pets.PetV2PolicyError('Сначала верни питомца из пути или Вылазки.')
    state=await pr.ensure_state(db,user_id,pet_id,pets.energy_max(1,pet['species_id']))
    return pet,state


async def change(db,*,user_id,pet_id,operation,item,expected_tier,action_id):
    from services import pets_v2 as service
    action_id=service._action(action_id)
    request=dict(type='equipment',pet_id=pet_id,operation=operation,item=item,expected_tier=expected_tier)
    if operation not in ('starter','craft','upgrade','equip','unequip') or (operation!='starter' and item not in rules.ITEMS):
        raise pets.PetV2PolicyError('Неизвестный предмет или действие.')
    async with db.connection.transaction():
        await pr.lock_user(db,user_id)
        replay=await _replay(db,user_id,action_id,request)
        if replay:return replay
        pet,state=await _pet(db,user_id,pet_id)
        value=rules.gear(state.get('equipment')); cost=0
        old_build=service._build(state,await pr.equipped_talismans(db,user_id,pet_id),await pr.camp_levels(db,user_id))
        clock=await pr.clock(db)
        energy=service._rest(state,pet,clock['now'],old_build)
        if operation=='starter':
            if value['starter_claimed']: raise pets.PetV2PolicyError('Начальный набор уже получен.')
            for k in rules.STARTERS:
                value['items'].setdefault(k,1)
                value['equipped'].setdefault(rules.ITEMS[k][0],k)
            value['starter_claimed']=True
        else:
            tier=value['items'].get(item,0)
            if operation in ('craft','upgrade'):
                if expected_tier is None or expected_tier!=tier: raise pets.PetV2PolicyError('Уровень предмета изменился. Обнови экипировку.')
                if operation=='craft' and tier: raise pets.PetV2PolicyError('Этот предмет уже изготовлен.')
                if operation=='upgrade' and tier not in rules.UPGRADE_COST: raise pets.PetV2PolicyError('Улучшать можно предмет I или II уровня.')
                cost=rules.CRAFT_COST if operation=='craft' else rules.UPGRADE_COST[tier]
                if await repo.parts(db,user_id)<cost: raise pets.PetV2PolicyError(f'Не хватает деталей: нужно {cost}.')
                value['items'][item]=tier+1
            elif not tier:raise pets.PetV2PolicyError('Сначала изготовь предмет.')
            elif operation=='equip':value['equipped'][rules.ITEMS[item][0]]=item
            elif value['equipped'].get(rules.ITEMS[item][0])==item:del value['equipped'][rules.ITEMS[item][0]]
        fx=pets.build_effects(state.get('calling'),tuple(service._json_list(state.get('traits'))),equipment=rules.active(value))
        energy=min(energy,pets.energy_max(int(state['level']),pet['species_id'],fx['energy_bonus']))
        await pr.save_state(db,user_id,pet_id,level=int(state['level']),xp=float(state['xp']),energy=energy,pity=int(state['pity']))
        value['revision'] += 1
        await repo.save_gear(db,user_id,pet_id,value)
        if cost:await repo.add_parts(db,user_id,-cost)
        response=dict(ok=True,equipment=value,parts=await repo.parts(db,user_id),spent=cost,energy=round(energy,1),idempotent_replay=False)
        await pr.save_action(db,user_id,action_id,request,response)
        return response


async def start(db,*,user_id,pet_id,action_id,rng=None):
    from services import pets_v2 as service
    action_id=service._action(action_id); rng=rng or random.SystemRandom()
    request=dict(type='outing_start',pet_id=pet_id)
    async with db.connection.transaction():
        await pr.lock_user(db,user_id)
        replay=await _replay(db,user_id,action_id,request)
        if replay:return replay
        if await repo.active_outing(db,user_id):raise pets.PetV2PolicyError('Сначала закончи текущую Вылазку.')
        pet,state=await _pet(db,user_id,pet_id);clock=await pr.clock(db)
        if await repo.outings_today(db,user_id,clock['day'])>=rules.DAILY_OUTINGS:raise pets.PetV2PolicyError('Попытки Вылазки на сегодня закончились.')
        build=service._build(state,await pr.equipped_talismans(db,user_id,pet_id),await pr.camp_levels(db,user_id))
        energy=service._rest(state,pet,clock['now'],build)
        if energy<rules.OUTING_ENERGY:raise pets.PetV2PolicyError(f'Для Вылазки нужно {rules.OUTING_ENERGY} энергии.')
        await pr.save_state(db,user_id,pet_id,level=int(state['level']),xp=float(state['xp']),energy=energy-rules.OUTING_ENERGY,pity=int(state['pity']))
        value=rules.new_outing(rng.sample(range(len(rules.EVENTS)),rules.STEPS),rules.active(state.get('equipment')))
        outing_id=uuid4().hex
        await repo.create_outing(db,user_id,pet_id,outing_id,clock['day'],value)
        response=dict(ok=True,outing=rules.outing_view(dict(id=outing_id,pet_id=pet_id,state=value)),energy=round(energy-rules.OUTING_ENERGY,1),idempotent_replay=False)
        await pr.save_action(db,user_id,action_id,request,response)
        return response


async def choose(db,*,user_id,outing_id,step,choice,action_id,rng=None):
    from services import pets_v2 as service
    action_id=service._action(action_id);rng=rng or random.SystemRandom()
    request=dict(type='outing_choose',outing_id=outing_id,step=step,choice=choice)
    async with db.connection.transaction():
        await pr.lock_user(db,user_id)
        replay=await _replay(db,user_id,action_id,request)
        if replay:return replay
        row=await repo.get_outing(db,user_id,outing_id)
        if not row:raise pets.PetV2PolicyError('Вылазка не найдена.')
        if row['state']['status']!='active' or row['state']['step']!=step:raise pets.PetV2PolicyError('Развилка уже пройдена. Обнови Вылазку.')
        try:value=rules.advance(row['state'],choice,rng.random()*100)
        except ValueError as exc:raise pets.PetV2PolicyError(str(exc)) from exc
        if value['status']!='active':await repo.add_parts(db,user_id,value['reward'])
        await repo.save_outing(db,outing_id,value);row['state']=value
        response=dict(ok=True,outing=rules.outing_view(row),parts=await repo.parts(db,user_id),idempotent_replay=False)
        await pr.save_action(db,user_id,action_id,request,response)
        return response
