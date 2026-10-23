"""Release only tested generations after startup schema completion."""
from loguru import logger
from core import player_release as policy
from infrastructure.repositories import player_release as repo,chests_v1

async def activate(db):
    if not await repo.required_storage(db) or not await chests_v1._schema_ready(db):
        raise RuntimeError('Approved player release storage is incomplete')
    await repo.ensure_tables(db)
    changed=await repo.apply_once(db,policy.RELEASE_ID,policy.FLAGS)
    if changed:logger.info('Player revision released: {}',policy.RELEASE_ID)
    if await db.connection.fetchval("SELECT to_regclass('mafia_online_rooms') IS NOT NULL"):
        await repo.apply_once(db, 'owner-mafia-online-2026-10-23', ('game_mafia_online',))
    # The already funded spot market can be opened without issuing any money.
    # A missing market/secret is not permission to bootstrap or mint capital.
    if await repo.applied(db,policy.RELEASE_ID+':spot'):return
    from services import coin_market_v2 as market
    from infrastructure.repositories import coin_market_v2 as market_repo
    try:
        await market.require(db,new=False)
        funding=await db.connection.fetchrow("SELECT mora,metadata FROM coin_market_v2_funding WHERE id='initial-v2'")
        rows=await market_repo.rows(db,0)
        metadata={} if not funding else market_repo.decode(funding['metadata'])
        if not funding or int(funding['mora'])!=120000*market.rules.MORA or metadata.get('authorization')!='project_owner:2026-10-17:explicit_120000_mora_one_time_issuance' or metadata.get('kind')!='one_time_system_issuance' or not {c[0] for c in market.SYSTEM_COINS}.issubset({x['id'] for x in rows}):
            return
        for item in sorted(rows,key=lambda x:x['id']):
            async with db.connection.transaction():
                row=await market_repo.load(db,item['id'],lock=True)
                _,book,_,_=market.checked(row)
                await market_repo.reconcile(db,row,book)
        await repo.apply_once(db,policy.RELEASE_ID+':spot',('coin_market_v2',))
    except market.Unavailable:
        logger.warning('Player spot release waits for configured, funded market')
