"""Живой реестр Reconstruction 3.0.

Этот модуль содержит только продуктовые константы и контент. Здесь нет БД,
FastAPI и Telegram: боевой движок может валидировать этот реестр изолированно,
а клиент — получать из него один и тот же контракт.

Старая ``core.units`` остаётся миграционным реестром. Новая кампания намеренно
не добавляет стартовых героев в старую гачу и не меняет production-экономику.
"""
from __future__ import annotations

from typing import Any, Final

GAME_VERSION: Final = "3.0.0-alpha.3"
BALANCE_VERSION: Final = "r13-2026-08-22-rhythm-keeper"
FEATURE_FLAG_KEY: Final = "game_reconstruction_v1"
CAMPAIGN_ID: Final = "echoes_of_the_drowned_bell"


# У нового стартового отряда нет редкости: герои работают как три автоматических
# канала урона вокруг одного понятного действия игрока — нажатия по ядру.
STARTER_UNITS: dict[str, dict[str, Any]] = {
    "r_oath_bell": {
        "name": "Клятвенный Звонарь",
        "short_name": "Звонарь",
        "emoji": "🔔",
        "role": "guardian",
        "element": "stone",
        "stats": {"hp": 168, "power": 22, "armor": 18, "move": 3, "range": 1},
        "basic": {
            "code": "oath_toll",
            "name": "Звон клятвы",
            "description": (
                "Автоматически бьёт в такт колоколу и поддерживает пассивный "
                "урон отряда, пока игрок набирает Импульс."
            ),
        },
        "skill": {
            "code": "oath_circle",
            "name": "Круг обещания",
            "description": (
                "Каждый автоматический Разряд усиливает следующий удар отряда."
            ),
            "cooldown": 2,
        },
        "mastery": "Не рвать серию перед автоматическим Разрядом.",
        "counterplay": "Даёт стабильность, но не заменяет активные нажатия.",
    },
    "r_red_seam": {
        "name": "Швея Красной Нити",
        "short_name": "Швея",
        "emoji": "🪡",
        "role": "striker",
        "element": "ember",
        "stats": {"hp": 112, "power": 32, "armor": 8, "move": 4, "range": 2},
        "basic": {
            "code": "needle_step",
            "name": "Стежок на ходу",
            "description": (
                "Каждый десятый удар серии прошивает цель дополнительным уроном."
            ),
        },
        "skill": {
            "code": "red_seam",
            "name": "Красный шов",
            "description": (
                "Критическое нажатие оставляет шов; следующий Разряд разрывает "
                "его и наносит дополнительный урон."
            ),
            "cooldown": 2,
        },
        "mastery": "Попадать в золотое окно, не превращая бой в ритм-экзамен.",
        "counterplay": "Вне золотого окна Швея не создаёт взрывной темп.",
    },
    "r_tide_cartographer": {
        "name": "Картограф Прилива",
        "short_name": "Картограф",
        "emoji": "🌊",
        "role": "controller",
        "element": "tide",
        "stats": {"hp": 128, "power": 18, "armor": 11, "move": 3, "range": 3},
        "basic": {
            "code": "undertow",
            "name": "Обратная волна",
            "description": (
                "Постепенно наполняет Импульс даже без нажатий и не даёт бою "
                "полностью остановиться."
            ),
        },
        "skill": {
            "code": "course_change",
            "name": "Смена течения",
            "description": (
                "После пробития вражеской печати сразу добавляет заряд к Импульсу."
            ),
            "cooldown": 2,
        },
        "mastery": "Пробивать печати быстро, пока они не съели пассивный урон.",
        "counterplay": "Его вклад раскрывается только в длинной серии.",
    },
}

STARTER_SQUAD: Final = tuple(STARTER_UNITS)


# После каждой волны игрок выбирает одно усиление. Это единственная пауза с
# решением: сам раунд остаётся чистым автокликером без панели способностей.
CLICKER_UPGRADES: dict[str, dict[str, Any]] = {
    "heavy_echo": {
        "name": "Тяжёлый резонанс",
        "emoji": "🔔",
        "archetype": "Напор",
        "description": "+18 урона каждого точного знака.",
        "tradeoff": "Сигнал гаснет на 0,16 с раньше.",
        "effect": {"tap_power": 18, "signal_window_ms": -160},
    },
    "quick_current": {
        "name": "Глубокое течение",
        "emoji": "🌊",
        "archetype": "Темп",
        "description": "Пассивный урон отряда усиливается в 3,2 раза.",
        "tradeoff": "Разряд требует пять точных знаков вместо четырёх.",
        "effect": {"auto_dps_multiplier": 3.2, "charge_per_hit": -5},
    },
    "golden_seam": {
        "name": "Живая нить",
        "emoji": "🪡",
        "archetype": "Точность",
        "description": "Золотое окно шире на 0,18 с, критический удар сильнее.",
        "tradeoff": "Обычный точный знак наносит на 10 меньше урона.",
        "effect": {"critical_window_ms": 180, "critical_multiplier": 0.5, "tap_power": -10},
    },
    "deep_discharge": {
        "name": "Грозовой разряд",
        "emoji": "⚡",
        "archetype": "Взрыв",
        "description": "+95 урона автоматического Разряда.",
        "tradeoff": "Каждый обычный знак наносит на 8 меньше урона.",
        "effect": {"overdrive_power": 95, "tap_power": -8},
    },
    "last_bell": {
        "name": "Клятва тишины",
        "emoji": "◌",
        "archetype": "Контроль",
        "description": "Первая неверная руна волны не лечит цель и сохраняет половину заряда.",
        "tradeoff": "Пассивный урон отряда снижается на 40%.",
        "effect": {"mistake_guard": True, "auto_dps_multiplier": 0.6},
    },
    "hungry_pattern": {
        "name": "Голодный узор",
        "emoji": "✦",
        "archetype": "Риск",
        "description": "Точная серия наращивает урон на 80% быстрее.",
        "tradeoff": "Ошибка сильнее лечит цель и полностью гасит заряд.",
        "effect": {
            "combo_step_multiplier": 1.8,
            "wrong_heal_bonus": 55,
            "reset_charge_on_wrong": True,
        },
    },
}


# Контент первого часа. ``implemented`` — честный технический статус, а не
# обещание интерфейсу. Первая волна делает полностью играбельной e01; следующие
# встречи уже зафиксированы как контракт, чтобы движок не проектировался под
# единственную цель «убить всех».
ENCOUNTERS: dict[str, dict[str, Any]] = {
    "e01_two_bells": {
        "order": 1,
        "name": "Два безымянных колокола",
        "implemented": True,
        "objective": {
            "type": "rush",
            "description": "Разбить три воплощения колокола до затухания эха.",
            "waves": 3,
            "round_limit": 3,
        },
        "teaches": ("серия нажатий", "золотое окно", "разряд", "усиление между волнами"),
        "mastery": "Победить три волны и удержать серию 30 без обязательного ритм-экзамена.",
        "reward_choice": ("m_mobile_oath", "m_long_seam", "m_safe_current"),
    },
    "e02_shattered_causeway": {
        "order": 2,
        "name": "Разломанный тракт",
        "implemented": True,
        "objective": {
            "type": "streak",
            "description": "Провести живой Фонарь через три волны, сохраняя точность выше 75%.",
            "waves": 3,
            "round_limit": 3,
            "lantern_integrity": 100,
            "minimum_accuracy": 75,
        },
        "teaches": ("точная серия", "восстановление после ошибки", "длинный забег"),
        "mastery": "Довести Фонарь без единого усиления, которое расширяет окно сигнала.",
        "reward_choice": ("m_resonant_guard", "m_cross_stitch", "m_reverse_flow"),
    },
    "e03_ink_path": {
        "order": 3,
        "branch": "ink",
        "name": "Чернильная тропа",
        "implemented": True,
        "objective": {
            "type": "decipher",
            "description": "Отличить настоящую руну от отражений и разрушить три чернильные маски.",
            "waves": 3,
            "round_limit": 3,
            "clarity": 100,
        },
        "teaches": ("ложные сигналы", "чтение знака", "точность без спама"),
        "mastery": "Найти каждый оригинал с первой попытки.",
    },
    "e03_ash_path": {
        "order": 3,
        "branch": "ash",
        "name": "Пепельная тропа",
        "implemented": True,
        "objective": {
            "type": "survival",
            "description": "Удержать костёр, отвечая правильной руной на три ускоряющиеся волны.",
            "waves": 3,
            "round_limit": 3,
            "fire_integrity": 100,
        },
        "teaches": ("смена темпа", "риск золотого окна", "контроль ошибок"),
        "mastery": "Костёр сохраняет не меньше 70% прочности.",
    },
    "e04_drowned_names": {
        "order": 4,
        "name": "Долг утонувших имён",
        "implemented": True,
        "objective": {
            "type": "sequence",
            "description": "Запомнить короткие цепочки рун и разорвать три якоря в показанном порядке.",
            "waves": 3,
            "round_limit": 3,
            "sequence_lengths": (2, 3, 3),
        },
        "teaches": ("короткая память", "последовательность", "цена поспешного ответа"),
        "mastery": "Разорвать все якоря без повторного показа цепочек.",
    },
    "e05_mirror_courtyard": {
        "order": 5,
        "name": "Зеркальный двор",
        "implemented": True,
        "objective": {
            "type": "duel_rule",
            "description": "Победить Переписчика, который запрещает повторять последнюю выбранную позицию.",
            "waves": 3,
            "round_limit": 3,
            "mirror_wards": 3,
        },
        "teaches": ("чтение перестановки", "смена позиции", "адаптация серии"),
        "mastery": "Не получить ни одной кары за повтор позиции.",
    },
    "e06_archivist": {
        "order": 6,
        "name": "Архивариус Утонувшего Колокола",
        "implemented": True,
        "objective": {
            "type": "boss",
            "description": "Пережить три фазы и разорвать запись собственного имени.",
            "waves": 3,
            "round_limit": 3,
        },
        "phases": (
            {
                "name": "Запись",
                "rule": "Босс запоминает выбранную позицию и делает её ложной в следующем сигнале.",
                "counter": "Сопоставлять сам знак, а не нажимать привычную сторону.",
            },
            {
                "name": "Прилив",
                "rule": "Окно сигнала то сжимается, то расширяется в показанном заранее ритме.",
                "counter": "Не спешить в длинном окне и не охотиться за золотым бонусом в коротком.",
            },
            {
                "name": "Последнее имя",
                "rule": "Архивариус показывает две руны подряд и принимает только правильную последовательность.",
                "counter": "Удержать короткий узор и не превращать ответ в спам.",
            },
        ),
        "mastery": "Пройти все фазы с точностью не ниже 90%.",
    },
}


MEMORIES: dict[str, dict[str, str]] = {
    "m_mobile_oath": {
        "name": "Клятва в пути",
        "unit_id": "r_oath_bell",
        "effect": "Первая ошибка волны сохраняет половину серии.",
        "tradeoff": "Разряд наносит на 15% меньше урона.",
    },
    "m_long_seam": {
        "name": "Длинный стежок",
        "unit_id": "r_red_seam",
        "effect": "Золотое попадание усиливает два следующих точных знака.",
        "tradeoff": "Сам золотой удар имеет меньший критический множитель.",
    },
    "m_safe_current": {
        "name": "Тихая заводь",
        "unit_id": "r_tide_cartographer",
        "effect": "Первый пропущенный сигнал волны не обрывает серию.",
        "tradeoff": "Пассивный урон отряда снижается на 20%.",
    },
    "m_resonant_guard": {
        "name": "Ответный звон",
        "unit_id": "r_oath_bell",
        "effect": "После трёх точных знаков следующая ошибка не лечит цель.",
        "tradeoff": "За защищённую ошибку всё равно теряется весь заряд.",
    },
    "m_cross_stitch": {
        "name": "Крестовый шов",
        "unit_id": "r_red_seam",
        "effect": "Каждое пятое точное попадание дважды продвигает Импульс.",
        "tradeoff": "Бонус урона пятого попадания исчезает.",
    },
    "m_reverse_flow": {
        "name": "Обратное русло",
        "unit_id": "r_tide_cartographer",
        "effect": "После золотого удара следующий сигнал открывается медленнее и живёт дольше.",
        "tradeoff": "Серия растёт медленнее в обычных окнах.",
    },
}


def validate_content() -> list[str]:
    """Вернуть ошибки контракта, не падать при импорте production-процесса."""
    errors: list[str] = []
    if len(STARTER_UNITS) != 3:
        errors.append("Стартовый отряд должен содержать ровно трёх героев.")
    if {u["role"] for u in STARTER_UNITS.values()} != {"guardian", "striker", "controller"}:
        errors.append("Стартовый отряд должен покрывать guardian/striker/controller.")
    if len(CLICKER_UPGRADES) < 6:
        errors.append("Автокликеру нужно минимум шесть различающихся межволновых усилений.")
    orders = {int(e["order"]) for e in ENCOUNTERS.values()}
    if orders != set(range(1, 7)):
        errors.append("Первый час должен содержать этапы 1–6 (на этапе 3 разрешена развилка).")
    objective_types = {e["objective"]["type"] for e in ENCOUNTERS.values()}
    if len(objective_types) < 5:
        errors.append("Кампания должна проектироваться минимум под пять типов целей.")
    boss = ENCOUNTERS.get("e06_archivist", {})
    if len(boss.get("phases", ())) < 3:
        errors.append("Первый босс обязан иметь минимум три различающиеся фазы.")
    for encounter_id, encounter in ENCOUNTERS.items():
        for memory_id in encounter.get("reward_choice", ()):
            if memory_id not in MEMORIES:
                errors.append(f"{encounter_id}: неизвестная память {memory_id}.")
    return errors
