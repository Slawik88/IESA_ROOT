"""Clear, varied quest definitions backed by terminal server events."""
from __future__ import annotations
from typing import Final
from datetime import datetime, timedelta, timezone
from core import pets_v2 as pet_rules

POLICY_VERSION: Final = "quests-v1-2026-09-13-2"
DAILY_COUNT: Final = 4
WEEKLY_COUNT: Final = 5
STANDARD_WEEKLY_REROLLS: Final = 2
VIP_WEEKLY_REROLLS: Final = 5

# ``lane`` prevents one random set from filling several slots with the same
# kind of work. ``source`` is checked against live availability before an
# assignment or reroll is made. Every metric has a terminal server writer.
QUESTS: Final = (
 {"id":"any_game_4","period":"daily","difficulty":1,"metric":"game_completed","lane":"flex","source":"any_game","target":4,"title":"Заверши 4 любые игры","help":"Играй в Ритм или Сапёр — можно сочетать их как удобно."},
 {"id":"rhythm_runs_3","period":"daily","difficulty":1,"metric":"rhythm_completed","lane":"rhythm_play","source":"rhythm","target":3,"title":"Заверши 3 забега в Ритме","help":"Засчитываются только завершённые сервером забеги без нарушений целостности."},
 {"id":"rhythm_normal_2","period":"daily","difficulty":1,"metric":"rhythm_normal_completed","lane":"rhythm_normal","source":"rhythm","target":2,"title":"Пройди 2 обычных забега","help":"В Ритме выбери обычный режим и заверши два забега."},
 {"id":"rhythm_augments_1","period":"daily","difficulty":2,"metric":"rhythm_augments_completed","lane":"rhythm_augments","source":"rhythm","target":1,"title":"Заверши забег с рун-даром","help":"В Ритме дойди до конца первого чанка, возьми рун-дар и заверши забег."},
 {"id":"rhythm_score_500_1","period":"daily","difficulty":2,"metric":"rhythm_score_500","lane":"rhythm_score","source":"rhythm","target":1,"title":"Набери 500 очков за забег","help":"Заверши подтверждённый забег Ритма со счётом не ниже 500."},
 {"id":"minesweeper_plays_2","period":"daily","difficulty":1,"metric":"minesweeper_completed","lane":"mines_play","source":"minesweeper","target":2,"title":"Заверши 2 партии в Сапёре","help":"Победа или поражение засчитываются после завершения партии."},
 {"id":"minesweeper_win_1","period":"daily","difficulty":2,"metric":"minesweeper_win","lane":"mines_win","source":"minesweeper","target":1,"title":"Одержи победу в Сапёре","help":"Заверши любую сложность победой."},
 {"id":"minesweeper_easy_win_1","period":"daily","difficulty":1,"metric":"minesweeper_easy_win","lane":"mines_easy","source":"minesweeper","target":1,"title":"Победи в лёгком Сапёре","help":"Выбери лёгкую сложность и выиграй одну партию."},
 {"id":"minesweeper_normal_win_1","period":"daily","difficulty":2,"metric":"minesweeper_normal_win","lane":"mines_normal","source":"minesweeper","target":1,"title":"Победи в обычном Сапёре","help":"Выбери обычную сложность и выиграй одну партию."},
 {"id":"chest_open_1","period":"daily","difficulty":1,"metric":"chest_revealed","lane":"chest_open","source":"chests","target":1,"title":"Раскрой один сундук","help":"Подойдёт любой ключ."},
 {"id":"pet_feed_1","period":"daily","difficulty":1,"metric":"pet_fed","lane":"pet_care","source":"pet_care","target":1,"title":"Позаботься о питомце","help":"Задание появляется только когда есть еда и питомцу можно восстановить выносливость."},
 {"id":"pet_activity_1","period":"daily","difficulty":1,"metric":"pet_activity_completed","lane":"pet_journey","source":"pets_v2_daily","target":1,"title":"Верни питомца из приключения","help":"Получи награду за поход, экспедицию или дозор до сброса дня. Начать занятие недостаточно."},
 {"id":"pet_trek_1","period":"daily","difficulty":1,"metric":"pet_trek_completed","lane":"pet_journey","source":"pets_v2_trek_daily","target":1,"title":"Пройди тропу с питомцем","help":"Отправь питомца в поход и получи награду до сброса дня. Маршрут и длительность — на твой выбор."},
 {"id":"pet_expedition_1","period":"daily","difficulty":2,"metric":"pet_expedition_completed","lane":"pet_journey","source":"pets_v2_expedition_daily","target":1,"title":"Заверши экспедицию питомца","help":"Верни питомца из экспедиции и получи награду до сброса дня. Подойдёт любой исход выбранного пути."},
 {"id":"pet_watch_1","period":"daily","difficulty":1,"metric":"pet_watch_completed","lane":"pet_journey","source":"pets_v2_watch_daily","target":1,"title":"Сними питомца с дозора","help":"Получи награду за завершённый дозор до сброса дня. Новый дозор длится не меньше 12 часов — учитывай время возвращения."},
 {"id":"any_game_18","period":"weekly","difficulty":1,"metric":"game_completed","lane":"flex","source":"any_game","target":18,"title":"Заверши 18 любых игр","help":"Ритм, Сапёр и доступная тебе Мафия складываются в общий прогресс."},
 {"id":"rhythm_runs_10","period":"weekly","difficulty":1,"metric":"rhythm_completed","lane":"rhythm_play","source":"rhythm","target":10,"title":"Заверши 10 забегов в Ритме","help":"Режим можно менять от забега к забегу."},
 {"id":"rhythm_normal_6","period":"weekly","difficulty":1,"metric":"rhythm_normal_completed","lane":"rhythm_normal","source":"rhythm","target":6,"title":"Пройди 6 обычных забегов","help":"Заверши шесть забегов в обычном режиме Ритма."},
 {"id":"rhythm_augments_4","period":"weekly","difficulty":2,"metric":"rhythm_augments_completed","lane":"rhythm_augments","source":"rhythm","target":4,"title":"Пройди 4 забега с рун-дарами","help":"Заверши четыре забега, в которых ты взял хотя бы один рун-дар."},
 {"id":"rhythm_score_500_3","period":"weekly","difficulty":2,"metric":"rhythm_score_500","lane":"rhythm_score","source":"rhythm","target":3,"title":"Трижды набери 500 очков","help":"Заверши три подтверждённых забега Ритма со счётом не ниже 500."},
 {"id":"minesweeper_plays_8","period":"weekly","difficulty":1,"metric":"minesweeper_completed","lane":"mines_play","source":"minesweeper","target":8,"title":"Заверши 8 партий в Сапёре","help":"Любая сложность и любой итог партии идут в прогресс."},
 {"id":"minesweeper_wins_4","period":"weekly","difficulty":2,"metric":"minesweeper_win","lane":"mines_win","source":"minesweeper","target":4,"title":"Одержи 4 победы в Сапёре","help":"Сложность можно выбирать самостоятельно."},
 {"id":"minesweeper_easy_wins_3","period":"weekly","difficulty":1,"metric":"minesweeper_easy_win","lane":"mines_easy","source":"minesweeper","target":3,"title":"Победи 3 раза на лёгком поле","help":"Выиграй три партии на лёгкой сложности Сапёра."},
 {"id":"minesweeper_normal_wins_2","period":"weekly","difficulty":2,"metric":"minesweeper_normal_win","lane":"mines_normal","source":"minesweeper","target":2,"title":"Победи 2 раза на обычном поле","help":"Выиграй две партии на обычной сложности Сапёра."},
 {"id":"minesweeper_hard_win_1","period":"weekly","difficulty":3,"metric":"minesweeper_hard_win","lane":"mines_hard","source":"minesweeper","target":1,"title":"Победи на сложном поле","help":"Выиграй одну партию на сложном поле Сапёра."},
 {"id":"mafia_matches_3","period":"weekly","difficulty":3,"metric":"mafia_completed","lane":"mafia_play","source":"mafia","target":3,"title":"Заверши 3 матча Мафии","help":"Задание выдаётся только игрокам, которые уже участвовали в Мафии."},
 {"id":"mafia_win_1","period":"weekly","difficulty":3,"metric":"mafia_win","lane":"mafia_result","source":"mafia","target":1,"title":"Победи в матче Мафии","help":"Победа засчитается всем участникам победившей стороны."},
 {"id":"chest_open_5","period":"weekly","difficulty":1,"metric":"chest_revealed","lane":"chest_open","source":"chests","target":5,"title":"Раскрой 5 сундуков","help":"Ключи дают квесты, походы и экспедиции; часть ключей можно купить."},
 {"id":"pet_activity_2","period":"weekly","difficulty":2,"metric":"pet_activity_completed","lane":"pet_journey","source":"pets","target":2,"title":"Заверши 2 приключения питомца","help":"Получи награды за два занятия питомцев: походы, экспедиции или дозоры любой доступной длительности."},
 {"id":"pet_treks_3","period":"weekly","difficulty":2,"metric":"pet_trek_completed","lane":"pet_journey","source":"pets_v2","target":3,"title":"Пройди 3 тропы с питомцами","help":"Получи награды за три похода. Можно менять питомцев, длительность и маршруты."},
 {"id":"pet_expeditions_2","period":"weekly","difficulty":2,"metric":"pet_expedition_completed","lane":"pet_journey","source":"pets_v2","target":2,"title":"Исследуй мир в 2 экспедициях","help":"Получи награды за две экспедиции. Победа на пути не требуется: любой завершённый исход засчитывается."},
 {"id":"pet_watches_3","period":"weekly","difficulty":2,"metric":"pet_watch_completed","lane":"pet_journey","source":"pets_v2","target":3,"title":"Заверши 3 дозора питомцев","help":"Получи награды за три дозора в течение недели. Одно занятие со спутником считается один раз."},
 {"id":"pet_feed_3","period":"weekly","difficulty":1,"metric":"pet_fed","lane":"pet_care","source":"pet_care","target":3,"title":"Покорми питомцев 3 раза","help":"Задание появляется только когда в инвентаре уже есть еда для питомцев."},
)


def pet_daily_sources(pets: list[dict], runs: list[dict], *, now: datetime) -> frozenset[str]:
    """Conservative eligibility; reserve five minutes for collecting the reward.

    Stored energy is a lower bound: do not predict rest, a purchase or a free slot.
    Already running jobs may qualify even when there is no pet free to start one.
    """
    if now.tzinfo is None:
        raise ValueError('quest availability needs an aware server timestamp')
    now = now.astimezone(timezone.utc)
    finish_by = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1, minutes=-5)
    owned = {int(p['id']): p for p in pets if p.get('species_id') in pet_rules.SPECIES}
    busy, possible = set(), set()
    for run in runs:
        busy.add(int(run['pet_id']))
        if run.get('companion_id') is not None:
            busy.add(int(run['companion_id']))
        end = run['ends_at']
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        if int(run['pet_id']) in owned and end.tzinfo is not None and end <= finish_by:
            possible.add(run['kind'])
    if len(runs) < pet_rules.SLOTS:
        for pet in owned.values():
            if int(pet['id']) in busy:
                continue
            energy = float(pet['energy']) if pet.get('energy') is not None else pet_rules.energy_max(1, pet['species_id'])
            for kind in ('trek', 'expedition', 'watch'):
                hours = min(pet_rules.WATCH_HOURS if kind == 'watch' else pet_rules.RUN_HOURS)
                energy_kind = 'watch' if kind == 'watch' else 'run'
                if now + timedelta(hours=hours) <= finish_by and energy >= pet_rules.ACTIVITY_ENERGY[(energy_kind, hours)]:
                    possible.add(kind)
    sources = {f'pets_v2_{kind}_daily' for kind in possible if kind in {'trek','expedition','watch'}}
    if sources:
        sources.add('pets_v2_daily')
    return frozenset(sources)

def validate() -> None:
    ids=[q['id'] for q in QUESTS]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate quest id')
    if any(not q['title'] or not q['help'] or q['target']<=0 or q['difficulty'] not in range(1,6) or not q.get('metric') or not q.get('lane') or not q.get('source') for q in QUESTS): raise ValueError('invalid quest')
    for period,count in (("daily",DAILY_COUNT),("weekly",WEEKLY_COUNT)):
        lanes={q['lane'] for q in QUESTS if q['period']==period and q['source']!='mafia'}
        if len(lanes)<=count: raise ValueError(f'{period} reroll needs distinct available lanes')


def definitions(period: str, sources: set[str] | frozenset[str] | None = None) -> tuple[dict, ...]:
    if period not in {'daily', 'weekly'}:
        raise ValueError('unknown quest period')
    available=None if sources is None else set(sources)
    return tuple(q for q in QUESTS if q['period'] == period and (available is None or q['source'] in available or (q['source']=='any_game' and bool(available & {'rhythm','minesweeper','mafia'}))))


def definition(quest_id: str) -> dict:
    for quest in QUESTS:
        if quest['id'] == quest_id:
            return quest
    raise ValueError('unknown quest')
