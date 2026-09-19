"""Sequential, non-expiring story cases for Reconstruction."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Final

TARGET_MEANINGFUL_DAYS: Final = 3

def _case(policy: str, case_id: str, title: str, intro: str, paths: dict,
          second_reveal: str, finales: dict) -> dict[str, Any]:
    return {"policy_version": policy, "case_id": case_id, "title": title,
            "intro": intro, "paths": paths, "second_reveal": second_reveal,
            "finales": finales, "target_days": TARGET_MEANINGFUL_DAYS}

CASE_CATALOG: Final[tuple[dict[str, Any], ...]] = (
    _case("weekly-case-v1-2026-08-27", "bell_beneath_water", "Колокол под водой",
        "После отлива на дне слышен звон. Он повторяет ритм последнего путника, но на карте нет звонницы.", {
            "follow_bell": {"name":"Идти на звон","promise":"Ответить источнику сигнала и принять риск ложного эха.","consequence":"Звон приводит к затопленной звоннице. Кто-то отвечает твоим же ритмом.","coda":"Ты оставляешь звоннице право отвечать — но только на осознанный вызов."},
            "follow_silence": {"name":"Идти за тишиной","promise":"Найти место, которое намеренно не отвечает Колоколу.","consequence":"Тишина оказывается печатью: под водой удерживают не чудовище, а чужое воспоминание.","coda":"Ты сохраняешь печать и уносишь способ услышать то, что не должно звать первым."}},
        "На внутренней стене вырезано: «Не всякий ответ просит продолжения».", {
            "many_voices":{"name":"Хор свидетельств","text":"Звонница отвечает тремя голосами и признаёт тебя свидетелем."},
            "careful_echo":{"name":"Осторожное эхо","text":"Ты различаешь главное: ответ Колокола меняется от способа слушать."},
            "single_note":{"name":"Одна сохранённая нота","text":"Ты выносишь из воды одну ноту, которая не исчезнет с новой неделей."}}),
    _case("weekly-case-v1-2026-08-27-02", "station_without_shadows", "Станция без теней",
        "Ночной состав приходит пустым. В его окнах отражаются все, кроме тех, кто стоит на платформе.", {
            "board_train":{"name":"Войти в состав","promise":"Проверить маршрут изнутри, оставив платформу позади.","consequence":"Каждый вагон хранит один несделанный выбор, но двери открываются только вперёд.","coda":"Ты возвращаешь поезду тень и оставляешь одно окно незаполненным."},
            "search_platform":{"name":"Исследовать платформу","promise":"Искать того, кто отправляет поезд, не принимая его приглашение.","consequence":"Под табло обнаруживается расписание прибытий людей, которые ещё не приняли решение.","coda":"Ты стираешь своё имя из расписания, сохраняя маршрут для следующего свидетеля."}},
        "В будке дежурного лежит компостер: он пробивает не билет, а воспоминание о пункте назначения.", {
            "many_voices":{"name":"Полный маршрут","text":"Три способа действия складываются в карту линии, которой нет на схемах."},
            "careful_echo":{"name":"Возвращённый билет","text":"Маршрут не раскрыт целиком, но поезд больше не может назвать тебя пассажиром без согласия."},
            "single_note":{"name":"Остановка по требованию","text":"Ты сохраняешь одну точку маршрута — достаточно, чтобы однажды вернуться осознанно."}}),
    _case("weekly-case-v1-2026-08-27-03", "garden_of_second_names", "Сад вторых имён",
        "На пустыре выросли таблички с именами. Каждое принадлежит знакомому человеку, но никто их не помнит.", {
            "read_names":{"name":"Прочитать таблички","promise":"Дать забытым именам прозвучать, рискуя быть услышанным.","consequence":"Одно имя отвечает голосом твоего спутника и просит не искать владельца.","coda":"Ты оставляешь имена в саду, но возвращаешь им право быть произнесёнными."},
            "trace_roots":{"name":"Проследить корни","promise":"Искать источник сада, не произнося написанного.","consequence":"Корни сходятся под старой книгой учёта, где имена записаны как долги.","coda":"Ты закрываешь книгу, превращая долг в добровольную память."}},
        "Между грядками стоит пустая табличка. Буквы появляются только тогда, когда на неё перестают смотреть.", {
            "many_voices":{"name":"Имена возвращены","text":"Разные способы действия отделяют память от владения: сад больше никого не удерживает."},
            "careful_echo":{"name":"Право на забвение","text":"Ты освобождаешь часть имён и понимаешь, почему некоторые решили остаться."},
            "single_note":{"name":"Одно настоящее имя","text":"Ты уносишь единственное имя без владельца — не трофей, а обещание не присваивать его."}}),
    _case("weekly-case-v1-2026-08-27-04", "lighthouse_looking_inward", "Маяк, смотрящий внутрь",
        "На рассвете маяк разворачивает луч от моря к городу. Освещённые окна показывают события завтрашнего дня.", {
            "climb_lighthouse":{"name":"Подняться к линзе","promise":"Остановить механизм там, где будущее превращается в свет.","consequence":"Линза собрана из осколков зеркал; в каждом ты уже сделал другой выбор.","coda":"Ты оставляешь луч городу, но лишаешь его власти выдавать возможность за судьбу."},
            "follow_beam":{"name":"Следовать за лучом","promise":"Проверить предсказания на улицах, не касаясь механизма.","consequence":"Будущее меняется после каждого замеченного окна: наблюдение оказывается частью машины.","coda":"Ты гасишь последнее окно и сохраняешь право города удивить самого себя."}},
        "В журнале смотрителя нет прогнозов — только список тех, кто поверил лучу и тем самым сделал его точным.", {
            "many_voices":{"name":"Неслучившийся рассвет","text":"Три способа действия размыкают предсказание. Утро приходит без заранее назначенного владельца."},
            "careful_echo":{"name":"Слепая зона","text":"Ты создаёшь место, которого луч не видит, и город впервые получает пространство для ошибки."},
            "single_note":{"name":"Погашенное окно","text":"Одно будущее перестаёт притворяться неизбежным. Для начала этого достаточно."}}),
    _case("weekly-case-v1-2026-08-28-05", "bridge_of_unspoken_answers", "Мост несказанных ответов",
        "Над ущельем появился мост из записок. На каждой — ответ на вопрос, который никто не решился задать.", {
            "read_crossing":{"name":"Читать по пути","promise":"Перейти мост, принимая чужие ответы как подсказки, а не приказы.","consequence":"Записки меняют порядок: мост проверяет, какой ответ ты поставишь первым.","coda":"Ты оставляешь ответы на месте и уносишь право задать собственный вопрос."},
            "walk_blank":{"name":"Искать пустые листы","promise":"Пройти по местам, где ответа ещё нет, сохраняя неопределённость.","consequence":"Пустые листы держат мост крепче исписанных: неизвестность оказывается его опорой.","coda":"Ты сохраняешь один пустой лист — не обещание ответа, а место для честного выбора."}},
        "Под последней доской написано: «Чужая уверенность не сокращает твою дорогу».", {
            "many_voices":{"name":"Свободный вопрос","text":"Три способа действия отделяют совет от приказа, и мост перестаёт выбирать за путника."},
            "careful_echo":{"name":"Неполная переправа","text":"Ты находишь достаточно опор, чтобы перейти, не превращая неизвестное в ошибку."},
            "single_note":{"name":"Чистое поле","text":"Один незаполненный ответ остаётся твоим — этого хватает, чтобы дорога продолжилась."}}),
    _case("weekly-case-v1-2026-08-28-06", "archive_of_warm_snow", "Архив тёплого снега",
        "В закрытом архиве идёт тёплый снег. Он тает только на записях о событиях, которых не было.", {
            "save_pages":{"name":"Спасти записи","promise":"Отделить подлинную память от удобной версии прошлого.","consequence":"Чернила на спасённых страницах спорят друг с другом, но даты остаются одинаковыми.","coda":"Ты сохраняешь противоречия рядом: ни одно не получает право стать единственной правдой."},
            "follow_snow":{"name":"Проследить снег","promise":"Найти источник правок, не решая заранее, какая запись верна.","consequence":"Снег выпадает из пустой папки с твоим именем — она ждёт историю, которую ты откажешься помнить.","coda":"Ты закрываешь пустую папку и оставляешь будущее без заранее написанной версии."}},
        "Каталог различает не правду и ложь, а записи, за которые кто-то готов отвечать.", {
            "many_voices":{"name":"Сверенное прошлое","text":"Разные методы сохраняют расхождения и раскрывают того, кто пытался стереть выбор."},
            "careful_echo":{"name":"Две честные версии","text":"Ты не устраняешь противоречие, но лишаешь его возможности тайно управлять настоящим."},
            "single_note":{"name":"Нетронутая дата","text":"Одна дата остаётся без исправлений и становится надёжной точкой возвращения."}}),
    _case("weekly-case-v1-2026-08-28-07", "market_of_borrowed_hours", "Рынок одолженных часов",
        "Раз в месяц на площади продают лишние часы. Покупатели узнают цену только после того, как время потрачено.", {
            "trace_sellers":{"name":"Искать продавцов","promise":"Выяснить, кому принадлежало время и было ли согласие настоящим.","consequence":"Каждый продавец помнит оплату, но никто не помнит, когда соглашался на сделку.","coda":"Ты возвращаешь часам имена владельцев и запрещаешь рынку торговать без явного согласия."},
            "watch_buyers":{"name":"Следить за покупателями","promise":"Понять, что меняется в жизни после чужого дополнительного часа.","consequence":"Купленное время всегда уходит на решение, которого покупатель избегал дольше всего.","coda":"Ты оставляешь выбор покупателю, но делаешь цену видимой до первого шага."}},
        "Главные часы площади стоят: рынок существует только за счёт времени, которое люди перестали считать своим.", {
            "many_voices":{"name":"Возвращённый полдень","text":"Три подхода раскрывают цепочку сделок, и площадь впервые проживает собственный час."},
            "careful_echo":{"name":"Цена до решения","text":"Рынок остаётся, но ни одна сделка больше не скрывает, чьё время будет потрачено."},
            "single_note":{"name":"Один свободный час","text":"Ты возвращаешь владельцу один час без условий и оставляешь след для следующего расследования."}}),
    _case("weekly-case-v1-2026-08-28-08", "choir_behind_the_wall", "Хор за стеной",
        "В старом доме каждую ночь поёт хор. Комнаты пусты, а голоса знают решения жильцов раньше них самих.", {
            "open_rooms":{"name":"Открывать комнаты","promise":"Искать источник голосов, сверяя песню с реальными следами людей.","consequence":"В каждой комнате звучит только один возможный выбор, будто остальные никогда не существовали.","coda":"Ты открываешь окна и возвращаешь комнатам шум мира, в котором есть больше одного пути."},
            "listen_outside":{"name":"Слушать с улицы","promise":"Проверить, кому предназначена песня, не входя в навязанный сценарий.","consequence":"Снаружи хор слышен как множество несогласных голосов; идеальная мелодия существует только за стеной.","coda":"Ты сохраняешь разноголосицу и лишаешь стену права выдавать её за ошибку."}},
        "На чердаке найден камертон без частоты: он звучит только рядом с решением, которое ещё можно изменить.", {
            "many_voices":{"name":"Хор возможностей","text":"Три дисциплины возвращают голосам различия, и песня перестаёт предсказывать выбор."},
            "careful_echo":{"name":"Открытая репетиция","text":"Ты не находишь дирижёра, но делаешь слышимыми голоса, которые раньше подавлялись стеной."},
            "single_note":{"name":"Непредсказанная нота","text":"Одна нота возникает после песни и доказывает: решение всё ещё принадлежит человеку."}}),
)

CONTENT_PACKS: Final[tuple[dict[str, Any], ...]] = (
    {"id": "weekly-cases-pack-1", "case_ids": tuple(item["case_id"] for item in CASE_CATALOG[:4])},
    {"id": "weekly-cases-pack-2", "case_ids": tuple(item["case_id"] for item in CASE_CATALOG[4:])},
)

def definition_digest(case: dict[str, Any]) -> str:
    canonical = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def case_token(case: dict[str, Any]) -> str:
    """Bounded identity for Telegram callbacks; order is display-only."""
    return definition_digest(case)[:12]

POLICY_VERSION: Final = CASE_CATALOG[0]["policy_version"]
CASE_ID: Final = CASE_CATALOG[0]["case_id"]
PATHS: Final = CASE_CATALOG[0]["paths"]
FINALES: Final = CASE_CATALOG[0]["finales"]

def case_for_policy(policy_version: str) -> dict[str, Any] | None:
    return next((item for item in CASE_CATALOG if item["policy_version"] == policy_version), None)

def next_case(policy_version: str) -> dict[str, Any] | None:
    for index, item in enumerate(CASE_CATALOG):
        if item["policy_version"] == policy_version:
            return CASE_CATALOG[index + 1] if index + 1 < len(CASE_CATALOG) else None
    return None

def finale_id(completed_categories: set[str]) -> str:
    known = set(completed_categories) & {"mastery", "tempo", "discovery"}
    return "many_voices" if len(known) == 3 else "careful_echo" if len(known) == 2 else "single_note"

def case_view(row: dict[str, Any], completed_categories: set[str], case: dict[str, Any] | None = None) -> dict[str, Any]:
    case = case or case_for_policy(str(row.get("policy_version") or ""))
    if not case:
        raise ValueError("Unknown immutable Weekly Case definition")
    target = int(case["target_days"])
    progress = min(target, max(0, int(row.get("progress_days") or 0)))
    path_id = row.get("path_id")
    path = case["paths"].get(str(path_id)) if path_id else None
    completed = bool(path and progress >= target)
    ending_id = str(row.get("finale_id") or finale_id(completed_categories)) if completed else None
    following = next_case(case["policy_version"])
    position = next(i + 1 for i, item in enumerate(CASE_CATALOG) if item["policy_version"] == case["policy_version"])
    return {"policy_version":case["policy_version"],"case_id":case["case_id"],"case_token":case_token(case),"title":case["title"],"intro":case["intro"],
        "path_id":path_id,"paths":[{"id":key,**value} for key,value in case["paths"].items()],"progress_days":progress,"target_days":target,
        "resets_on_week_boundary":False,"expires":False,"stars_can_buy_progress":False,"economic_reward":None,
        "reveals":[{"step":1,"unlocked":progress>=1,"text":path["consequence"] if path and progress>=1 else None},{"step":2,"unlocked":progress>=2,"text":case["second_reveal"] if progress>=2 else None}],
        "completed":completed,"finale":({"id":ending_id,**case["finales"][ending_id],"path_coda":path["coda"]} if ending_id else None),
        "next_case_available":bool(completed and following),"next_case_title":following["title"] if completed and following else None,
        "catalog_position":position,"catalog_total":len(CASE_CATALOG)}

def public_manifest() -> dict[str, Any]:
    return {"policy_version":"weekly-case-catalog-v2-2026-08-28","case_id":CASE_ID,"case_count":len(CASE_CATALOG),
        "content_packs":[{"id":pack["id"],"case_count":len(pack["case_ids"])} for pack in CONTENT_PACKS],
        "target_meaningful_days":TARGET_MEANINGFUL_DAYS,"path_count":2,"finale_count":3,"expires":False,"new_currency":False,"stars_can_buy_progress":False}
