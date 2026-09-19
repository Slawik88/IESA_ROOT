"""Server-authoritative quest assignment, rerolls and metric receipts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from core import quests_v1 as rules
from infrastructure.repositories import chests_v1 as chest_repo
from infrastructure.repositories import pets_v1 as pets_repo
from infrastructure.repositories import economy_ledger, quests_v1 as repo, system_flags
from services.chests_v1 import grant_quest_completion_key_in_transaction


class QuestError(Exception):
    pass


class QuestConflict(QuestError):
    pass


# These free rewards intentionally never mint Stars, Zarniki, cosmetics or a
# random item.  They are a modest, transparent Mora reward for the three
# owner-approved completion milestones.
REWARD_POLICY_VERSION = 'quest-rewards-v1-2026-09-06'
REWARD_MORA = {'daily': 20, 'weekly': 100, 'combined': 75}
REWARD_KEYS = {'daily': 1, 'weekly': 1, 'combined': 0}


def _unavailable_overview(*, vip_active: bool) -> dict:
    keys = period_keys()
    limit = rules.VIP_WEEKLY_REROLLS if vip_active else rules.STANDARD_WEEKLY_REROLLS
    return {
        'policy_version': rules.POLICY_VERSION,
        'daily': {'period_key': keys['daily'], 'quests': [], 'all_completed': False},
        'weekly': {'period_key': keys['weekly'], 'quests': [], 'all_completed': False},
        'rerolls': {'used': 0, 'limit': limit, 'remaining': 0},
        'completion': {'daily': False, 'weekly': False, 'combined': False},
        'rewards': {
            'policy_version': REWARD_POLICY_VERSION, 'currency': 'mora',
            'items': {kind: {'amount_mora': REWARD_MORA[kind], 'amount_keys': REWARD_KEYS[kind],
                             'claimed': False, 'claimable': False}
                      for kind in ('daily', 'weekly', 'combined')},
            'key_balance': 0,
            'message': 'Квесты появятся, когда будет доступна хотя бы одна подтверждаемая игра.',
        },
    }


def period_keys(now: datetime | None = None) -> dict[str, str]:
    instant = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    day = instant.date()
    return {'daily': day.isoformat(), 'weekly': (day - timedelta(days=day.weekday())).isoformat()}


def _count(period: str) -> int:
    return rules.DAILY_COUNT if period == 'daily' else rules.WEEKLY_COUNT


def _definition(row: dict) -> dict:
    value = row['definition_json']
    return dict(value) if isinstance(value, dict) else __import__('json').loads(value)


def _public(row: dict) -> dict:
    definition = _definition(row)
    return {
        'slot': int(row['slot']), 'id': str(row['quest_id']), 'title': definition['title'], 'help': definition['help'],
        'metric': definition['metric'], 'lane': definition.get('lane'), 'source': definition.get('source'),
        'progress': int(row['progress']), 'target': int(row['target']),
        'completed': row['completed_at'] is not None,
    }


def _lane(definition: dict) -> str:
    if definition.get('lane'):
        return str(definition['lane'])
    metric = str(definition.get('metric', ''))
    if metric == 'mafia_completed':
        return 'mafia_play'
    if metric.startswith('rhythm'):
        return 'rhythm_play'
    if metric.startswith('minesweeper'):
        return 'mines_play'
    return metric


def _source(definition: dict) -> str:
    if definition.get('source'):
        return str(definition['source'])
    metric = str(definition.get('metric', ''))
    return 'mafia' if metric.startswith('mafia') else 'rhythm' if metric.startswith('rhythm') else 'minesweeper'


def _source_available(definition: dict, sources: frozenset[str] | set[str] | None) -> bool:
    if sources is None:
        return True
    source = _source(definition)
    return source in sources or (source == 'any_game' and bool(set(sources) & {'rhythm', 'minesweeper', 'mafia'}))


def _balanced_sample(definitions: list[dict], count: int) -> list[dict]:
    """Choose distinct lanes and distribute them across available activities."""
    by_lane: dict[str, list[dict]] = {}
    for definition in definitions:
        by_lane.setdefault(_lane(definition), []).append(definition)
    if len(by_lane) < count:
        raise QuestConflict('Недостаточно доступных разных типов квестов.')
    randomizer = secrets.SystemRandom()
    selected_lanes: list[str] = []
    flex_lanes = [lane for lane, variants in by_lane.items() if _source(variants[0]) == 'any_game']
    if flex_lanes:
        selected_lanes.append(randomizer.choice(flex_lanes))
    source_lanes: dict[str, list[str]] = {}
    for lane, variants in by_lane.items():
        source = _source(variants[0])
        if source != 'any_game':
            source_lanes.setdefault(source, []).append(lane)
    source_order = list(source_lanes)
    randomizer.shuffle(source_order)
    while len(selected_lanes) < count and source_order:
        progressed = False
        for source in source_order:
            available = [lane for lane in source_lanes[source] if lane not in selected_lanes]
            if available and len(selected_lanes) < count:
                selected_lanes.append(randomizer.choice(available))
                progressed = True
        if not progressed:
            break
    if len(selected_lanes) < count:
        remaining = [lane for lane in by_lane if lane not in selected_lanes]
        selected_lanes.extend(randomizer.sample(remaining, count - len(selected_lanes)))
    return [randomizer.choice(by_lane[lane]) for lane in selected_lanes]


async def available_sources(db, *, user_id: int) -> frozenset[str]:
    """Live assignment eligibility; Mafia also requires prior participation."""
    sources = set()
    if await system_flags.is_enabled(db, 'game_rhythm_v2'):
        sources.add('rhythm')
    if await system_flags.is_enabled(db, 'game_minesweeper_v2'):
        sources.add('minesweeper')
    if await system_flags.is_enabled(db, 'game_mafia_v1'):
        async with db.execute('SELECT 1 FROM mafia_v1_players WHERE user_id=? LIMIT 1', (int(user_id),)) as cursor:
            if await cursor.fetchone():
                sources.add('mafia')
    if await system_flags.is_enabled(db, 'content_chests_v1') and await chest_repo.get_balance(db, int(user_id)) > 0:
        # A chest quest is assigned only when the player already owns a free or
        # paid entitlement. The daily set must never force the first purchase.
        sources.add('chests')
    owned_pets = await pets_repo.list_owned_pets(db, int(user_id))
    if owned_pets:
        sources.add('pets')
        has_food = any(int(amount) > 0 for amount in (await chest_repo.inventory_summary(
            db, user_id=int(user_id),
        ))['foods'].values())
        can_feed = False
        for pet in owned_pets:
            if pet.get('endurance') is None or pet.get('endurance_updated_at') is None:
                continue
            from core.pets_v1 import endurance_after_elapsed
            endurance, _ = endurance_after_elapsed(
                int(pet['endurance']), last_updated_at=pet['endurance_updated_at'], now=pet['server_now'],
            )
            can_feed = can_feed or endurance < 100
        if has_food and can_feed:
            sources.add('pet_care')
    return frozenset(sources)


async def _ensure_period(db, *, user_id: int, period: str, period_key: str,
                         sources: frozenset[str] | set[str] | None = None) -> list[dict]:
    definitions = list(rules.definitions(period, sources))
    existing = await repo.list_assignments(db, user_id=user_id, period=period, period_key=period_key)
    if existing:
        if len(existing) != _count(period):
            raise QuestConflict('quest assignment set is incomplete; contact support')
        policy_stale = any(_definition(row).get('policy_version') != rules.POLICY_VERSION for row in existing)
        pristine = all(not int(row['progress']) and row['completed_at'] is None for row in existing)
        if policy_stale and not pristine:
            # Never rewrite even the untouched rows of a period once the player
            # has made progress in it. The whole historical set expires intact.
            return existing
        if policy_stale and pristine:
            # A zero-progress set can be upgraded without taking earned work
            # away. Progressed historical sets stay intact until their reset.
            replacements = _balanced_sample(definitions, _count(period))
            ordered = sorted(existing, key=lambda item: int(item['slot']))
            for row in ordered:
                placeholder = {**_definition(row), 'id': f"__quest_migration_{period}_{int(row['slot'])}_{secrets.token_hex(4)}"}
                await repo.replace_assignment(
                    db, user_id=user_id, period=period, period_key=period_key, slot=int(row['slot']),
                    definition=placeholder, generation=int(row['reroll_generation']),
                )
            for row, replacement in zip(ordered, replacements):
                await repo.replace_assignment(
                    db, user_id=user_id, period=period, period_key=period_key, slot=int(row['slot']),
                    definition={**replacement, 'policy_version': rules.POLICY_VERSION},
                    generation=int(row['reroll_generation']),
                )
            return await repo.list_assignments(db, user_id=user_id, period=period, period_key=period_key)
        available_metrics = {definition['metric'] for definition in definitions}
        occupied_lanes: set[str] = set()
        refreshable = []
        for row in existing:
            definition = _definition(row)
            lane = _lane(definition)
            unavailable = definition.get('metric') not in available_metrics or not _source_available(definition, sources)
            duplicate_lane = lane in occupied_lanes
            if (unavailable or duplicate_lane) and not int(row['progress']) and row['completed_at'] is None:
                refreshable.append(row)
            else:
                occupied_lanes.add(lane)
        if refreshable:
            occupied_ids = {str(row['quest_id']) for row in existing}
            candidates = [definition for definition in definitions if definition['id'] not in occupied_ids and _lane(definition) not in occupied_lanes]
            replacements = _balanced_sample(candidates, len(refreshable))
            for row, replacement in zip(refreshable, replacements):
                await repo.replace_assignment(db, user_id=user_id, period=period, period_key=period_key,
                                              slot=int(row['slot']), definition={**replacement, 'policy_version': rules.POLICY_VERSION},
                                              generation=int(row['reroll_generation']))
            return await repo.list_assignments(db, user_id=user_id, period=period, period_key=period_key)
        return existing
    selected = _balanced_sample(definitions, _count(period))
    for slot, definition in enumerate(selected):
        await repo.create_assignment(db, user_id=user_id, period=period, period_key=period_key, slot=slot,
                                     definition={**definition, 'policy_version': rules.POLICY_VERSION})
    return await repo.list_assignments(db, user_id=user_id, period=period, period_key=period_key)


async def _overview_locked(db, *, user_id: int, keys: dict[str, str], vip_active: bool,
                           sources: frozenset[str] | set[str] | None = None) -> dict:
    daily = await _ensure_period(db, user_id=user_id, period='daily', period_key=keys['daily'], sources=sources)
    weekly = await _ensure_period(db, user_id=user_id, period='weekly', period_key=keys['weekly'], sources=sources)
    state = await repo.reroll_state(db, user_id=user_id, week_key=keys['weekly'])
    limit = rules.VIP_WEEKLY_REROLLS if vip_active else rules.STANDARD_WEEKLY_REROLLS
    all_daily = all(row['completed_at'] is not None for row in daily)
    all_weekly = all(row['completed_at'] is not None for row in weekly)
    reward_ids = {
        'daily': f"daily:{keys['daily']}",
        'weekly': f"weekly:{keys['weekly']}",
        # The combined bonus is weekly, not daily.  This prevents a completed
        # weekly set from generating another combined payout every new day.
        'combined': f"combined:{keys['weekly']}",
    }
    claimed = {kind: await repo.reward_receipt_exists(db, user_id=user_id, reward_id=reward_id)
               for kind, reward_id in reward_ids.items()}
    chests_enabled = await system_flags.is_enabled(db, 'content_chests_v1')
    actual_key_grants = {}
    for kind in ('daily', 'weekly'):
        source_kind = f'quest_{kind}_set_complete'
        actual_key_grants[kind] = bool(await chest_repo.find_grant(
            db, user_id=user_id, source_kind=source_kind,
            source_event_id=reward_ids[kind],
        ))
    completion = {'daily': all_daily, 'weekly': all_weekly, 'combined': all_daily and all_weekly}
    rewards = {
        kind: {
            'amount_mora': REWARD_MORA[kind],
            'amount_keys': (1 if claimed[kind] and actual_key_grants.get(kind) else
                            REWARD_KEYS[kind] if not claimed[kind] and chests_enabled else 0),
            'claimed': claimed[kind],
            'claimable': completion[kind] and not claimed[kind],
        }
        for kind in ('daily', 'weekly', 'combined')
    }
    return {
        'policy_version': rules.POLICY_VERSION,
        'daily': {'period_key': keys['daily'], 'quests': [_public(row) for row in daily], 'all_completed': all_daily},
        'weekly': {'period_key': keys['weekly'], 'quests': [_public(row) for row in weekly], 'all_completed': all_weekly},
        'rerolls': {'used': int(state['used_count']), 'limit': limit, 'remaining': max(0, limit - int(state['used_count']))},
        'completion': completion,
        'rewards': {
            'policy_version': REWARD_POLICY_VERSION,
            'currency': 'mora', 'items': rewards,
            'key_balance': await chest_repo.get_balance(db, user_id),
            'message': ('Награды выдаются один раз. Полный день и неделя также дают по одному ключу.'
                        if chests_enabled else 'Награды выдаются один раз.'),
        },
    }


async def overview(db, *, user_id: int, vip_active: bool,
                   sources: frozenset[str] | set[str] | None = None) -> dict:
    if sources is not None and not sources:
        return _unavailable_overview(vip_active=vip_active)
    keys = period_keys()
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        return await _overview_locked(db, user_id=user_id, keys=keys, vip_active=vip_active, sources=sources)


async def reroll(db, *, user_id: int, vip_active: bool, period: str, slot: int, action_id: str,
                 sources: frozenset[str] | set[str] | None = None) -> dict:
    if sources is not None and not sources:
        raise QuestConflict('Сейчас нет доступных источников квестов.')
    if period not in {'daily', 'weekly'} or slot < 0 or slot >= _count(period):
        raise QuestError('Этот квест нельзя заменить.')
    action_id = str(action_id or '').strip()
    if not action_id or len(action_id) > 96:
        raise QuestError('action_id обязателен.')
    request = {'period': period, 'slot': int(slot)}
    keys = period_keys()
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.action(db, user_id=user_id, action_id=action_id)
        if replay:
            if replay['request'] != request:
                raise QuestConflict('action_id уже использован для другого действия.')
            return {**replay['response'], 'idempotent_replay': True}
        assignments = await _ensure_period(db, user_id=user_id, period=period, period_key=keys[period], sources=sources)
        target = next((row for row in assignments if int(row['slot']) == slot), None)
        if not target or target['completed_at'] is not None:
            raise QuestConflict('Завершённый квест заменить нельзя.')
        state = await repo.reroll_state(db, user_id=user_id, week_key=keys['weekly'])
        limit = rules.VIP_WEEKLY_REROLLS if vip_active else rules.STANDARD_WEEKLY_REROLLS
        if int(state['used_count']) >= limit:
            raise QuestConflict('Лимит замен на эту неделю исчерпан.')
        occupied = {str(row['quest_id']) for row in assignments}
        occupied_metrics = {_definition(row)['metric'] for row in assignments if int(row['slot']) != slot}
        occupied_lanes = {_lane(_definition(row)) for row in assignments if int(row['slot']) != slot}
        target_definition = _definition(target)
        candidates = [definition for definition in rules.definitions(period, sources)
                      if definition['id'] not in occupied and definition['metric'] not in occupied_metrics
                      and _lane(definition) not in occupied_lanes
                      and definition['metric'] != target_definition['metric']
                      and _lane(definition) != _lane(target_definition)]
        if not candidates:
            raise QuestConflict('Для замены пока нет другого подходящего квеста.')
        replacement = secrets.choice(candidates)
        await repo.replace_assignment(db, user_id=user_id, period=period, period_key=keys[period], slot=slot,
                                      definition={**replacement, 'policy_version': rules.POLICY_VERSION},
                                      generation=int(target['reroll_generation']) + 1)
        await repo.consume_reroll(db, user_id=user_id, week_key=keys['weekly'])
        response = await _overview_locked(db, user_id=user_id, keys=keys, vip_active=vip_active, sources=sources)
        await repo.save_action(db, user_id=user_id, action_id=action_id, request=request, response=response)
    return response


async def claim_reward(db, *, user_id: int, vip_active: bool, kind: str,
                       sources: frozenset[str] | set[str] | None = None) -> dict:
    if sources is not None and not sources:
        raise QuestConflict('Сейчас нет доступных квестов для награды.')
    """Credit one completed milestone once, atomically with its receipt."""
    if kind not in REWARD_MORA:
        raise QuestError('Неизвестная награда квеста.')
    keys = period_keys()
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        state = await _overview_locked(db, user_id=user_id, keys=keys, vip_active=vip_active, sources=sources)
        reward = state['rewards']['items'][kind]
        if reward['claimed']:
            return {**state, 'reward_result': {'kind': kind, 'already_claimed': True}}
        if not reward['claimable']:
            raise QuestConflict('Сначала заверши нужные квесты.')
        reward_id = (f"daily:{keys['daily']}" if kind == 'daily' else
                     f"weekly:{keys['weekly']}" if kind == 'weekly' else f"combined:{keys['weekly']}")
        if not await repo.reserve_reward_receipt(
            db, user_id=user_id, reward_id=reward_id, reward_kind=kind,
            quest_policy_version=rules.POLICY_VERSION,
            reward_policy_version=REWARD_POLICY_VERSION,
            amount_mora=REWARD_MORA[kind],
        ):
            return {**await _overview_locked(db, user_id=user_id, keys=keys, vip_active=vip_active, sources=sources),
                    'reward_result': {'kind': kind, 'already_claimed': True}}
        mutation = await economy_ledger.apply_balance_change(
            db, user_id, {'mora': REWARD_MORA[kind]}, reason_code='quest_reward',
            idempotency_key=f'quest-v1:{reward_id}', source_type='quest',
            reference_type='quest_reward', reference_id=reward_id,
            metadata={'policy_version': REWARD_POLICY_VERSION, 'reward_kind': kind,
                      'reward_id': reward_id, 'amount_mora': REWARD_MORA[kind]},
            note=f'Квесты: {kind} награда',
        )
        key_receipt = None
        chests_enabled = await system_flags.is_enabled(db, 'content_chests_v1')
        if REWARD_KEYS[kind] and chests_enabled:
            key_receipt = await grant_quest_completion_key_in_transaction(
                db, user_id=user_id, reward_kind=kind, reward_id=reward_id,
            )
        state = await _overview_locked(db, user_id=user_id, keys=keys, vip_active=vip_active, sources=sources)
    return {**state, 'reward_result': {'kind': kind, 'already_claimed': False,
                                        'amount_mora': REWARD_MORA[kind],
                                        'amount_keys': REWARD_KEYS[kind] if chests_enabled else 0,
                                        'key_grant_id': key_receipt.grant_id if key_receipt else None,
                                        'operation_id': mutation.operation_id}}


async def record_metric(db, *, user_id: int, metric: str, event_id: str, vip_active: bool,
                        sources: frozenset[str] | set[str] | None = None) -> dict:
    """Internal-only hook for an already-validated terminal activity event."""
    if metric not in {definition['metric'] for definition in rules.QUESTS}:
        raise QuestError('unknown quest metric')
    event_id = str(event_id or '').strip()
    if not event_id or len(event_id) > 128:
        raise QuestError('invalid quest event id')
    keys = period_keys()
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        if not await repo.save_metric_receipt(db, user_id=user_id, metric=metric, event_id=event_id):
            return await _overview_locked(db, user_id=user_id, keys=keys, vip_active=vip_active, sources=sources)
        for period in ('daily', 'weekly'):
            await _ensure_period(db, user_id=user_id, period=period, period_key=keys[period], sources=sources)
            await repo.increment_metric(db, user_id=user_id, period=period, period_key=keys[period], metric=metric)
        return await _overview_locked(db, user_id=user_id, keys=keys, vip_active=vip_active, sources=sources)
