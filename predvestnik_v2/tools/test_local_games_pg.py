"""PostgreSQL proof: offline results, lost replies, legacy isolation and rewards."""
import argparse
import asyncio
import copy
from uuid import uuid4
from urllib.parse import urlparse

import asyncpg
from core import rhythm_v2 as r, minesweeper_v2 as m
from infrastructure.pg_adapter import PGAdapter
from services import local_games as local, rhythm_v2 as rhythm, minesweeper_v2 as mine


async def rejected(awaitable, error):
    try:
        await awaitable
    except error:
        return
    raise AssertionError("invalid/foreign/replayed mutation was accepted")


def rhythm_journal(packet):
    state=copy.deepcopy(packet['state']); seed=bytes.fromhex(packet['seed']);actions=[]
    # Two full chunks, two gifts and all their ongoing effects, then defeat.
    while state['health']:
        if r.draft_pending(next_signal_no=state['next_signal_no'],picks=len(state['selected'])):
            choice=r.perk_offers(seed,len(state['selected'])+1,health=state['health'],perks=state['perks'],legacy=packet['legacy'])[0]
            state['health'],state['perks']=r.apply_perk(choice,health=state['health'],perks=state['perks'])
            state['selected'].append(choice);actions.append(dict(kind='pick',perk_id=choice));continue
        signal=state['next_signal_no'];window=r.window_ms(signal,state['perks'])
        good=signal<45; rune=r.expected_rune(seed,signal) if good else None; elapsed=window//3 if good else window+1
        actions.append(dict(kind='tap',signal_no=signal,rune=rune,elapsed_ms=elapsed))
        if good:
            state['correct_streak']+=1
            state['health'],state['perks']=r.after_correct(state['perks'],health=state['health'],streak_after=state['correct_streak'])
        else:
            state['health'],state['perks']=r.after_error(health=state['health'],perks=state['perks'],timed_out=True)
            state['correct_streak']=0
        state['next_signal_no']+=1
    return actions


async def run(dsn):
    assert urlparse(dsn).hostname in {'127.0.0.1','localhost','::1'}
    c=await asyncpg.connect(dsn);db=PGAdapter(c);tx=c.transaction();await tx.start()
    try:
        uid=990083201
        await c.execute('INSERT INTO users(user_tg_id,user_balance_mora) VALUES($1,1000) ON CONFLICT DO NOTHING',uid)
        started=await rhythm.start_run(db,user_id=uid,mode='normal');run_id=started['run_id']
        ticket=await rhythm.issue_transport_ticket(db,user_id=uid,run_id=run_id)
        _,lease,live=await rhythm.connect_transport(db,run_id=run_id,ticket=ticket['ticket'])
        # A very old opened signal must not consume any health on migration.
        await c.execute("UPDATE rhythm_v2_runs SET signal_opened_at=NOW()-INTERVAL '1 hour' WHERE run_id=$1",run_id)
        packet=await local.packet(db,game='rhythm',user_id=uid,run_id=run_id)
        assert packet['state']['health']==5
        assert await local.packet(db,game='rhythm',user_id=uid,run_id=run_id)==packet
        await rejected(local.packet(db,game='rhythm',user_id=uid+1,run_id=run_id),rhythm.RhythmConflict)
        await rejected(rhythm.transport_state(db,user_id=uid,run_id=run_id,lease=lease),rhythm.RhythmConflict)
        await rejected(rhythm.tap(db,user_id=uid,run_id=run_id,signal_no=1,rune='left',action_id='legacy'),rhythm.RhythmConflict)
        current=await rhythm.current_run(db,user_id=uid,run_id=run_id)
        assert current['health']==5 and current['status']=='active'
        actions=rhythm_journal(packet)
        await rejected(local.finalize(db,game='rhythm',user_id=uid,run_id=run_id,actions=actions[:1]),rhythm.RhythmConflict)
        assert (await rhythm.current_run(db,user_id=uid,run_id=run_id))['health']==5
        expected=local.replay_rhythm(packet,actions)
        # Replacement of an open server row cannot destroy a finished local
        # result waiting for connection. The next run keeps its own row.
        replacement=await rhythm.start_run(db,user_id=uid,mode='normal')
        result=await local.finalize(db,game='rhythm',user_id=uid,run_id=run_id,actions=actions)
        assert result['score']==expected['score']>0 and result['integrity_status']=='clear',result
        assert result['gifts'] and result['analysis']['complete']
        assert await local.finalize(db,game='rhythm',user_id=uid,run_id=run_id,actions=actions)==result
        assert await local.packet(db,game='rhythm',user_id=uid,run_id=run_id)==packet
        changed=copy.deepcopy(actions);changed[0]['elapsed_ms']+=1
        await rejected(local.finalize(db,game='rhythm',user_id=uid,run_id=run_id,actions=changed),rhythm.RhythmConflict)
        await rejected(local.finalize(db,game='rhythm',user_id=uid+1,run_id=run_id,actions=actions),rhythm.RhythmConflict)
        assert (await rhythm.current_run(db,user_id=uid,run_id=replacement['run_id']))['status']=='active'
        assert await c.fetchval('SELECT COUNT(*) FROM rhythm_v2_leaderboard WHERE best_run_id=$1',run_id)==1
        assert await c.fetchval("SELECT COUNT(*) FROM rhythm_v2_actions WHERE run_id=$1 AND action_id='local:result:v1'",run_id)==1

        imported_id=str(uuid4())
        uploaded=await local.finalize(db,game='rhythm',user_id=uid,run_id=imported_id,actions=actions,
                    origin={'seed':packet['seed'],'ruleset_version':r.RULESET_VERSION})
        assert uploaded['score']==result['score'] and uploaded['integrity_status']=='clear'
        assert await local.finalize(db,game='rhythm',user_id=uid,run_id=imported_id,actions=actions)==uploaded

        for won in (False,True):
            started=await mine.start_run(db,user_id=uid,difficulty='easy');run_id=started['run_id']
            p=await local.packet(db,game='minesweeper',user_id=uid,run_id=run_id)
            assert await local.packet(db,game='minesweeper',user_id=uid,run_id=run_id)==p
            await rejected(mine.act(db,user_id=uid,run_id=run_id,action_id='legacy',expected_revision=0,kind='open',cell=0),mine.MinesweeperConflict)
            first=0;mines=set(p['layouts']['0']);actions=[dict(kind='open',cell=first,elapsed_ms=0)]
            if won:
                actions += [dict(kind='open',cell=cell,elapsed_ms=1000+cell*100) for cell in range(1,36) if cell not in mines]
                # Flood reveal can end the board before every scheduled safe
                # cell is visited. Trim at its exact terminal action.
                for n in range(1,len(actions)+1):
                    try:local.replay_mine(p,actions[:n]);actions=actions[:n];break
                    except ValueError:pass
            else:actions.append(dict(kind='open',cell=next(iter(mines)),elapsed_ms=2345))
            await mine.start_run(db,user_id=uid,difficulty='normal')
            result=await local.finalize(db,game='minesweeper',user_id=uid,run_id=run_id,actions=actions)
            assert result['status']==('won' if won else 'lost')
            assert result['elapsed_ms']==actions[-1]['elapsed_ms']
            imported=await local.finalize(db,game='minesweeper',user_id=uid,run_id=str(uuid4()),actions=actions,
                origin={'seed':p['seed'],'ruleset_version':m.RULESET_VERSION,'difficulty':'easy'})
            assert imported['status']==result['status'] and imported['elapsed_ms']==result['elapsed_ms']

            assert await local.finalize(db,game='minesweeper',user_id=uid,run_id=run_id,actions=actions)==result
            await rejected(local.finalize(db,game='minesweeper',user_id=uid,run_id=run_id,actions=actions+[actions[-1]]),mine.MinesweeperConflict)
            assert await c.fetchval('SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=$1 AND source_event_id=$2',uid,run_id)==1
        # An ordinary offline first-open flood is valid, unranked, and replayable.
        auto_id=str(uuid4())
        auto_actions=[dict(kind='open',cell=14,elapsed_ms=0)]
        auto_origin={'seed':(536).to_bytes(32,'big').hex(),'ruleset_version':m.LEGACY_RULESET_VERSION,'difficulty':'easy'}
        auto=await local.finalize(db,game='minesweeper',user_id=uid,run_id=auto_id,actions=auto_actions,origin=auto_origin)
        assert auto['status']=='won' and auto['opened_actions']==1 and not auto['speed_ranked']
        assert await local.finalize(db,game='minesweeper',user_id=uid,run_id=auto_id,actions=auto_actions,origin=auto_origin)==auto
        assert await c.fetchval("SELECT COUNT(*) FROM minesweeper_v2_runs WHERE run_id=$1 AND status='won'",auto_id)==1
        assert await c.fetchval('SELECT COUNT(*) FROM minesweeper_v2_leaderboard WHERE best_run_id=$1',auto_id)==0
        print('OK: real PostgreSQL local packets, replay, ownership, Mines loss+win, automatic win unranked and preserved')
    finally:
        await tx.rollback();await c.close()


async def concurrency(dsn):
    # Real separate connections need committed fixtures. These synthetic rows
    # stay only in the dedicated disposable preprod database.
    assert urlparse(dsn).path == '/predvestnik_preprod'
    c=await asyncpg.connect(dsn);db=PGAdapter(c)
    uid=99_008_000_000+uuid4().int%1_000_000
    await c.execute('INSERT INTO users(user_tg_id,user_balance_mora) VALUES($1,1000)',uid)
    started=await rhythm.start_run(db,user_id=uid,mode='normal')
    packet=await local.packet(db,game='rhythm',user_id=uid,run_id=started['run_id'])
    actions=rhythm_journal(packet)
    async def submit(run_id,origin=None):
        connection=await asyncpg.connect(dsn)
        try:return await local.finalize(PGAdapter(connection),game='rhythm',user_id=uid,run_id=run_id,actions=actions,origin=origin)
        finally:await connection.close()
    for run_id,origin in ((started['run_id'],None),(str(uuid4()),{'seed':packet['seed'],'ruleset_version':r.RULESET_VERSION})):
        left,right=await asyncio.gather(submit(run_id,origin),submit(run_id,origin))
        assert left==right and left['integrity_status']=='clear'
        assert await c.fetchval("SELECT COUNT(*) FROM rhythm_v2_actions WHERE run_id=$1 AND action_id='local:result:v1'",run_id)==1
        assert await c.fetchval('SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=$1 AND source_event_id=$2',uid,run_id)==1
    await c.close()
    print('OK: true two-connection concurrent result delivery and offline UUID import each settle exactly once')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn',required=True);dsn=p.parse_args().dsn
    asyncio.run(run(dsn));asyncio.run(concurrency(dsn))
