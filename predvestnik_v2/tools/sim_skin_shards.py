"""Skin shards proposal numbers (docs/SKIN_SHARDS_PROPOSAL.md): shards per key tier, weeks to a skin, top-up prices."""
import sys; sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parents[1].as_posix())
from core.chests_v1 import STAR_WEIGHTS, KEY_OFFERS
from core.skins_v3 import BUY_PRICE_ZARNIKI as P
NEED={r:3*p for r,p in P.items()}
DROP={3:15,4:25,5:40,6:60,7:90,8:130,9:180,10:260}
tot=sum(STAR_WEIGHTS.values())
def ev(tier):
    e=0
    for s,w in STAR_WEIGHTS.items():
        st=max(s,tier); e+=w/tot*DROP.get(st,0)
    return e
print("need",NEED)
for t,price in ((1,10),(3,800/10/10),(4,120),(6,300)):
    e=ev(t); print(f"tier{t}: EV shards {e:.1f}; list value {e/3:.1f}✨ vs key price {price}✨")
FREE_KEYS_WEEK=17+7  # quests + pets (approx)
for paid in (0,14):
    week=FREE_KEYS_WEEK*ev(1)+paid*ev(1)
    tgt=week*0.6
    print(f"keys/wk free+paid {FREE_KEYS_WEEK}+{paid}: {week:.0f} shards/wk, target {tgt:.0f}/wk; weeks to own:",
          {r:round(NEED[r]/tgt,1) for r in NEED})
for r in ('A','S','SSS'):
    for frac in (.3,.5,.8):
        left=NEED[r]*(1-frac); price=round(left/NEED[r]*P[r]*0.9)
        print(r,f"{int(frac*100)}% collected → finish for {price}✨ (full {P[r]}✨)")
