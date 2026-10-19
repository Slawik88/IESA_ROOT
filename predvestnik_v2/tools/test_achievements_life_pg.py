"""Rollback-only proof: finite life achievements, verified history and replay."""
import argparse,asyncio,json,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

async def run(dsn):
 import asyncpg
 from core import achievements_v1 as rules
 from core.skins_v3_catalog import SKINS
 from core.skins_v3 import TIERS
 from infrastructure.pg_adapter import PGAdapter
 from infrastructure.repositories import achievements_v1 as repo,skins_v3,economy_ledger,pets_v2,quests_v1
 from services import achievements_v1 as service
 c=await asyncpg.connect(dsn);db=PGAdapter(c)
 for r in (repo,skins_v3,economy_ledger,pets_v2,quests_v1):await r.ensure_tables(db)
 tx=c.transaction();await tx.start()
 try:
  uid=976419
  await c.execute('INSERT INTO users(user_tg_id,user_balance_mora) VALUES($1,1000)',uid)
  await skins_v3.essence_apply(db,uid,1000,reason='test',reference='fixture',idempotency_key='life-fixture-funds')
  refs=[('pet_v2_camp',f'{b}:{l}') for b in ('lounge','markers','workshop') for l in range(1,6)]
  refs += [('skin_upgrade',f'{skin}:{tier}') for skin in list(SKINS)[:16] for tier in TIERS[1:]]
  refs += [('skin_upgrade','forest:C'),('pet_v2_camp','unknown:9'),('skin_upgrade','forest:D')]
  for i,(reason,ref) in enumerate(refs):
   await skins_v3.essence_apply(db,uid,-1,reason=reason,reference=ref,idempotency_key=f'past-{i}')
  now=datetime.now(timezone.utc)
  for i,day in enumerate((1,1,2,3)):
   request={'type':'feed','pet_id':i+1,'food_id':'food_basic'};response={'ok':True,'pet_id':i+1}
   await c.execute('INSERT INTO pet_v2_actions(user_id,action_id,request_json,response_json,created_at) VALUES($1,$2,$3,$4,$5)',uid,f'past-feed-{i}',json.dumps(request),json.dumps(response),now-timedelta(days=day))
  for i in range(1,4):
   day=(now-timedelta(days=i)).date().isoformat()
   await quests_v1.reserve_reward_receipt(db,user_id=uid,reward_id=f'daily:{day}',reward_kind='daily',quest_policy_version='verified-past',reward_policy_version='verified-past',amount_mora=5)
  await quests_v1.reserve_reward_receipt(db,user_id=uid,reward_id='weekly:2026-10-12',reward_kind='weekly',quest_policy_version='past',reward_policy_version='past',amount_mora=5)
  got=await service.reconcile_history(db,user_id=uid)
  assert got['facts']==15+96+3+3,got
  view=await service.overview(db,user_id=uid);families={f['id']:f for f in view['families']}
  assert families['builder']['level']==5 and families['builder']['completed_events']==15
  assert families['stylist']['level']==7 and families['stylist']['completed_events']==96
  assert families['care']['level']==2 and families['care']['completed_events']==3
  assert families['quester']['level']==2 and families['quester']['completed_events']==3
  assert all(families[x]['next'] is None or families[x]['next']['weeks_required']==0 for x in ('care','builder','stylist','quester'))
  before=await c.fetchval('SELECT user_balance_mora FROM users WHERE user_tg_id=$1',uid)
  assert before==1000+25+35+10+10,before
  assert (await service.reconcile_history(db,user_id=uid))['facts']==0
  assert await c.fetchval('SELECT user_balance_mora FROM users WHERE user_tg_id=$1',uid)==before
  day=(now-timedelta(days=1)).date().isoformat()
  assert (await service.record_life_event(db,user_id=uid,family='care',fact=day))['idempotent_replay']
  # A late old-worker receipt must still be picked up after the first import.
  await quests_v1.reserve_reward_receipt(db,user_id=uid,reward_id='daily:'+now.date().isoformat(),reward_kind='daily',quest_policy_version='past',reward_policy_version='past',amount_mora=5)
  assert (await service.reconcile_history(db,user_id=uid))['facts']==1
  # A source transaction rollback removes both its achievement and payout.
  other=uid+1;await c.execute('INSERT INTO users(user_tg_id,user_balance_mora) VALUES($1,1000)',other)
  try:
   async with c.transaction():
    await service.record_life_event(db,user_id=other,family='care',fact=now.date().isoformat())
    raise RuntimeError('source rolled back')
  except RuntimeError:pass
  assert await c.fetchval('SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=$1',other)==0
  assert await c.fetchval('SELECT user_balance_mora FROM users WHERE user_tg_id=$1',other)==1000
  print('PASS: all 15 past camp upgrades and 96 skin tiers; care day dedupe; daily-only quests; repeat/late history; atomic rollback; finite reward budget')
 finally:
  await tx.rollback();await c.close()

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--dsn',required=True);args=ap.parse_args()
 if urlparse(args.dsn).hostname not in ('127.0.0.1','localhost','::1'):raise SystemExit('Loopback test DB required')
 asyncio.run(run(args.dsn))
