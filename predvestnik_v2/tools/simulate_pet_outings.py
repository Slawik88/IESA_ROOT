"""Deterministic actual-rules balance scenarios, not a forecast of player behaviour."""
import json,random,sys
from pathlib import Path
from itertools import product
from statistics import mean
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import pet_equipment as r, pets_v2 as p


def run():
    builds=[tuple(zip(keys,[tier]*5)) for keys in product(*[[k for k,v in r.ITEMS.items() if v[0]==slot] for slot in r.SLOTS]) for tier in (1,2,3)]
    maximum=max(r.effects(b)['xp'] for b in builds)
    assert abs(maximum-1.2208)<1e-8
    for b in builds:
        fx=p.build_effects(None,(),equipment=b)
        for before in (0,499,500,900,1000,1500):
            grant=p.pool_credit(before,600*fx['xp_mult'])
            assert 0<=grant<=p.DAILY_MAX
            assert p.pool_credit(2000,600*fx['xp_mult'])==0
    results={};rng=random.Random(20261022)
    for gear_name,equipment in [('none',()),('starter',tuple((k,1) for k in r.STARTERS)),('max',tuple((k,3) for k in r.STARTERS))]:
        for policy in ('middle','bold','conserve','bank'):
            records=[];statuses={}
            for _ in range(5000):
                s=r.new_outing(rng.sample(range(len(r.EVENTS)),r.STEPS),equipment)
                while s['status']=='active':
                    options=[o for o in r.choices(s) if o['enabled']]
                    if policy=='bank' and s['hp']<=1 and s['cargo']>=4:choice='leave'
                    elif policy=='bold':choice=2
                    elif policy=='middle':choice=1
                    elif policy=='conserve':
                        healing=[o for o in options if o['heal'] and s['hp']<=2]
                        refill=[o for o in options if o['supplies'] and s['supplies']<=1]
                        choice=(healing or refill or sorted(options,key=lambda o:(o['chance'],o['gain']),reverse=True))[0]['id']
                    else:choice=1
                    before=s
                    s=r.advance(s,choice,rng.random()*100)
                    assert before is not s and 0<=s['hp']<=4 and 0<=s['supplies']<=5 and 0<=s['cargo']<=32 and s['step']<=7
                assert 0<=s['reward']<=32
                records.append(s['reward']);statuses[s['status']]=statuses.get(s['status'],0)+1
            results[gear_name+'/'+policy]={'mean_parts':round(mean(records),2),'min':min(records),'max':max(records),'status':statuses}
    # Independent lifecycle witnesses: retreat banks all; rescue banks half;
    # completed route has a fixed bonus, supplies/cargo are spent even on failure.
    s=r.new_outing([0]*7,());s['cargo']=9
    assert r.advance(s,'leave',0)['reward']==9
    s['hp']=1
    assert r.advance(s,2,99)['reward']==4
    s['supplies']=0
    try:r.advance(s,0,0)
    except ValueError:pass
    else:raise AssertionError('cannot spend absent supply')
    result={'builds':len(builds),'simulated_runs':len(results)*5000,'max_xp_multiplier':maximum,
            'daily_xp_cap':p.DAILY_MAX,'max_parts_per_run':32,'max_parts_per_day':96,'scenarios':results}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
