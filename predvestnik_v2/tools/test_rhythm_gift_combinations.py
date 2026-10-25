"""Exhaustive ordered gift pairs and new-gift triples, with semantic bounds."""
from itertools import product
from core import rhythm_v2 as r


def chain(ids,health=5):
 p=r.new_perks()
 for id in ids:health,p=r.apply_perk(id,health=health,perks=p)
 return health,p


def points(p,health=5,combo=0,elapsed=10):
 return r.score_for_correct(elapsed_ms=elapsed,allowed_window_ms=600,combo_before=combo,perks=p,health=health)


def run():
 ids=[p.id for p in r.PERKS if not p.filler];new=tuple(p.id for p in r.PERKS if p.since>5 and not p.filler)
 cases=0
 for count in (1,2,3):
  for selected in product(ids,repeat=count):
   if count==3 and not any(x in new for x in selected):continue
   for health in (1,2,3,5,7):
    try:hp,p=chain(selected,health)
    except r.RhythmRuleError:continue
    assert 0<hp<=r.MAX_HEALTH
    assert p==r.normalize_perks(p)
    for signal in (21,201,501,1001):
     window=r.window_ms(signal,p);assert window>=r.min_window_ms(signal)>=r.HARD_FLOOR_MS
     for combo in (0,3,14,19,1000):
      scores=[r.score_for_correct(elapsed_ms=e,allowed_window_ms=window,combo_before=combo,perks=p,health=hp) for e in (0,window//2,window)]
      assert scores[0]>=scores[1]>=scores[2]>=1,'slower timing must never earn more'
      assert scores[0]<6000,'score remains additive and bounded even for bloody/sharp/cadence'
    dying=hp;effects=p
    for _ in range(20):dying,effects=r.after_error(health=dying,perks=effects,timed_out=True)
    assert dying==0,'free timeouts, recovery and shields cannot forgive endless misses'
    cases+=1
 # Both orders matter: the sacrifice cannot create a strictly stronger old pair.
 a,pa=chain(('last_spark','glass_cannon'));b,pb=chain(('glass_cannon','last_spark'))
 c,pc=chain(('glass_cannon','gambit'))
 assert (a,b,c)==(2,1,2)
 assert points(pa,a)==points(pb,b)<points(pc,c)
 assert r.window_ms(21,pa)>r.window_ms(21,pc),'lower bonus buys the wider window'
 _,m=chain(('metronome',));assert points(m,combo=0)==85 and points(m,combo=3)==240
 assert points(m,combo=4)==98
 # Even maximally stacked score gifts keep the burst below the fixed bound.
 peak=r.new_perks();peak['owned']={item.id:item.max_stack for item in r.PERKS if item.score_pct>0 or item.combo_step or item.sharp_eye or item.streak_bonus_pct or item.id in ('metronome','last_spark')};peak['bloody']=20
 assert points(peak,health=2,combo=999)==6259  # was 5733 before the series gifts: Hot streak and Trade add 9%, still one bounded burst
 # Recovery lasts three signals, never heals or triggers on shields/free misses.
 hp,p=chain(('second_wind','stone_shield'))
 hp,p=r.after_error(health=hp,perks=p,timed_out=False);assert hp==5 and p['recovery']==0
 hp,p=r.after_error(health=hp,perks=p,timed_out=False);assert hp==4 and p['recovery']==3
 base=r.window_ms(21,{**p,'recovery':0});assert r.window_ms(21,p)>base
 for left in (2,1,0):hp,p=r.after_correct(p,health=hp,streak_after=1);assert p['recovery']==left and hp==4
 hp,p=chain(('second_wind','steady_hand'))
 hp,p=r.after_error(health=hp,perks=p,timed_out=True);assert hp==5 and p['recovery']==0
 hp,p=r.after_error(health=hp,perks=p,timed_out=True);assert hp==4 and p['recovery']==3
 p={**p,'shield':1};hp,p=r.after_error(health=hp,perks=p,timed_out=False);assert p['recovery']==2
 # A surviving hit re-arms once, not once per heart. Picking a sacrifice does not.
 hp,p=chain(('second_wind','gold_vein'))
 hp,p=r.after_error(health=hp,perks=p,timed_out=False);assert hp==3 and p['recovery']==3
 hp,p=chain(('second_wind','last_spark'));assert hp==4 and p['recovery']==0
 # Scoring uses pre-regeneration health; the next tap sees healed health.
 hp,p=chain(('last_spark','vampire'),health=3);assert hp==2
 before=points(p,health=hp);hp,p=r.after_correct(p,health=hp,streak_after=15)
 assert hp==3 and before>points(p,health=hp)
 for draft in range(1,101):
  assert not set(new).intersection(r.perk_offers(b'legacy',draft,health=5,perks=r.new_perks(),ruleset_version='rhythm-v2-rules-5'))
  assert not {p.id for p in r.PERKS if p.since>=8}.intersection(r.perk_offers(b'legacy',draft,health=5,perks=r.new_perks(),ruleset_version='rhythm-v2-rules-7'))
 print(f'PASS: {cases} eligible singles/ordered pairs/new triples across five health states; burst bounds, cadence, recovery, vampire timing, series gifts and legacy pools')

if __name__=='__main__':run()
