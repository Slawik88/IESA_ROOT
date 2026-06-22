"""
services/profile_render.py
Pure profile rendering — no bot/aiogram imports.
Used by both bot/handlers/identity.py and FastAPI/routers/themes.py.

Returns HTML string compatible with both Telegram's HTML parse_mode
AND browser innerHTML (same tag subset: <b>, <i>, <code>, <a>).
"""
import re
from datetime import datetime

from core.constants import XP_PER_LEVEL
from core.registry import PET_SPECIES
from services import roles
from services.formatting import parse_dt
from services.utils import safe_html, resolve_display_name


# ── VIP badge (Implementation Block 3.1) ────────────────────────────────────────

def format_display_name(name: str, is_vip: bool) -> str:
    """Единственное место, определяющее как выглядит VIP-бейдж."""
    return f"👑 {name}" if is_vip else name


# ── helpers ───────────────────────────────────────────────────────────────────

def _compact(n) -> str:
    try:
        n = int(float(n))
    except (TypeError, ValueError):
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m".replace(".0m", "m")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)


def _xp_bar(current: int, maximum: int, length: int = 8) -> str:
    filled = int((min(current, maximum) / maximum) * length) if maximum > 0 else 0
    return "█" * filled + "░" * (length - filled)


def _xp_pct(current: int, maximum: int) -> int:
    return int((min(current, maximum) / maximum) * 100) if maximum > 0 else 0


def _premium_bar(pct: int, length: int = 7) -> str:
    filled = round(pct / 100 * length)
    return "▰" * filled + "▱" * (length - filled)


def _fatigue_icon(fatigue: int) -> str:
    if fatigue >= 100: return "⛔"
    if fatigue >= 80:  return "🔴"
    if fatigue >= 40:  return "🟡"
    return "🟢"


def _marriage_duration(val) -> str:
    if not val:
        return "?"
    dt = parse_dt(val)
    if not dt:
        return "?"
    delta = datetime.now() - dt
    d, h = delta.days, delta.seconds // 3600
    return f"{d} дн." if d > 0 else f"{h} ч."


def _load_theme(theme_id: str) -> dict:
    from core.themes import THEMES, DEFAULT_THEME
    return THEMES.get(theme_id, THEMES[DEFAULT_THEME])


def _pets_block(pets: list, prefix: str = "") -> str:
    active  = [p for p in pets if p.get("placement") == "active"]
    passive = [p for p in pets if p.get("placement") == "passive"]
    if not active and not passive:
        return f"{prefix}└ Нет питомцев\n"
    slots = []
    if active:
        slots.append(("⚔️", "Актив", active[0]))
    if passive:
        slots.append(("💤", "Пассив", passive[0]))
    lines = []
    for i, (icon, role, p) in enumerate(slots):
        sp   = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
        lvl  = p.get("pet_level", 1) or 1
        dups = p.get("duplicates_collected", 0) or 0
        fat  = p.get("fatigue", 0)
        sym  = "└" if i == len(slots) - 1 else "├"
        pet_name = p["name"]
        sp_part  = f" ({sp})" if sp and sp != pet_name else ""
        lines.append(
            f"{prefix}{sym} {icon} {role}: <b>{pet_name}</b>{sp_part}"
            f" · Lv{lvl} · {_fatigue_icon(fat)} · 📦×{dups}"
        )
    return "\n".join(lines) + "\n"


# ── Theme Lab: кастомные raw-шаблоны премиум-тем (правки без деплоя) ───────────
# _build_template_ctx даёт полный словарь переменных для _safe_format.
# _DEFAULT_RAW_TEMPLATES — стартовый текст для textarea в дев-консоли
# (используется ТОЛЬКО для UI, не подставляется в рендер напрямую).

# Раньше матчились только латинские {var}. Theme Lab — текстовое поле, и
# пользователи интуитивно пишут русские имена ({ник}, {мора}, {дата и т.п.}) —
# расширяем до "что угодно без { } и переноса строк", чтобы такие плейсхолдеры
# тоже подставлялись (см. русские алиасы в _build_template_ctx), а не уходили
# в чат как «сырой» {var}.
_PLACEHOLDER_RE = re.compile(r"\{([^{}\n]+)\}")


def _safe_format(template: str, ctx: dict) -> str:
    """.format()-подобная подстановка, но не падает на «голых» { } в украшениях —
    заменяет только известные ключи {var}, остальное оставляет как есть."""
    return _PLACEHOLDER_RE.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), template)


_MULTI_SPACE_RE = re.compile(r" {2,}")


def _protect_spacing(text: str) -> str:
    """И Telegram (обычный HTML-текст), и CSS `white-space: pre-line` схлопывают
    подряд идущие пробелы в один — выравнивание ASCII-арта/рамок в премиум-темах
    ломается. Меняем каждый пробел в run из 2+ на NBSP ( ): он не
    схлопывается ни там, ни там, поэтому Theme Lab превью и реальное сообщение
    в Telegram совпадают 1:1."""
    return _MULTI_SPACE_RE.sub(lambda m: " " * len(m.group()), text)


def _build_template_ctx(*, user_id, name, nm, name_upper, g_rank, l_rank, lvl, pct, bar,
                         mora, dia, dark, zar, d, w, a, ach_count, warns, marr,
                         first_seen, last_seen, is_vip,
                         pets_passive, _pa, _pp, _pnm, _plv, _pfat, _pdup) -> dict:
    """Полный набор переменных, доступных в кастомных raw-шаблонах (все 14 премиум-тем)."""

    _hb_f = round(pct / 10)
    _8_f  = round(pct / 100 * 8)

    return {
        "user_id": user_id, "name_raw": name, "nm": nm, "name_upper": name_upper,
        "g_rank": g_rank, "l_rank": l_rank, "lvl": lvl, "pct": pct, "bar": bar,
        "mora": mora, "dia": dia, "dark": dark, "zar": zar,
        "d": d, "w": w, "a": a, "ach_count": ach_count, "warns": warns,
        "marr": marr or "нет", "marr_dash": marr or "—",
        "first_seen": first_seen, "last_seen": last_seen,

        "pet_a_name": _pnm(_pa), "pet_a_level": _plv(_pa),
        "pet_a_fatigue": _pfat(_pa), "pet_a_dups": _pdup(_pa),
        "pet_p_name": _pnm(_pp), "pet_p_level": _plv(_pp),
        "pet_p_fatigue": _pfat(_pp), "pet_p_dups": _pdup(_pp),

        "linux_vip_line": "[💎 VIP: АКТИВЕН]" if is_vip else "[VIP: неактивен]",
        "linux_pet1": (f"🦅 {_pnm(_pa)} [L{_plv(_pa)},{_pfat(_pa)},{_pdup(_pa)}дуб]" if _pa else "🦅 —"),
        "linux_pet2": (f"🐢 {_pnm(_pp)} [L{_plv(_pp)},{_pfat(_pp)},{_pdup(_pp)}дуб]" if _pp else "🐢 —"),

        "hardcore_shell_vip_line": "[💎 VIP: ACTIVATED]" if is_vip else "[VIP: OFFLINE]",
        "hardcore_shell_hb": "#" * _hb_f + "." * (10 - _hb_f),
        "hardcore_shell_l1": (f"PET_01: {_pnm(_pa)} | L:{_plv(_pa)}" if _pa else "PET_01: —"),
        "hardcore_shell_l2": (f"PET_02: {_pnm(_pp)} | L:{_plv(_pp)}" if _pp else "PET_02: —"),

        "starlight_p1": (f"{_pnm(_pa)} (v{_plv(_pa)})" if _pa else "—"),
        "starlight_p2": (f"{_pnm(_pp)} (v{_plv(_pp)})" if _pp else "—"),

        "order_p1": (f"{_pnm(_pa)} (L{_plv(_pa)})" if _pa else "—"),
        "order_p2": (f"{_pnm(_pp)} (L{_plv(_pp)})" if _pp else "—"),

        "prism_os_pb": "▒" * _8_f + "░" * (8 - _8_f),

        "empire_bar_el": "▆" * _8_f + "▃" * (8 - _8_f),

        # ── русские алиасы для Theme Lab (те же значения, что и выше) ───────────
        "ник": nm, "глобал_ранг": g_rank, "локал_ранг": l_rank, "уровень": lvl,
        "мора": mora, "алмазы": dia, "темная_мора": dark, "зарники": zar,
        "ачивки": ach_count, "дни": d, "недели": w, "всего": a,
        "брак_инфо": marr or "нет", "дата": first_seen, "id": user_id,
        "репутация": "+0",
        "питомец_актив": _pnm(_pa) if _pa else "—",
        "кол-во питомцев": len(pets_passive),
        "кол-во питомцев в пасиве": len(pets_passive),
    }


# Дефолтные шаблоны премиум-тем — единый источник для обычного рендера И для
# стартового/сбрасываемого текста в Theme Lab (см. _render_premium_impl).
_DEFAULT_RAW_TEMPLATES: dict[str, str] = {
    "linux": (
        "predvestnik@root:~/data#\n"
        "{linux_vip_line}\n"
        "👤 user: {ник}\n"
        "🌍 glob: {глобал_ранг}\n"
        "🏘 loc:  {локал_ранг}\n"
        "🔋 lvl: {уровень}\n"
        "  ↳ {bar} {pct}%\n\n"
        "&gt;_ [WALLET]\n"
        "🪙 mora: {мора}\n"
        "💎 dia:  {алмазы}\n"
        "🌑 dark: {темная_мора}\n"
        "✨ zar:  {зарники}\n\n"
        "&gt;_ [STATS]\n"
        "⚖️ rep: {репутация}\n"
        "🏆 ach: {ачивки}\n"
        "⚠️ warn: {warns}\n\n"
        "&gt;_ [ACTIVITY]\n"
        "💬 {дни}д/{недели}н\n"
        "  ↳ всего: {всего}\n"
        "📅 in: {дата}\n"
        "  ↳ out: {last_seen}\n"
        "💍 link: {брак_инфо}\n\n"
        "&gt;_ [PETS]\n"
        "{linux_pet1}\n"
        "{linux_pet2}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "[ID: {id}]\n"
        "predvestnik@root:~$ _"
    ),
    "hardcore_shell": (
        "┌──({ник} ㉿ pv2)\n"
        "└─$ whoami\n"
        "{hardcore_shell_vip_line}\n"
        "ID: {id}\n"
        "-----------------\n"
        "GRANK: {глобал_ранг}\n"
        "LRANK: {локал_ранг}\n"
        "LVL: {уровень} {pct}%\n"
        " ↳ [{hardcore_shell_hb}]\n"
        "-----------------\n"
        "CASH: {мора} 🪙\n"
        "CRYPT: {алмазы} 💎\n"
        "DARK: {темная_мора} 🌑\n"
        "ZARN: {зарники} ✨\n"
        "-----------------\n"
        "REP: {репутация}\n"
        "ACHV: {ачивки} 🏆\n"
        "WARN: {warns} ⚠️\n"
        "MSG: {дни}д/{недели}н\n"
        " ↳ TOTAL: {всего}\n"
        "-----------------\n"
        "SEEN: {дата}\n"
        " ↳ LAST: {last_seen}\n"
        "LINK: {marr_dash}\n"
        "-----------------\n"
        "{hardcore_shell_l1}\n"
        "{hardcore_shell_l2}\n"
        " ↳ RESERVE: {кол-во питомцев}\n"
        "-----------------\n"
        "$ ./run.sh --status\n"
        "# Система в норме."
    ),
    "starlight": (
        "⋆ ˚｡ 🌌 S T A R L I G H T ｡˚ ⋆\n\n"
        "┊ 🛸 Пилот: {ник}\n"
        "┊ 🪐 Сектор: {глобал_ранг}\n"
        "┊ 🛰 Узел: {локал_ранг}\n"
        "┊ 🌟 Фаза: {уровень}\n"
        "┊   ↳ {bar} {pct}%\n\n"
        "╰┈➤ ☄️ ГРУЗ\n"
        "  ⌑ 💫 Пыль: {мора}\n"
        "  ⌑ ☄️ Ядра: {алмазы}\n"
        "  ⌑ 🌑 Тьма: {темная_мора}\n"
        "  ⌑ ✨ Зар: {зарники}\n\n"
        "╰┈➤ 📊 РЕЙТИНГ\n"
        "  ⌑ ⚖️ Карма: {репутация}\n"
        "  ⌑ 🏆 Ачив: {ачивки}\n"
        "  ⌑ ⚠️ Тревог: {warns}\n\n"
        "╰┈➤ 📡 ЖУРНАЛ\n"
        "  ⌑ 📡 {дни}д|{недели}н\n"
        "    ↳ всего: {всего}\n"
        "  ⌑ 🛰 Старт: {дата}\n"
        "    ↳ Сигнал: {last_seen}\n\n"
        "╰┈➤ 🛸 ЭКИПАЖ\n"
        "  ⌑ 💞 Связь: {брак_инфо}\n"
        "  ⌑ 🦅 Дрон I: {starlight_p1}\n"
        "  ⌑ 🐢 Дрон II: {starlight_p2}\n"
        "    ↳ резерв: {кол-во питомцев}\n\n"
        "⋆ ˚｡ 🆔 {id} ｡˚ ⋆\n"
        "🌟 Каждая звезда — мечта…"
    ),
    "order": (
        "🍷 ✧ ── 🎭 ЛОЖА 🎭 ── ✧ 🍷\n\n"
        "◈ Мастер: {ник}\n"
        "◈ Совет: {глобал_ранг}\n"
        "◈ Ранг: {локал_ранг}\n"
        "◈ Степень {уровень}\n"
        " ↳ {bar} {pct}%\n\n"
        "♱ 🪙 ФОНД\n"
        " ▫️ 🪙: {мора}\n"
        " ▫️ 💎: {алмазы}\n"
        " ▫️ 🌑: {темная_мора}\n"
        " ▫️ ✨: {зарники}\n\n"
        "♱ ⚖️ РЕПУТАЦИЯ\n"
        " ▫️ Вес: {репутация}\n"
        " ▫️ 🏆: {ачивки}\n"
        " ▫️ ⚠️: {warns}\n\n"
        "♱ 💬 СЛУХИ\n"
        " ▫️ {дни}д|{недели}н\n"
        "  ↳ всего: {всего}\n"
        " ▫️ Вступил: {дата}\n"
        "  ↳ Замечен: {last_seen}\n\n"
        "♱ 💍 СОЮЗЫ\n"
        " ▫️ Связь: {брак_инфо}\n"
        " ▫️ Агент I: {order_p1}\n"
        " ▫️ Агент II: {order_p2}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "🍷 ✧ ── 🆔 {id}\n"
        "🟪 Видим то, что скрыто…"
    ),
    "prism_os": (
        "[ 🪞 P R I S M _ O S 🪞 ]\n\n"
        "≼ ID: {ник}\n"
        "≼ Сеть: {глобал_ранг}\n"
        "≼ Хост: {локал_ранг}\n"
        "≼ Заряд: {уровень}\n"
        "  ↳ {prism_os_pb} {pct}%\n\n"
        "░░░ [ДАМП ПАМЯТИ]\n"
        "~&gt; Фотоны: {мора}\n"
        "~&gt; Осколки: {алмазы}\n"
        "~&gt; Тень: {темная_мора}\n"
        "~&gt; Искры: {зарники}\n\n"
        "░░░ [РЕГИСТРЫ]\n"
        "~&gt; Резонанс: {репутация}\n"
        "~&gt; Ачив: {ачивки}\n"
        "~&gt; Ошибки: {warns}\n\n"
        "░░░ [ЛОГИ]\n"
        "~&gt; Сеанс: {дни}д/{недели}н\n"
        "  ↳ всего: {всего}\n"
        "~&gt; Аптайм: {дата}\n"
        "  ↳ выход: {last_seen}\n"
        "~&gt; Линк: {брак_инфо}\n\n"
        "░░░ [ПЕРИФЕРИЯ]\n"
        "~&gt; Юнит1: {pet_a_name}\n"
        "  ↳ &lt;v{pet_a_level}&gt; {pet_a_fatigue}\n"
        "~&gt; Юнит2: {pet_p_name}\n"
        "  ↳ &lt;v{pet_p_level}&gt; {pet_p_fatigue}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "[ 🆔 {id} ]\n"
        "💎 Свет находит путь сквозь кристалл…"
    ),
    "avangard": (
        "✧ ━━ 🕊️ АВАНГАРД 🕊️ ━━ ✧\n\n"
        "✦ {ник}\n"
        "✦ {глобал_ранг} / {локал_ранг}\n"
        "✦ Ранг {уровень}\n"
        "  ↳ {bar} {pct}%\n\n"
        "✧ ЭКОНОМИКА\n"
        " 🪙: {мора}\n"
        " 💎: {алмазы}\n"
        " 🌑: {темная_мора}\n"
        " ✨: {зарники}\n\n"
        "✧ ДОСТИЖЕНИЯ\n"
        " ⚖️ Реп: {репутация}\n"
        " 🏆 Ачив: {ачивки}\n"
        " ⚠️ Пред: {warns}\n"
        " 💬 {дни}д|{недели}н\n"
        "  ↳ всего: {всего}\n"
        " 📅 С нами: {дата}\n"
        "  ↳ Был: {last_seen}\n\n"
        "✧ СВИТА\n"
        " 💍 Узы: {брак_инфо}\n"
        " 🦅 {pet_a_name}\n"
        "  ↳ ур.{pet_a_level} {pet_a_fatigue}\n"
        " 🐢 {pet_p_name}\n"
        "  ↳ ур.{pet_p_level} {pet_p_fatigue}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "✧ ━━ 🆔 {id}\n"
        "☀️ Сияй, пока можешь…"
    ),
    "velvet": (
        "🟪 ═【 🌹 БАРХАТ 🌹 】═ 🟪\n\n"
        "👤 {ник}\n"
        "🌍 {глобал_ранг}\n"
        "🏠 {локал_ранг}\n"
        "🕯️ Покров {уровень}\n"
        "  ↳ {bar} {pct}%\n\n"
        "┄┄ 🧵 ЛАРЕЦ ┄┄\n"
        "🧵 Нити: {мора}\n"
        "🌹 Шёлк: {алмазы}\n"
        "🌑 Тень: {темная_мора}\n"
        "🔔 Звон: {зарники}\n"
        "🎭 Грация: {репутация}\n"
        "🏆 Слава: {ачивки}\n"
        "⚠️ Пятна: {warns}\n\n"
        "┄┄ 🤫 ШЁПОТЫ ┄┄\n"
        "{дни}д ⋅ {недели}н\n"
        "  ↳ всего: {всего}\n"
        "📅 {дата}\n"
        "  ↳ 🕓 {last_seen}\n"
        "💜 Узы: {брак_инфо}\n\n"
        "┄┄ 🌑 ТЕНИ ┄┄\n"
        "🥀 {pet_a_name}\n"
        "  ↳ ур.{pet_a_level} {pet_a_fatigue}\n"
        "🥀 {pet_p_name}\n"
        "  ↳ ур.{pet_p_level} {pet_p_fatigue}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "🟪 ID: {id}\n"
        "🟪 Бархат скрывает истинный характер…"
    ),
    "prism": (
        "✧ ═【 💎 ПРИЗМА 💎 】═ ✧\n\n"
        "👤 {ник}\n"
        "🌍 {глобал_ранг}\n"
        "🏠 {локал_ранг}\n"
        "🔆 Спектр {уровень}\n"
        "  ↳ {bar} {pct}%\n\n"
        "┄┄ 🌈 ГРАНИ ┄┄\n"
        "🌈 Лучи: {мора}\n"
        "💎 Грань: {алмазы}\n"
        "🌑 Тень: {темная_мора}\n"
        "✨ Искры: {зарники}\n"
        "🔅 Блеск: {репутация}\n"
        "🏆 Ачив: {ачивки}\n"
        "⚠️ Трещ: {warns}\n\n"
        "┄┄ ✨ ОТРАЖЕНИЯ ┄┄\n"
        "{дни}д ⋅ {недели}н\n"
        "  ↳ всего: {всего}\n"
        "📅 {дата}\n"
        "  ↳ 🕓 {last_seen}\n"
        "💞 Связь: {брак_инфо}\n\n"
        "┄┄ 🔮 СПУТНИКИ ┄┄\n"
        "🔹 {pet_a_name}\n"
        "  ↳ ур.{pet_a_level} {pet_a_fatigue}\n"
        "🔹 {pet_p_name}\n"
        "  ↳ ур.{pet_p_level} {pet_p_fatigue}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "✧ ID: {id}\n"
        "💎 Каждая грань — новый свет…"
    ),
    "celestial": (
        "꧁ ━━ ☀️ НЕБЕСНЫЙ ☀️ ━━ ꧂\n\n"
        "👤 {ник}\n"
        "🌍 {глобал_ранг}\n"
        "🏠 {локал_ранг}\n"
        "🕊️ Полёт {уровень}\n"
        "  ↳ {bar} {pct}%\n\n"
        "┄┄ ☀️ НЕБЕСА ┄┄\n"
        "☀️ Свет: {мора}\n"
        "🌙 Луна: {алмазы}\n"
        "🌑 Тень: {темная_мора}\n"
        "⭐ Звёзды: {зарники}\n"
        "😇 Святость: {репутация}\n"
        "🏆 Ачив: {ачивки}\n"
        "⚠️ Грех: {warns}\n\n"
        "┄┄ 🎶 ГИМНЫ ┄┄\n"
        "{дни}д ⋅ {недели}н\n"
        "  ↳ всего: {всего}\n"
        "📅 {дата}\n"
        "  ↳ 🕓 {last_seen}\n"
        "💞 Союз: {брак_инфо}\n\n"
        "┄┄ 👼 ХРАНИТЕЛИ ┄┄\n"
        "🕊️ {pet_a_name}\n"
        "  ↳ ур.{pet_a_level} {pet_a_fatigue}\n"
        "🕊️ {pet_p_name}\n"
        "  ↳ ур.{pet_p_level} {pet_p_fatigue}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "☀️ ID: {id}\n"
        "☀️ Небо для тех, кто смотрит ввысь…"
    ),
    "glass": (
        "💠 ═【 🕊️ ВИТРАЖ 🕊️ 】═ 💠\n\n"
        "👤 {ник}\n"
        "🌍 {глобал_ранг}\n"
        "🏠 {локал_ранг}\n"
        "🖼️ Картина {уровень}\n"
        "  ↳ {bar} {pct}%\n\n"
        "┄┄ 💠 ОСКОЛКИ ┄┄\n"
        "💠 Осколки: {мора}\n"
        "🔷 Грани: {алмазы}\n"
        "🌑 Тень: {темная_мора}\n"
        "✨ Блики: {зарники}\n"
        "🌈 Свет: {репутация}\n"
        "🏆 Ачив: {ачивки}\n"
        "⚠️ Трещ: {warns}\n\n"
        "┄┄ 🪞 ОТРАЖЕНИЯ ┄┄\n"
        "{дни}д ⋅ {недели}н\n"
        "  ↳ всего: {всего}\n"
        "📅 {дата}\n"
        "  ↳ 🕓 {last_seen}\n"
        "💞 Узор: {брак_инфо}\n\n"
        "┄┄ 🧩 ФРАГМЕНТЫ ┄┄\n"
        "🧩 {pet_a_name}\n"
        "  ↳ ур.{pet_a_level} {pet_a_fatigue}\n"
        "🧩 {pet_p_name}\n"
        "  ↳ ур.{pet_p_level} {pet_p_fatigue}\n"
        "  ↳ резерв: {кол-во питомцев}\n\n"
        "💠 ID: {id}\n"
        "💠 Каждый осколок — часть картины…"
    ),
    "gold": (
        "⚜️ ═【 🪙 АУРУМ 🪙 】═ ⚜️\n\n"
        "👤 {ник}\n"
        "🌍 {глобал_ранг}\n"
        "🏠 {локал_ранг}\n"
        "👑 Проба {уровень}\n"
        "  ↳ {bar} {pct}%\n\n"
        "┄┄ 🪙 ХРАНИЛИЩЕ ┄┄\n"
        "🪙 Слитки: {мора}\n"
        "💛 Самоцветы: {алмазы}\n"
        "🌑 Тень: {темная_мора}\n"
        "✨ Искры: {зарники}\n"
        "⚖️ Вес: {репутация}\n"
        "🏆 Ачив: {ачивки}\n"
        "⚠️ Скол: {warns}\n\n"
        "┄┄ 🔔 ЭХО ┄┄\n"
        "{дни}д ⋅ {недели}н\n"
        "  ↳ всего: {всего}\n"
        "📅 {дата}\n"
        "  ↳ 🕓 {last_seen}\n"
        "💞 Альянс: {брак_инфо}\n\n"
        "┄┄ 🦁 СОКРОВИЩА ┄┄\n"
        "🦁 {pet_a_name}\n"
        "  ↳ ур.{pet_a_level} {pet_a_fatigue}\n"
        "🦁 {pet_p_name}\n"
        "  ↳ ур.{pet_p_level} {pet_p_fatigue}\n"
        "  ↳ в кладовой: {кол-во питомцев}\n\n"
        "⚜️ ID: {id}\n"
        "💛 Золото молчит, но его слышат все…"
    ),
    "system_override": (
        "▼ 💻 ＳＹＳＴＥＭ_ＯＶＥＲＲＩＤＥ 💻 ▼\n\n"
        ">_ USER: {ник} 📟\n"
        ">_ AUTH: {глобал_ранг}\n"
        ">_ NODE: {локал_ранг}\n"
        ">_ SYNC: {уровень}\n"
        "  ↳ [{bar}] {pct}% ⚡\n\n"
        "► [ROOT/ASSETS]\n"
        "/// CRDT: {мора} 🔌\n"
        "/// CRYPT: {алмазы} 🌐\n"
        "/// DARK: {темная_мора} 🌑\n"
        "/// ZARN: {зарники} ⚡\n\n"
        "► [ROOT/STATUS]\n"
        "/// REP: {репутация} ⚙️\n"
        "/// ACHV: {ачивки} 🔓\n"
        "/// ERR: {warns} ⚠️\n\n"
        "► [ROOT/LOG]\n"
        "/// MSG: {дни}д|{недели}н 📊\n"
        "  ↳ all: {всего} 🕹️\n"
        "/// SEEN: init {дата}\n"
        "  ↳ last {last_seen}\n"
        "/// LINK: {брак_инфо} 💟\n\n"
        "► [ROOT/ENTITIES]\n"
        "[*] PORT_01: {pet_a_name}\n"
        "  ↳ [v{pet_a_level}.0] {pet_a_fatigue}\n"
        "[*] PORT_02: {pet_p_name}\n"
        "  ↳ [v{pet_p_level}.0] {pet_p_fatigue}\n"
        "  ↳ standby: {кол-во питомцев}\n\n"
        "▲ ID: {id} ▲\n"
        "«Проснись, Нео. Ты всё ещё в чате…» ▮ 🟢"
    ),
    "wind_free": (
        "【 🎐 ‧̍̊˙· ВЕТЕР СВОБОДЫ ·˙‧̍̊ 🎐 】\n\n"
        "👤 {name_upper} 🪽\n"
        "🌍 {глобал_ранг}\n"
        "🏘 {локал_ранг}\n"
        "╰┈➤ 🌬️ Ур.{уровень} [{bar}] {pct}% ✨\n\n"
        "▽ 【 ЗАСЛУГИ 】\n"
        "🪙 Монет: {мора}\n"
        "💎 Кристаллов: {алмазы}\n"
        "🌑 Тьмы: {темная_мора}\n"
        "✨ Звёзд: {зарники}\n"
        "🪷 Кармы: {репутация}\n"
        "📜 Ачивок: {ачивки}\n"
        "⚠️ Штрафов: {warns}\n\n"
        "▽ 【 АКТИВНОСТЬ 】\n"
        "🍃 {дни}д | ✉️ {недели}н\n"
        "╰┈➤ всего: {всего} 🌐\n"
        "📅 С нами: {дата} 🍃\n"
        "╰┈➤ Был: {last_seen}\n"
        "💞 Узы: {брак_инфо}\n\n"
        "▽ 【 СПУТНИКИ И ОТРЯД 】\n"
        "🐾 Слот I: {pet_a_name}\n"
        "╰┈➤ Ранг {pet_a_level} {pet_a_fatigue} 🔥\n"
        "🐾 Слот II: {pet_p_name}\n"
        "╰┈➤ Ранг {pet_p_level} {pet_p_fatigue} 🌙\n"
        "╰┈➤ в отряде: {кол-во питомцев}\n\n"
        "【 🎐 ID: {id} 】\n"
        "«Разве не прекрасно, когда ветер сам выбирает путь?» 🍃"
    ),
    "empire": (
        "⊱⟡━━꧁༺ ♕ ༻꧂━━⟡⊰\n"
        "┊꧁𓊈𒆜 ИМПЕРИЯ 𒆜𓊉꧂┊\n"
        "⊱⟡━━꧁༺ ♕ ༻꧂━━⟡⊰\n"
        "\n"
        "⊱⟡━𓊈👤ПРОФИЛЬ𓊉━⟡⊰\n"
        "┊ ⚜️ Имя: {ник}\n"
        "┊ ⚜️ Звание: {глобал_ранг}\n"
        "┊ ⚜️ Чин: {локал_ранг}\n"
        "┊ ⚜️ Ур.{уровень} {empire_bar_el}\n"
        "⊱⟡━━━━━━━━━━━━━⟡⊰\n"
        "\n"
        "⊱⟡━𓊈💎АКТИВЫ𓊉━⟡⊰\n"
        "┊ 🪙 {мора} | 💎 {алмазы}\n"
        "┊ 🌑 {темная_мора} | ✨ {зарники}\n"
        "┊ ⚖️ {репутация} | 🏆 {ачивки}\n"
        "⊱⟡━━━━━━━━━━━━━⟡⊰\n"
        "\n"
        "⊱⟡━𓊈🏰ПРИЁМЫ𓊉━⟡⊰\n"
        "┊ ⚜️ В замке: {дни}д | {недели}н\n"
        "┊ ⚜️ Династия: {брак_инфо}\n"
        "┊ ⚜️ При дворе с: {дата}\n"
        "┊ ⚜️ Послед. визит: {last_seen}\n"
        "⊱⟡━━━━━━━━━━━━━⟡⊰\n"
        "\n"
        "⊱⟡━𓊈🐾СВИТА𓊉━⟡⊰\n"
        "┊ 🦊 Актив: {pet_a_name}\n"
        "┊ 🐺 В запасе: {кол-во питомцев}\n"
        "⊱⟡━━━━━━━━━━━━━⟡⊰\n"
        "\n"
        "꧁𓊈𒆜 ID:{id} 𒆜𓊉꧂\n"
        "\n"
        "«У роскоши нет предела, есть только цена…» ✨"
    ),
}


def _default_raw_text_for_basic_theme(theme: dict) -> str:
    """Стартовый raw-текст для ОБЫЧНОЙ (не премиум) темы — собран из её
    top/sep/bot/accent/side/prefix + переменных _build_template_ctx, чтобы
    редактирование в Theme Lab начиналось с вида, максимально близкого
    к текущему стандартному профилю."""
    top    = theme.get("top", "")
    sep    = theme.get("sep", "─" * 8)
    bot    = theme.get("bot", "")
    accent = theme.get("accent", "")
    side   = theme.get("side", "")
    P      = theme.get("prefix", "")

    if side:
        name_block = (
            f"{P}{side} {accent} <b>{{ник}}</b> {accent}\n"
            f"{P}{side} 🌍 {{глобал_ранг}}  |  🏘 {{локал_ранг}}\n"
        )
    else:
        name_block = (
            f"{P}{accent} <b>{{ник}}</b>\n"
            f"{P}🌍 {{глобал_ранг}}  |  🏘 {{локал_ранг}}\n"
        )

    return (
        (f"{top}\n" if top else "")
        + name_block
        + f"{P}📅 В чате с: {{дата}}\n"
        + f"\n{P}{sep}\n\n"
        + f"{P}🌟 Ур.<b>{{уровень}}</b>  [{{bar}}] {{pct}}%\n"
        + f"{P}🪙 {{мора}}  |  💎 {{алмазы}}  |  🌑 {{темная_мора}}  |  ✨ {{зарники}}\n"
        + f"{P}🏆 {{ачивки}} ачив.  |  ⚖️ Реп: {{репутация}}  |  ⚠️ Варны: {{warns}}\n"
        + f"\n{P}{sep}\n\n"
        + f"{P}💬 {{дни}}д | {{недели}}н | {{всего}}всего\n"
        + f"{P}🕓 Последнее появление: {{last_seen}}\n"
        + f"{P}💍 Брак: {{брак_инфо}}\n"
        + f"\n{P}{sep}\n\n"
        + f"{P}🐾 Актив: {{pet_a_name}} (ур.{{pet_a_level}})\n"
        + f"{P}💤 Пассив: {{pet_p_name}} (ур.{{pet_p_level}})\n"
        + f"\n{P}🆔 <code>{{id}}</code>\n"
        + (bot if bot else "")
    )


def get_default_raw_template(template_id: str) -> str | None:
    """Стартовый raw-текст для Theme Lab (или None, если шаблон неизвестен)."""
    if template_id in _DEFAULT_RAW_TEMPLATES:
        return _DEFAULT_RAW_TEMPLATES[template_id]
    from core.themes import THEMES
    theme = THEMES.get(template_id)
    if theme and not theme.get("premium_template"):
        return _default_raw_text_for_basic_theme(theme)
    return None


def get_template_variables(template_id: str) -> list[str]:
    """Список переменных {var}, доступных в этом шаблоне (подсказка в Theme Lab)."""
    default = get_default_raw_template(template_id) or ""
    return sorted(set(_PLACEHOLDER_RE.findall(default)))


def _render_premium(template_id: str, user_id: int, name: str,
                    g_rank: str, l_rank: str, lvl: int, pct: int,
                    mora_v, dia_v, d_msgs, w_msgs, a_msgs,
                    streak, ach_count, warns, marriage, nursery_pets,
                    partner_display: str | None = None,
                    dark_v=0, zar_v=0, is_vip: bool = False,
                    first_seen: str = "—", last_seen: str = "—",
                    override_raw_text: str | None = None,
                    title: str | None = None) -> str | None:
    text = _render_premium_impl(
        template_id, user_id, name, g_rank, l_rank, lvl, pct,
        mora_v, dia_v, d_msgs, w_msgs, a_msgs,
        streak, ach_count, warns, marriage, nursery_pets,
        partner_display, dark_v, zar_v, is_vip, first_seen, last_seen,
        override_raw_text=override_raw_text, title=title,
    )
    return _protect_spacing(text) if text else text


def _render_premium_impl(template_id: str, user_id: int, name: str,
                    g_rank: str, l_rank: str, lvl: int, pct: int,
                    mora_v, dia_v, d_msgs, w_msgs, a_msgs,
                    streak, ach_count, warns, marriage, nursery_pets,
                    partner_display: str | None = None,
                    dark_v=0, zar_v=0, is_vip: bool = False,
                    first_seen: str = "—", last_seen: str = "—",
                    override_raw_text: str | None = None,
                    title: str | None = None) -> str | None:
    bar  = _premium_bar(pct)
    mora = _compact(mora_v)
    dia  = _compact(dia_v)
    dark = _compact(dark_v)
    zar  = _compact(zar_v)
    d, w, a = _compact(d_msgs), _compact(w_msgs), _compact(a_msgs)
    name_upper = name.upper()
    nm = safe_html(name)   # имя экранируется — иначе спецсимволы (< > &) ломают весь профиль

    if marriage:
        dur  = _marriage_duration(marriage.get("marriage_date"))
        partner_raw = f"{partner_display} ({dur})"
    else:
        partner_raw = None
    marr = partner_raw if partner_raw else None

    pets_active  = [p for p in nursery_pets if p.get("placement") == "active"]
    pets_passive = [p for p in nursery_pets if p.get("placement") == "passive"]

    # ── Хелперы вывода питомца для новых премиум-тем (активный=🦅, пассивный=🐢) ──
    _pa = pets_active[0] if pets_active else None
    _pp = pets_passive[0] if pets_passive else None
    def _pnm(p): return safe_html(p["name"]) if p else "—"
    def _plv(p): return (p.get("pet_level", 1) or 1) if p else 0
    def _pdup(p): return (p.get("duplicates_collected", 0) or 0) if p else 0
    def _pfat(p): return _fatigue_icon(p.get("fatigue", 0)) if p else "⚪"

    # ── Единый шаблонный движок: override из Theme Lab или дефолт темы ───────
    ctx = _build_template_ctx(
        user_id=user_id, name=name, nm=nm, name_upper=name_upper, g_rank=g_rank, l_rank=l_rank,
        lvl=lvl, pct=pct, bar=bar, mora=mora, dia=dia, dark=dark, zar=zar,
        d=d, w=w, a=a, ach_count=ach_count, warns=warns, marr=marr,
        first_seen=first_seen, last_seen=last_seen, is_vip=is_vip,
        pets_passive=pets_passive,
        _pa=_pa, _pp=_pp, _pnm=_pnm, _plv=_plv, _pfat=_pfat, _pdup=_pdup,
    )
    ctx["титул"] = title or ""   # косметический титул (опц., для премиум/Theme Lab)
    ctx["title"] = title or ""
    tpl = override_raw_text or _DEFAULT_RAW_TEMPLATES.get(template_id)
    if tpl is None:
        return None
    return _safe_format(tpl, ctx)


# ── main render function ───────────────────────────────────────────────────────

async def build_profile_text(
    db,
    user_id: int,
    chat_id: int,
    theme_id_override: str | None = None,
    developer_id: int = 0,
    raw_template_override: str | None = None,
) -> str:
    """
    Generate the exact same HTML string that the bot sends to Telegram.
    Works for both standard and premium themes.
    The result is valid for Telegram HTML parse_mode AND browser innerHTML.

    raw_template_override: Theme Lab dry-run — render with this raw text
    instead of the saved DB override (not persisted, used for /preview).
    """
    from infrastructure.repositories import economy as eco_repo
    from infrastructure.repositories import dark_mora as dark_mora_repo
    from infrastructure.repositories import chat as chat_repo
    from infrastructure.repositories import users as users_repo
    from infrastructure.repositories import zoo as zoo_db
    from infrastructure.repositories import marriages as marriage_repo
    from infrastructure.repositories import achievements as ach_repo
    from infrastructure.repositories.streak import get_streak
    from infrastructure.repositories.themes import get_active_theme
    from infrastructure.repositories import theme_templates as theme_tpl_repo
    from services.vip import is_vip_active

    # Fetch data
    name           = await resolve_display_name(db, user_id, chat_id, f"user_{user_id}")
    bal            = await eco_repo.get_balance(db, user_id)
    dark_mora      = await dark_mora_repo.get_dark_mora_balance(db, user_id)
    stats          = await chat_repo.get_chat_stats(db, user_id, chat_id)
    global_rank_id = await users_repo.get_global_rank(db, user_id)
    first_seen_raw = await users_repo.get_first_seen(db, user_id)
    nursery_pets   = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    streak_row     = await get_streak(db, user_id, chat_id)
    marriage       = await marriage_repo.get_user_marriage(db, user_id)
    hamster_inc    = await zoo_db.get_pending_hamster_income(db, user_id)
    ach_count      = await ach_repo.get_user_achievements_count(db, user_id)
    is_vip         = await is_vip_active(db, user_id)

    from services.cosmetics import get_active_cosmetics
    title = (await get_active_cosmetics(db, user_id)).get("title")

    theme_id = theme_id_override or await get_active_theme(db, user_id)
    theme    = _load_theme(theme_id)

    t_top      = theme.get("top", "")
    t_sep      = theme.get("sep", "─" * 8)
    t_bot      = theme.get("bot", "")
    t_accent   = theme.get("accent", "")
    t_side     = theme.get("side", "")
    t_prefix   = theme.get("prefix", "")
    t_id_in_bot= theme.get("id_in_bot", False)
    t_name     = theme.get("name", "?")
    P          = t_prefix

    g_rank = roles.get_global_rank_name(user_id, global_rank_id, developer_id=developer_id)
    l_rank = roles.get_local_rank_name(user_id, stats.get("local_rank", 0), developer_id=developer_id)

    lvl       = stats.get("user_level", 1)
    xp        = stats.get("user_xp", 0)
    xp_in_lvl = xp % XP_PER_LEVEL
    bar       = _xp_bar(xp_in_lvl, XP_PER_LEVEL)
    pct       = _xp_pct(xp_in_lvl, XP_PER_LEVEL)
    xp_str    = f"({_compact(xp_in_lvl)}/{_compact(XP_PER_LEVEL)})"

    mora_v = float(bal["user_balance_mora"])
    dia_v  = float(bal["user_balance_diamonds"])
    zar_v  = float(bal.get("user_balance_zarniki", 0))
    dark_v = float(dark_mora)
    ham_note = f" +{_compact(hamster_inc)}🐹" if hamster_inc > 0 else ""

    def _fmt_exact(n: float) -> str:
        return f"{int(n):,}".replace(",", " ")

    _bal1 = f"💰 {_fmt_exact(mora_v)} 🪙  |  💎 {dia_v:.1f}{ham_note}"
    _bal2 = f"🌑 {_fmt_exact(dark_v)} Тёмная  |  ✨ {zar_v:.0f} Зарники"

    streak = streak_row.get("streak", 0)
    d_msgs = stats.get("user_messages_count_per_day", 0)
    w_msgs = stats.get("user_messages_count_per_week", 0)
    a_msgs = stats.get("user_messages_count_all_time", 0)
    warns  = stats.get("warnings", 0)

    is_immune    = stats.get("is_immune", False)
    immune_until = stats.get("immune_until")
    if is_immune:
        shield_line = "🛡 Абс. иммунитет"
    elif immune_until:
        dt = parse_dt(immune_until)
        shield_line = f"🛡 до {dt.strftime('%d.%m %H:%M')}" if dt and dt > datetime.now() else ""
    else:
        shield_line = ""

    partner_display = None
    if marriage:
        partner_id = marriage["user2_id"] if marriage["user1_id"] == user_id else marriage["user1_id"]
        p_nm = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        partner_display = await resolve_display_name(db, partner_id, chat_id, p_nm)
        dur  = _marriage_duration(marriage.get("marriage_date"))
        partner_line = f"💍 Брак: {partner_display} ({dur})"
    else:
        partner_line = "💍 Не в браке"

    join_str = "—"
    if first_seen_raw:
        dt = parse_dt(first_seen_raw)
        if dt:
            join_str = dt.strftime("%d.%m.%Y")

    # Последнее появление — последняя активность в этом чате
    last_str = "—"
    last_seen_raw = stats.get("last_message_at")
    if last_seen_raw:
        dt = parse_dt(last_seen_raw)
        if dt:
            last_str = dt.strftime("%d.%m %H:%M")

    # Premium-шаблон ИЛИ Theme Lab raw_text-оверрайд для обычной темы (ключ — theme_id)
    premium_tpl = theme.get("premium_template")
    tpl_key = premium_tpl or theme_id
    if raw_template_override is not None:
        override_raw = raw_template_override
    else:
        override_raw = await theme_tpl_repo.get_override(db, tpl_key)
    if premium_tpl or override_raw:
        result = _render_premium(
            tpl_key, user_id, name, g_rank, l_rank, lvl, pct,
            mora_v, dia_v, d_msgs, w_msgs, a_msgs,
            streak, ach_count, warns, marriage, nursery_pets,
            partner_display, dark_v, zar_v, is_vip, join_str, last_str,
            override_raw_text=override_raw, title=title,
        )
        if result:
            return result

    # Standard / zarniki render
    if t_side:
        name_block = (
            f"{P}{t_side} {t_accent} <b>{name}</b> {t_accent}\n"
            f"{P}{t_side} 🌍 {g_rank}  |  🏘 {l_rank}\n"
            f"{P}{t_side} 📅 В чате с: {join_str}\n"
        )
    else:
        name_block = (
            f"{P}{t_accent} <b>{name}</b>\n"
            f"{P}🌍 {g_rank}  |  🏘 {l_rank}\n"
            f"{P}📅 В чате с: {join_str}\n"
        )

    pets_str = _pets_block(nursery_pets, P)

    if t_id_in_bot:
        tail = f"{t_sep}\n" + t_bot.replace("{id}", str(user_id))
    else:
        tail = f"{t_sep}\n{P}🆔 <code>{user_id}</code>\n{t_bot}"

    if t_prefix:
        return (
            f"{t_top}\n"
            + name_block
            + (f"{P}🏷 <i>{safe_html(title)}</i>\n" if title else "")
            + f"\n"
            + f"{t_sep}\n\n"
            + f"{P}🌟 Ур.<b>{lvl}</b>  [{bar}] {pct}% {xp_str}\n"
            + f"{P}{_bal1}\n"
            + f"{P}{_bal2}\n"
            + f"{P}🏆 {ach_count} ачив.  |  ⚖️ Реп: +0  |  ⚠️ Варны: {warns}\n"
            + (f"{P}🔥 Стрик: <b>{streak}</b> дн.\n" if streak else "")
            + f"\n{t_sep}\n\n"
            + f"{P}{partner_line}\n"
            + (f"{P}{shield_line}\n" if shield_line else "")
            + f"{P}🎨 Тема: {t_name}\n"
            + f"{P}💬 {d_msgs} д  |  {w_msgs} н  |  {a_msgs} всего\n"
            + f"{P}🕓 Последнее появление: {last_str}\n"
            + f"\n{P}🐾 <b>Питомцы:</b>\n"
            + pets_str + tail
        )
    else:
        return (
            f"{t_top}\n"
            + name_block
            + (f"🏷 <i>{safe_html(title)}</i>\n" if title else "")
            + f"\n"
            + f"{t_sep}\n\n"
            + f"🌟 Ур.<b>{lvl}</b>  [{bar}] {pct}% {xp_str}\n"
            + f"{_bal1}\n"
            + f"{_bal2}\n"
            + f"🏆 {ach_count} ачив.  |  ⚖️ Реп: +0  |  ⚠️ Варны: {warns}\n"
            + f"🔥 Стрик: <b>{streak}</b> дн.\n\n"
            + f"{t_sep}\n\n"
            + f"💬 {d_msgs} д  |  {w_msgs} н  |  {a_msgs} всего\n"
            + f"🕓 Последнее появление: {last_str}\n"
            + f"{partner_line}\n"
            + (f"{shield_line}\n" if shield_line else "")
            + f"🎨 Тема: {t_name}\n\n"
            + f"{t_sep}\n\n"
            + f"🐾 <b>Питомцы:</b>\n"
            + pets_str + tail
        )
