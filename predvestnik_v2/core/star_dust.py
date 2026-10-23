"""Earned, personal star dust. No transfer, paid multipliers or cash conversion."""
from math import floor,isfinite

POLICY_VERSION='star-dust-trail-2026-10-23'
VIP_DAY_COST=100
CHAT_MAX_DUST=24
LUCK_STEPS=1_000_000
UNITS_PER_DUST=18_000_000_000
PET_RATES={'trek':10,'expedition':10,'watch':1}
PET_HOURS={'trek':(3,6,9),'expedition':(3,6,9),'watch':(12,24)}


class DustError(ValueError): pass


def chat_reward(luck: float) -> int:
    if isinstance(luck,bool) or not isinstance(luck,(float,int)) or not isfinite(luck) or not 0<=luck<=1:
        raise DustError('Некорректный результат поиска.')
    return floor(CHAT_MAX_DUST*luck*luck+.5)


def luck_view(luck: float, amount: int) -> dict:
    chat_reward(luck)
    if not amount:return {'title':'Звёзды скрылись','stars':0,'text':'Сегодня небо тихое. Следующая попытка — завтра.'}
    index=0 if luck<.4 else 1 if luck<.65 else 2 if luck<.85 else 3 if luck<.95 else 4
    return {'title':('Тихое мерцание','Удачная ночь','Звёздная россыпь','Звёздный дождь','Редкое сияние')[index],
            'stars':index+1,'text':('Несколько искр удалось поймать.','Звёзды оставили приятную находку.',
                                 'Небо щедро поделилось пылью.','Много ярких искр за одну попытку!','Одна из самых щедрых находок!')[index]}


def pet_rate(kind):
    if kind not in PET_RATES:raise DustError('Неизвестное путешествие.')
    return PET_RATES[kind]


def pet_reward(kind: str,hours: int) -> int:
    if isinstance(hours,bool) or not isinstance(hours,int) or hours not in PET_HOURS.get(kind,()):
        raise DustError('Неизвестное путешествие.')
    return hours*3_600_000_000*pet_rate(kind)//UNITS_PER_DUST


def new_coverage_units(start_us:int,end_us:int,rate:int,covered) -> int:
    """New intensity above the collected trail. Coordinates: exact microseconds.

    Overlap uses max intensity, never number of pets. Fractional units persist.
    """
    if end_us<start_us or rate not in PET_RATES.values():raise DustError('Некорректный звёздный след.')
    intervals=[(max(start_us,a),min(end_us,b),r) for a,b,r in covered if a<end_us and b>start_us]
    points=sorted({start_us,end_us,*(p for a,b,_ in intervals for p in (a,b))})
    return sum((b-a)*max(0,rate-max((r for x,y,r in intervals if x<=a and y>=b),default=0))
               for a,b in zip(points,points[1:]))
