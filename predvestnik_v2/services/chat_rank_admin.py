"""Chat-local rank editor; permissions never grant a global staff role."""
from core.chat_rank_policy import ACTIONS, ACTION_BY_KEY, RANKS, OWNER, rank_name
from infrastructure.repositories import chat_rank_rights as repo

class RightsError(ValueError):
    pass

class StaleRights(RightsError):
    pass

class Denied(PermissionError):
    pass

def authorize(actor):
    if actor.get('kind','staff') != 'staff' or actor.get('rank',0)<5:
        raise Denied('Права рангов в админке меняет разработчик или создатель.')

async def snapshot(db, chat_id):
    current=await repo.read(db,chat_id)
    return {'values':current,'ranks':[{'rank':i,'name':rank_name(i)} for i in range(len(RANKS))],
            'actions':[{'key':a.key,'title':a.label,'default':a.default} for a in ACTIONS]}

async def update(db, actor, chat_id, *, changes, expected, reason):
    authorize(actor)
    if not isinstance(changes,dict) or not changes or len(changes)>len(ACTIONS):
        raise RightsError('Выберите хотя бы одно право.')
    if not isinstance(expected,dict) or set(expected)!=set(changes):
        raise RightsError('Обновите карточку чата перед сохранением.')
    for key,value in changes.items():
        if key not in ACTION_BY_KEY or type(value) is not int or not 0<=value<=OWNER:
            raise RightsError('Неизвестное право или ранг вне диапазона 0–9.')
        if type(expected[key]) is not int:
            raise RightsError('Некорректное исходное значение.')
    reason=str(reason or '').strip()
    if not 3<=len(reason)<=200:
        raise RightsError('Укажите причину: от 3 до 200 символов.')
    async with db.connection.transaction():
        await repo.lock(db,chat_id)
        if not await repo.exists(db,chat_id): raise RightsError('Чат не найден.')
        current=await repo.read(db,chat_id)
        if any(current[k]!=expected[k] for k in changes):
            raise StaleRights('Права уже изменились. Обновите карточку и повторите выбор.')
        before={k:current[k] for k in changes}
        await repo.write(db,chat_id,changes,actor['id'])
        await repo.audit(db,actor['id'],chat_id,before,changes,reason)
    return {'ok':True,'message':'Права чата сохранены. Бот применяет их сразу.'}
