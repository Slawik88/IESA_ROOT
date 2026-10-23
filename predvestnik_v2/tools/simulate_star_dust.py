#!/usr/bin/env python3
"""Source-only dust audit: actual trip durations, energy, slots and coverage.

No wallet, purchase, daily pet or future VIP caps. Profiles are scenarios, not
telemetry. Three level-1 moss cats; no VIP, gear, food or paid bonuses. Energy
regenerates during travel, matching services.pets_v2._rest. Only completed trips
pay; overlaps and fractional carry use production code.
"""
from __future__ import annotations
import argparse
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import statistics
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import pets_v2 as pets, star_dust as rules
HOUR_US = 3_600_000_000

@dataclass(frozen=True)
class Profile:
    name: str
    mode: str
    active_probability: float
    description: str
    exact_active_days: int | None = None

PROFILES = (
    Profile('casual','casual',.4,'12 active days/month; one 6h trek from 08:00; chat on active days'),
    Profile('medium','medium',.7,'21 active days/month; 9h trek from 08:00, then 3h trek on half those days; chat on active days'),
    *(Profile(f'active_{count}_days' if count<30 else 'active','active',1,
              f'{count} active days/month; sequential 9h+6h+(3h or 6h equally), 18/21h coverage; chat on active days',count)
      for count in (27,28,29,30)),
    Profile('watch_24h','watch24',1,'All three pets in parallel 24h watch; one collection/start daily; chat daily'),
    Profile('watch_12h','watch12',1,'All three pets in parallel 12h watch twice daily; chat daily'),
    Profile('chat_only','chat',1,'No pet trips; one chat claim daily'),
    Profile('stress_24h','stress',1,'One 3h expedition every 3h, rotating three pets, seamless 24h coverage; chat daily'),
    Profile('stress_parallel','parallel',1,'All three pets in parallel on sequential 9h+9h+6h expeditions, 72 slot-hours/day; chat daily'),
    Profile('stress_staggered','staggered',1,'Three 9h expeditions/day starting 00:00/08:00/16:00, seamless coverage; chat daily'),
)

def quantiles(values):
    ordered=sorted(values)
    def at(q):return ordered[min(len(ordered)-1,math.floor(q*(len(ordered)-1)))]
    return {'mean':round(statistics.fmean(values),3),'p10':at(.1),'median':statistics.median(values),
            'p90':at(.9),'min':ordered[0],'max':ordered[-1]}

def departures(mode,rng):
    if mode=='casual':return [(8,'trek',6)]
    if mode=='medium':return [(8,'trek',9)]+([(17,'trek',3)] if rng.random()<.5 else [])
    if mode=='active':return [(0,'trek',9),(9,'trek',6),(15,'trek',3 if rng.random()<.5 else 6)]
    if mode=='watch24':return [(0,'watch',24)]*3
    if mode=='watch12':return [(start,'watch',12) for start in (0,12) for _ in range(3)]
    if mode=='stress':return [(start,'expedition',3) for start in range(0,24,3)]
    if mode=='parallel':return [(start,'expedition',hours) for start,hours in ((0,9),(9,9),(18,6)) for _ in range(3)]
    if mode=='staggered':return [(start,'expedition',9) for start in (0,8,16)]
    if mode=='chat':return []
    raise ValueError(mode)

def simulate_profile(profile,*,users,days,seed):
    rng=random.Random(seed)
    outcomes={key:[] for key in ('dust_earned','dust_chat','dust_pets','vip_days_affordable',
              'dust_reserve_after_exchange','completed_trips','slot_hours','coverage_hours',
              'energy_rejected_departures','slot_rejected_departures')}
    energy_cap=pets.energy_max(1,'moss_cat')
    for _ in range(users):
        # Each pet: energy, last update hour, busy-until hour.
        animals=[[float(energy_cap),0.,0.] for _ in range(3)]
        active_days=(set(rng.sample(range(days),round(days*profile.exact_active_days/30)))
                     if profile.exact_active_days is not None else None)
        intervals=[];chat=energy_rejected=slot_rejected=0
        for day in range(days):
            active=day in active_days if active_days is not None else rng.random()<profile.active_probability
            if not active:continue
            chat+=rules.chat_reward(rng.randrange(rules.LUCK_STEPS+1)/rules.LUCK_STEPS)
            for hour,kind,duration in departures(profile.mode,rng):
                start=day*24+hour
                energy_kind='watch' if kind=='watch' else 'run'
                cost=pets.ACTIVITY_ENERGY[(energy_kind,duration)]
                candidates=[]
                for index,(energy,updated,busy) in enumerate(animals):
                    if busy>start:continue
                    projected=pets.energy_after_rest(energy,hours=start-updated,level=1,species_id='moss_cat')
                    if projected>=cost:candidates.append((projected,-updated,index))
                if sum(a[2]>start for a in animals)>=pets.SLOTS:
                    slot_rejected+=1;continue
                if not candidates:
                    energy_rejected+=1;continue
                projected,_,index=max(candidates)
                animals[index]=[pets.spend_energy(projected,energy_kind,duration),float(start),float(start+duration)]
                if start+duration<=days*24:
                    intervals.append((int(start*HOUR_US),int((start+duration)*HOUR_US),rules.pet_rate(kind)))
        # Return order differs from departure order for overlapping long/short trips.
        intervals.sort(key=lambda row:(row[1],row[0],row[2]))
        recent=deque();dust=remainder=units=0
        slot_hours=sum((b-a)/HOUR_US for a,b,_ in intervals)
        for start,end,rate in intervals:
            # Future claims can begin at most 24h before their completion.
            while recent and recent[0][1]<=end-24*HOUR_US:recent.popleft()
            overlapping=[row for row in recent if row[0]<end and row[1]>start]
            gained=rules.new_coverage_units(start,end,rate,overlapping)
            assert gained>=0
            credited,remainder=divmod(remainder+gained,rules.UNITS_PER_DUST)
            dust+=credited;units+=gained
            recent.append((start,end,rate))
        assert dust==units//rules.UNITS_PER_DUST
        covered=right=0
        for start,end,_ in sorted(intervals):
            covered+=max(0,end-max(start,right));right=max(right,end)
        coverage_hours=covered/HOUR_US
        assert coverage_hours<=days*24
        assert dust<=math.floor(days*24*2)
        total=dust+chat
        values=(total,chat,dust,total//rules.VIP_DAY_COST,total%rules.VIP_DAY_COST,
                len(intervals),slot_hours,coverage_hours,energy_rejected,slot_rejected)
        for key,value in zip(outcomes,values):outcomes[key].append(value)
    return {'profile':profile.name,'assumptions':profile.description,'users':users,'days':days,
            **{key:quantiles(values) for key,values in outcomes.items()},
            'vip_day_equivalent':quantiles([amount/rules.VIP_DAY_COST for amount in outcomes['dust_earned']])}

def audit_rules():
    assert rules.chat_reward(0)==0 and rules.chat_reward(1)==rules.CHAT_MAX_DUST
    for old in ('VIP_WINDOW_CAP','VIP_FUTURE_CAP','BALANCE_CAP','PET_DAILY_CAP'):
        assert not hasattr(rules,old),f'Old artificial cap remains: {old}'
    one_hour=rules.new_coverage_units(0,HOUR_US,rules.pet_rate('trek'),[])
    assert one_hour==rules.UNITS_PER_DUST*2
    assert rules.new_coverage_units(0,HOUR_US,10,[(0,HOUR_US,10)])==0
    assert rules.new_coverage_units(0,HOUR_US,1,[(0,HOUR_US,10)])==0
    assert rules.new_coverage_units(0,HOUR_US,10,[(0,HOUR_US,1)])==one_hour-one_hour//10
    thresholds=[]
    for k in range(1,rules.CHAT_MAX_DUST+1):
        numerator=(2*k-1)*rules.LUCK_STEPS**2;denominator=2*rules.CHAT_MAX_DUST
        threshold=math.isqrt(numerator//denominator)
        while threshold*threshold*denominator<numerator:threshold+=1
        thresholds.append(threshold)
    expected=sum((rules.LUCK_STEPS-t+1)/(rules.LUCK_STEPS+1) for t in thresholds)
    maximum_daily=48+rules.CHAT_MAX_DUST
    assert maximum_daily<rules.VIP_DAY_COST,'Physical source bound can fund permanent VIP'
    return {'command_mean_dust_exact':expected,'max_pet_dust_per_24h':48,
            'max_chat_dust_per_utc_day':rules.CHAT_MAX_DUST,'max_total_dust_per_day_long_run':maximum_daily,
            'vip_day_cost':rules.VIP_DAY_COST,'perfect_luck_30d_vip_capacity':30*maximum_daily/rules.VIP_DAY_COST,
            'stress_24h_30d_expected_vip_capacity':30*(48+expected)/rules.VIP_DAY_COST,
            'limitations':['Activity profiles are explicit assumptions, not real telemetry.',
                'Three level-1 pets, no paid bonuses; energy regenerates during trips as in production.',
                'Expedition stress assumes careful decisions with no extra energy loss; ordinary finds do not affect dust.',
                'No purchase or inventory limits. Long-term saving may buy weeks at once: only source rate is balanced.',
                'Only completed trips count; unfinished last-day trips carry rewards into the next month.',
                'VIP-day counts are affordable whole days, not observed redemption or retention.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--users',type=int,default=10000)
    parser.add_argument('--days',type=int,default=30)
    parser.add_argument('--seed',type=int,default=20261023)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.users<1 or args.days<1:parser.error('Positive --users and --days required')
    report={'seed':args.seed,'policy_version':rules.POLICY_VERSION,'rules_audit':audit_rules(),
            'profiles':[simulate_profile(p,users=args.users,days=args.days,seed=args.seed+i) for i,p in enumerate(PROFILES)]}
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text+'\n',encoding='utf-8')
    print(text)

if __name__=='__main__':main()
