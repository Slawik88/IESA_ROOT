"""Server-owned dust sources and atomic VIP exchanges without calendar limits. Never grants tradable currency."""
from datetime import datetime,timedelta,timezone
import secrets
from uuid import uuid4

from core import star_dust as rules
from infrastructure.repositories import star_dust as repo,system_flags,vip_v2 as vip_repo


def action(value):
    if not isinstance(value,str) or not 8<=len(value)<=96 or any(ord(c)<33 for c in value):
        raise rules.DustError('Повторите действие из свежего меню.')
    return value


async def enabled(db):return await system_flags.is_enabled(db,'star_dust_v1')


async def _instant(db,value):
    # Existing VIP storage is timestamp without time zone. Interpret it in the
    # database session's zone (including DST), never in the client machine's zone.
    if value is None or value.tzinfo:return value
    async with db.execute('SELECT ?::timestamp::timestamptz',(value,)) as c:return (await c.fetchone())[0]


async def overview(db,user_id):
    clock=await repo.clock(db);today=clock['day']
    balance=await repo.balance(db,user_id)
    async with db.execute('SELECT expires_at FROM vip_subscriptions WHERE user_id=?',(int(user_id),)) as c:
        row=await c.fetchone()
    expiry=await _instant(db,row[0]) if row else None
    return {'user_id':int(user_id),'policy_version':rules.POLICY_VERSION,'enabled':await enabled(db),'balance':balance,
            'pet_today':await repo.pet_today(db,user_id,today),
            'pet_fraction':(await repo.pet_remainder(db,user_id))/rules.UNITS_PER_DUST,
            'chat_ready':not bool(await repo.income(db,user_id,'chat',today.isoformat())),
            'next_chat_at':datetime.combine(today+timedelta(days=1),datetime.min.time(),timezone.utc).isoformat(),
            'vip':{'day_cost':rules.VIP_DAY_COST,'max_days':balance//rules.VIP_DAY_COST,
                   'active':bool(expiry and expiry>clock['now']),'expires_at':expiry.isoformat() if expiry else None}}


async def search(db,*,user_id:int) -> dict:
    if not await enabled(db):raise rules.DustError('Звёздная пыль пока недоступна.')
    async with db.connection.transaction():
        balance=await repo.lock_user(db,user_id);clock=await repo.clock(db);source=clock['day'].isoformat()
        previous=await repo.income(db,user_id,'chat',source)
        if previous:
            score=int(previous['luck_micros'])/rules.LUCK_STEPS
            return {'amount':int(previous['amount']),'raw_amount':int(previous['raw_amount']),'luck':rules.luck_view(score,int(previous['raw_amount'])),
                    'already_claimed':True,'balance':balance}
        roll=secrets.randbelow(rules.LUCK_STEPS+1);score=roll/rules.LUCK_STEPS;raw=rules.chat_reward(score)
        amount=raw
        await repo.grant(db,uid=user_id,kind='chat',source_id=source,day=clock['day'],amount=amount,raw=raw,luck=roll,
                         snapshot={'policy_version':rules.POLICY_VERSION})
        return {'amount':amount,'raw_amount':raw,'luck':rules.luck_view(score,raw),'already_claimed':False,'balance':balance+amount}


async def grant_pet_in_transaction(db,*,user_id:int,run:dict) -> dict:
    """Only claim_run calls this with its locked durable terminal. No reward for a companion or client score."""
    if not await enabled(db):return {'amount':0,'disabled':True}
    if int(run['user_id']) != int(user_id):raise rules.DustError('Чужое путешествие.')
    rules.pet_reward(run['kind'],int(run['hours']))
    start,end=run['starts_at'],run['ends_at']
    clock=await repo.clock(db)
    if end>clock['now'] or end<start:raise rules.DustError('Звёздный след ещё не собран.')
    # No collection outside the scheduled trip, even if claiming months later.
    if end-start>timedelta(hours=int(run['hours']),seconds=1):raise rules.DustError('Некорректная длительность пути.')
    balance=await repo.lock_user(db,user_id);previous=await repo.income(db,user_id,'pet',str(run['id']))
    if previous:return {'amount':int(previous['amount']),'idempotent_replay':True,'balance':balance}
    rate=rules.pet_rate(run['kind'])
    epoch=datetime(1970,1,1,tzinfo=timezone.utc)
    def micros(value):
        d=value-epoch
        return (d.days*86400+d.seconds)*1_000_000+d.microseconds
    covered=await repo.overlaps(db,user_id,start,end)
    units=rules.new_coverage_units(micros(start),micros(end),rate,
        [(micros(r['starts_at']),micros(r['ends_at']),int(r['rate'])) for r in covered])
    amount,remainder=divmod(await repo.pet_remainder(db,user_id)+units,rules.UNITS_PER_DUST)
    await repo.save_coverage(db,user_id,run['id'],start,end,rate,units,remainder)
    await repo.grant(db,uid=user_id,kind='pet',source_id=str(run['id']),day=clock['day'],amount=amount,raw=amount,
                     snapshot={'policy_version':rules.POLICY_VERSION,'kind':run['kind'],'hours':int(run['hours']),
                               'pet_id':int(run['pet_id']),'coverage_units':units,'remainder':remainder})
    return {'amount':amount,'balance':balance+amount,'fraction':remainder/rules.UNITS_PER_DUST,
            'shared_trail':True,'new_trail':units>0}


async def buy_vip(db,*,user_id:int,days:int,action_id:str,expected_cost:int|None=None) -> dict:
    action_id=action(action_id)
    if isinstance(days,bool) or not isinstance(days,int) or not 1<=days<=2_147_483_647:
        raise rules.DustError('Выберите целое положительное число дней VIP.')
    if not await enabled(db):raise rules.DustError('Обмен звёздной пыли пока недоступен.')
    async with db.connection.transaction():
        balance=await repo.lock_user(db,user_id)
        await vip_repo.lock_user(db,int(user_id))
        previous=await repo.vip_receipt(db,user_id,action_id)
        if previous:
            if previous['days']!=days or (expected_cost is not None and previous['cost']!=expected_cost):
                raise rules.DustError('Этот запрос уже использован для другого обмена.')
            return {'days':days,'cost':int(previous['cost']),'balance':balance,'expires_at':previous['expires_after'].isoformat(),'replayed':True}
        cost=days*rules.VIP_DAY_COST
        if expected_cost is not None and expected_cost!=cost:raise rules.DustError('Цена изменилась. Подтвердите обмен в свежем меню.')
        current=await vip_repo.current_subscription_for_update(db,user_id=int(user_id))
        before=await _instant(db,current['expires_at']) if current else None
        if balance<cost:raise rules.DustError(f'Не хватает звёздной пыли: нужно {cost}.')
        after_balance=await repo.debit(db,user_id,cost)
        if after_balance is None:raise rules.DustError('Баланс уже изменился. Откройте меню заново.')
        after=await _instant(db,await vip_repo.extend_subscription(db,user_id=int(user_id),days=days))
        await repo.save_vip(db,receipt_id=uuid4().hex,uid=user_id,action_id=action_id,days=days,cost=cost,
                            before=before,after=after,version=rules.POLICY_VERSION)
        return {'days':days,'cost':cost,'balance':after_balance,'expires_at':after.isoformat(),'replayed':False}
