# core/units.py — Боёвка 3.0: реестр боевых юнитов («Казарма»).
# Без внешних зависимостей (иерархия core/). Спецификация: BATTLE_REWORK_CONCEPT.md.
#
# Юниты — ОТДЕЛЬНАЯ от мирных питомцев сущность: только для боёв, без
# персистентного HP. Стихии — пентагон 🔥>❄️>⚡>🗿>🌑>🔥 (+30% по слабой,
# −20% по сильной). Каждый юнит приносит в колоду 3 руны: удар/защита/навык.
from typing import Any, Dict

# ── Стихии ────────────────────────────────────────────────────────────────────

ELEMENTS = ("fire", "ice", "storm", "earth", "dark")
ELEMENT_META: Dict[str, dict] = {
    "fire":  {"emoji": "🔥", "name": "Огонь"},
    "ice":   {"emoji": "❄️", "name": "Лёд"},
    "storm": {"emoji": "⚡", "name": "Шторм"},
    "earth": {"emoji": "🗿", "name": "Земля"},
    "dark":  {"emoji": "🌑", "name": "Тьма"},
}
# element BEATS следующую по кругу
_BEATS = {"fire": "ice", "ice": "storm", "storm": "earth", "earth": "dark", "dark": "fire"}
ELEMENT_STRONG_MULT = 1.30
ELEMENT_WEAK_MULT = 0.80


def element_mult(attacker_el: str | None, defender_el: str | None) -> float:
    if not attacker_el or not defender_el:
        return 1.0
    if _BEATS.get(attacker_el) == defender_el:
        return ELEMENT_STRONG_MULT
    if _BEATS.get(defender_el) == attacker_el:
        return ELEMENT_WEAK_MULT
    return 1.0


# ── Роли и статы ──────────────────────────────────────────────────────────────

ROLES = ("dd", "tank", "support")
ROLE_META: Dict[str, dict] = {
    "dd":      {"emoji": "⚔️", "name": "ДД"},
    "tank":    {"emoji": "🛡", "name": "Танк"},
    "support": {"emoji": "💚", "name": "Саппорт"},
}
# atk / def / hp на уровне 1 (редкость rare)
ROLE_BASE: Dict[str, tuple] = {
    "dd":      (30, 10, 140),
    "tank":    (16, 22, 260),
    "support": (20, 14, 180),
}
UNIT_RARITY_MULT: Dict[str, float] = {"rare": 1.0, "epic": 1.35, "legendary": 1.8}
UNIT_LEVEL_SCALE = 0.12          # +12% статов за уровень (level-1)
UNIT_MAX_LEVEL = 10
UNIT_CRIT_CHANCE: Dict[str, float] = {"dd": 0.20, "tank": 0.15, "support": 0.15}


def unit_stats(unit_id: str, level: int = 1) -> dict:
    """Паспортные статы юнита. Уровень клампится в [1, UNIT_MAX_LEVEL]."""
    u = UNITS[unit_id]
    level = max(1, min(UNIT_MAX_LEVEL, int(level or 1)))
    atk, dfn, hp = ROLE_BASE[u["role"]]
    m = UNIT_RARITY_MULT.get(u["rarity"], 1.0) * (1.0 + UNIT_LEVEL_SCALE * (level - 1))
    return {"atk": int(round(atk * m)), "def": int(round(dfn * m)),
            "hp_max": int(round(hp * m)), "crit": UNIT_CRIT_CHANCE[u["role"]]}


def unit_cp(unit_id: str, level: int = 1) -> int:
    """CP юнита — те же веса, что у старого pet_cp (atk×4 + def×3 + hp×0.5)."""
    s = unit_stats(unit_id, level)
    return int(round(s["atk"] * 4.0 + s["def"] * 3.0 + s["hp_max"] * 0.5))


# ── Синергии отряда ───────────────────────────────────────────────────────────
# 2+ юнита одной стихии в отряде → пассив стихии; 3 разных стихии → «Триада»
# (раз в бой бесплатная AoE-комбо-руна, см. движок).
ELEMENT_SYNERGY: Dict[str, dict] = {
    "fire":  {"desc": "+8% урон отряда",        "dmg_out": 0.08},
    "ice":   {"desc": "−8% входящий урон",       "dmg_in": -0.08},
    "storm": {"desc": "+10% шанс крита",         "crit": 0.10},
    "earth": {"desc": "+10% HP отряда",          "hp": 0.10},
    "dark":  {"desc": "+6% вампиризм",           "lifesteal": 0.06},
}

# ── Реестр юнитов ─────────────────────────────────────────────────────────────
# skill/ult: code — диспетчеризация в services/battle3.py, desc — для UI/доков.

UNITS: Dict[str, Dict[str, Any]] = {
    # ── 🔥 Огонь ──
    "u_salamandra": {
        "name": "Саламандра-Головня", "emoji": "🦎", "element": "fire", "role": "dd", "rarity": "rare",
        "skill": {"code": "burn", "name": "Поджог", "desc": "Удар 90% + горение 3 раунда (25% атаки/раунд)"},
        "ult": {"code": "erupt", "name": "Извержение", "desc": "130% урона ВСЕМ врагам + поджог всех"},
    },
    "u_vepr": {
        "name": "Вепрь Пепелища", "emoji": "🐗", "element": "fire", "role": "tank", "rarity": "epic",
        "skill": {"code": "ember_shell", "name": "Раскалённый панцирь", "desc": "Щит себе 25% HP + отражение 30% урона на раунд"},
        "ult": {"code": "flame_wall", "name": "Стена пламени", "desc": "Щит отряду 20% HP + отражение 35% на раунд"},
    },
    "u_phoenix": {
        "name": "Феникс-Недоросль", "emoji": "🦅", "element": "fire", "role": "support", "rarity": "legendary",
        "skill": {"code": "mend", "name": "Тёплое крыло", "desc": "Лечит самого раненого союзника на 25% его HP"},
        "ult": {"code": "rebirth", "name": "Возрождение", "desc": "Воскрешает павшего с 30% HP (1/бой); если все живы — лечит отряд на 25%"},
    },
    # ── ❄️ Лёд ──
    "u_ice_golem": {
        "name": "Ледяной Голем", "emoji": "🧊", "element": "ice", "role": "tank", "rarity": "rare",
        "skill": {"code": "chill_taunt", "name": "Мёрзлый таунт", "desc": "Перехватывает атаки следующей фазы врага, атакующие теряют 6 ярости"},
        "ult": {"code": "absolute_zero", "name": "Абсолютный ноль", "desc": "Вражеский отряд пропускает следующую фазу"},
    },
    "u_striga": {
        "name": "Снежная Стрига", "emoji": "❄️", "element": "ice", "role": "dd", "rarity": "rare",
        "skill": {"code": "frost_bite", "name": "Обморожение", "desc": "Удар 100% + 20% шанс заморозки (враг теряет действие)"},
        "ult": {"code": "ice_storm", "name": "Ледяной шторм", "desc": "150% урона + гарантированная заморозка цели"},
    },
    "u_olen": {
        "name": "Олень Инея", "emoji": "🦌", "element": "ice", "role": "support", "rarity": "epic",
        "skill": {"code": "ice_shield", "name": "Наледь", "desc": "Щит самому раненому союзнику 30% его HP"},
        "ult": {"code": "nast", "name": "Наст", "desc": "Щиты всему отряду по 25% HP"},
    },
    # ── ⚡ Шторм ──
    "u_zmey": {
        "name": "Грозовой Змей", "emoji": "🐍", "element": "storm", "role": "dd", "rarity": "rare",
        "skill": {"code": "chain", "name": "Цепная молния", "desc": "Удар 100% + 40% урона перескакивает на соседа"},
        "ult": {"code": "groza", "name": "Гроза", "desc": "110% урона по ВСЕМ врагам"},
    },
    "u_scorpion": {
        "name": "Штормовой Скорпион", "emoji": "🦂", "element": "storm", "role": "tank", "rarity": "rare",
        "skill": {"code": "counter_stance", "name": "Разрядная стойка", "desc": "Щит себе 20% HP + контрудар 80% атакующему"},
        "ult": {"code": "shell_shock", "name": "Разряд панциря", "desc": "Удар 100% + оглушение цели (пропуск действия)"},
    },
    "u_burevestnik": {
        "name": "Буревестник", "emoji": "🕊", "element": "storm", "role": "support", "rarity": "epic",
        "skill": {"code": "tailwind", "name": "Попутный ветер", "desc": "+10 ярости отряду, в следующем раунде рука 4 руны"},
        "ult": {"code": "second_wind", "name": "Второе дыхание", "desc": "Следующий раунд: рука 5 рун + 1 🧿 Фокуса"},
    },
    # ── 🗿 Земля ──
    "u_strazh": {
        "name": "Кремневый Страж", "emoji": "🗿", "element": "earth", "role": "tank", "rarity": "rare",
        "skill": {"code": "taunt_all", "name": "Бастионный таунт", "desc": "Перехватывает ВСЕ атаки следующей фазы, +50% защиты"},
        "ult": {"code": "bastion", "name": "Бастион", "desc": "Отряд неуязвим на следующую фазу врага"},
    },
    "u_aspid": {
        "name": "Обсидиановый Аспид", "emoji": "🪨", "element": "earth", "role": "dd", "rarity": "rare",
        "skill": {"code": "pierce", "name": "Пробитие", "desc": "Удар 110%, игнорирует 40% защиты"},
        "ult": {"code": "shatter", "name": "Расколоть", "desc": "120% урона + снимает 40% защиты цели до конца боя"},
    },
    "u_korneplet": {
        "name": "Корнеплёт", "emoji": "🌿", "element": "earth", "role": "support", "rarity": "epic",
        "skill": {"code": "regrow", "name": "Прорастание", "desc": "Лечит отряд на 10% + реген 5% на 2 раунда"},
        "ult": {"code": "roots", "name": "Объятия корней", "desc": "Лечит отряд на 20% + цель −50% урона на раунд"},
    },
    # ── 🌑 Тьма ──
    "u_pozhiratel": {
        "name": "Пожиратель Снов", "emoji": "👁", "element": "dark", "role": "dd", "rarity": "rare",
        "skill": {"code": "drain", "name": "Высасывание", "desc": "Удар 100% + вампиризм 35%"},
        "ult": {"code": "nightmare", "name": "Кошмар", "desc": "Урон 20% недостающего HP цели (мин. 80% атаки) + вампиризм"},
    },
    "u_vdovodel": {
        "name": "Вдоводел", "emoji": "🕷", "element": "dark", "role": "tank", "rarity": "rare",
        "skill": {"code": "web", "name": "Паутина", "desc": "Следующая атака цели ослаблена на 50%, щит себе 15% HP"},
        "ult": {"code": "cocoon", "name": "Кокон", "desc": "Цель: −50% урона на 2 раунда, не может критовать"},
    },
    "u_plakalschitsa": {
        "name": "Плакальщица", "emoji": "🌑", "element": "dark", "role": "support", "rarity": "epic",
        "skill": {"code": "grief", "name": "Скорбь", "desc": "Крадёт 12 ярости врага в свою шкалу"},
        "ult": {"code": "requiem", "name": "Реквием", "desc": "Обнуляет ярость врага + отряд +15% урона на 2 раунда"},
    },
    # ── Легендарный вне стихий (стихия меняется под слабость врага) ──
    "u_porozhdenie": {
        "name": "Порождение Бездны", "emoji": "🐉", "element": None, "role": "dd", "rarity": "legendary",
        "skill": {"code": "void_strike", "name": "Удар Пустоты", "desc": "Удар 115% стихией, которой враг слаб (меняется каждый раунд)"},
        "ult": {"code": "abyss_call", "name": "Зов Бездны", "desc": "5 ударов по 45% всеми пятью стихиями"},
    },
}

# Стартовый выбор новичка: 1 из 3 rare (разные стихии и роли)
STARTER_UNIT_CHOICES = ("u_salamandra", "u_ice_golem", "u_zmey")


def get_unit(unit_id: str) -> Dict | None:
    return UNITS.get(unit_id)
