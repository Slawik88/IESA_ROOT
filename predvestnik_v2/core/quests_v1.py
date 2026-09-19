"""Clear, varied quest definitions backed by terminal server events."""
from __future__ import annotations
from typing import Final

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
 {"id":"rhythm_augments_1","period":"daily","difficulty":2,"metric":"rhythm_augments_completed","lane":"rhythm_augments","source":"rhythm","target":1,"title":"Заверши забег с аугментациями","help":"В Ритме выбери режим с аугментациями и заверши один забег."},
 {"id":"rhythm_score_500_1","period":"daily","difficulty":2,"metric":"rhythm_score_500","lane":"rhythm_score","source":"rhythm","target":1,"title":"Набери 500 очков за забег","help":"Заверши подтверждённый забег Ритма со счётом не ниже 500."},
 {"id":"minesweeper_plays_2","period":"daily","difficulty":1,"metric":"minesweeper_completed","lane":"mines_play","source":"minesweeper","target":2,"title":"Заверши 2 партии в Сапёре","help":"Победа или поражение засчитываются после завершения партии."},
 {"id":"minesweeper_win_1","period":"daily","difficulty":2,"metric":"minesweeper_win","lane":"mines_win","source":"minesweeper","target":1,"title":"Одержи победу в Сапёре","help":"Заверши любую сложность победой."},
 {"id":"minesweeper_easy_win_1","period":"daily","difficulty":1,"metric":"minesweeper_easy_win","lane":"mines_easy","source":"minesweeper","target":1,"title":"Победи в лёгком Сапёре","help":"Выбери лёгкую сложность и выиграй одну партию."},
 {"id":"minesweeper_normal_win_1","period":"daily","difficulty":2,"metric":"minesweeper_normal_win","lane":"mines_normal","source":"minesweeper","target":1,"title":"Победи в обычном Сапёре","help":"Выбери обычную сложность и выиграй одну партию."},
 {"id":"chest_open_1","period":"daily","difficulty":1,"metric":"chest_revealed","lane":"chest_open","source":"chests","target":1,"title":"Раскрой один сундук","help":"Подойдёт бесплатный или купленный ключ — шансы у них одинаковые."},
 {"id":"pet_feed_1","period":"daily","difficulty":1,"metric":"pet_fed","lane":"pet_care","source":"pet_care","target":1,"title":"Позаботься о питомце","help":"Задание появляется только когда есть еда и питомцу можно восстановить выносливость."},
 {"id":"any_game_18","period":"weekly","difficulty":1,"metric":"game_completed","lane":"flex","source":"any_game","target":18,"title":"Заверши 18 любых игр","help":"Ритм, Сапёр и доступная тебе Мафия складываются в общий прогресс."},
 {"id":"rhythm_runs_10","period":"weekly","difficulty":1,"metric":"rhythm_completed","lane":"rhythm_play","source":"rhythm","target":10,"title":"Заверши 10 забегов в Ритме","help":"Режим можно менять от забега к забегу."},
 {"id":"rhythm_normal_6","period":"weekly","difficulty":1,"metric":"rhythm_normal_completed","lane":"rhythm_normal","source":"rhythm","target":6,"title":"Пройди 6 обычных забегов","help":"Заверши шесть забегов в обычном режиме Ритма."},
 {"id":"rhythm_augments_4","period":"weekly","difficulty":2,"metric":"rhythm_augments_completed","lane":"rhythm_augments","source":"rhythm","target":4,"title":"Пройди 4 забега с аугментациями","help":"Заверши четыре забега в режиме с аугментациями."},
 {"id":"rhythm_score_500_3","period":"weekly","difficulty":2,"metric":"rhythm_score_500","lane":"rhythm_score","source":"rhythm","target":3,"title":"Трижды набери 500 очков","help":"Заверши три подтверждённых забега Ритма со счётом не ниже 500."},
 {"id":"minesweeper_plays_8","period":"weekly","difficulty":1,"metric":"minesweeper_completed","lane":"mines_play","source":"minesweeper","target":8,"title":"Заверши 8 партий в Сапёре","help":"Любая сложность и любой итог партии идут в прогресс."},
 {"id":"minesweeper_wins_4","period":"weekly","difficulty":2,"metric":"minesweeper_win","lane":"mines_win","source":"minesweeper","target":4,"title":"Одержи 4 победы в Сапёре","help":"Сложность можно выбирать самостоятельно."},
 {"id":"minesweeper_easy_wins_3","period":"weekly","difficulty":1,"metric":"minesweeper_easy_win","lane":"mines_easy","source":"minesweeper","target":3,"title":"Победи 3 раза на лёгком поле","help":"Выиграй три партии на лёгкой сложности Сапёра."},
 {"id":"minesweeper_normal_wins_2","period":"weekly","difficulty":2,"metric":"minesweeper_normal_win","lane":"mines_normal","source":"minesweeper","target":2,"title":"Победи 2 раза на обычном поле","help":"Выиграй две партии на обычной сложности Сапёра."},
 {"id":"minesweeper_hard_win_1","period":"weekly","difficulty":3,"metric":"minesweeper_hard_win","lane":"mines_hard","source":"minesweeper","target":1,"title":"Победи на сложном поле","help":"Выиграй одну партию на сложном поле Сапёра."},
 {"id":"mafia_matches_3","period":"weekly","difficulty":3,"metric":"mafia_completed","lane":"mafia_play","source":"mafia","target":3,"title":"Заверши 3 матча Мафии","help":"Задание выдаётся только игрокам, которые уже участвовали в Мафии."},
 {"id":"mafia_win_1","period":"weekly","difficulty":3,"metric":"mafia_win","lane":"mafia_result","source":"mafia","target":1,"title":"Победи в матче Мафии","help":"Победа засчитается всем участникам победившей стороны."},
 {"id":"chest_open_5","period":"weekly","difficulty":1,"metric":"chest_revealed","lane":"chest_open","source":"chests","target":5,"title":"Раскрой 5 сундуков","help":"Ключи дают квесты, походы и экспедиции; при желании два ключа в день можно купить."},
 {"id":"pet_activity_2","period":"weekly","difficulty":2,"metric":"pet_activity_completed","lane":"pet_journey","source":"pets","target":2,"title":"Заверши 2 приключения питомца","help":"Сочетай походы и экспедиции любой доступной длительности."},
 {"id":"pet_feed_3","period":"weekly","difficulty":1,"metric":"pet_fed","lane":"pet_care","source":"pet_care","target":3,"title":"Покорми питомцев 3 раза","help":"Задание появляется только когда в инвентаре уже есть еда для питомцев."},
)

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
