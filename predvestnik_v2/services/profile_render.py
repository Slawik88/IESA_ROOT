"""
services/profile_render.py
Pure profile rendering — no bot/aiogram imports.
Used by both bot/handlers/identity.py and FastAPI/routers/themes.py.

Returns HTML string compatible with both Telegram's HTML parse_mode
AND browser innerHTML (same tag subset: <b>, <i>, <code>, <a>).
"""
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


def _render_premium(template_id: str, user_id: int, name: str,
                    g_rank: str, l_rank: str, lvl: int, pct: int,
                    mora_v, dia_v, d_msgs, w_msgs, a_msgs,
                    streak, ach_count, warns, marriage, nursery_pets,
                    partner_display: str | None = None,
                    dark_v=0, zar_v=0, is_vip: bool = False,
                    first_seen: str = "—", last_seen: str = "—") -> str | None:
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

    # 1. 🐧 LINUX (Kernel Shell)
    if template_id == "linux":
        vip_line = "[💎 VIP: АКТИВЕН]" if is_vip else "[VIP: неактивен]"
        pet1 = f"🦅 {_pnm(_pa)} [L{_plv(_pa)},{_pfat(_pa)},{_pdup(_pa)}дуб]" if _pa else "🦅 —"
        pet2 = f"🐢 {_pnm(_pp)} [L{_plv(_pp)},{_pfat(_pp)},{_pdup(_pp)}дуб]" if _pp else "🐢 —"
        return (
            f"predvestnik@root:~/user/data#\n"
            f"{vip_line}\n"
            f"👤 Юзер: <b>{nm}</b>\n"
            f"🌍 Глобал: {g_rank}\n"
            f"🏘 Локал: {l_rank}\n"
            f"🔋 Ядро: Ур.<b>{lvl}</b> {bar} <b>{pct}%</b>\n\n"
            f"&gt;_ [FS_RESOURCES]\n"
            f"🪙 Мора: {mora} | 💎 Алм: {dia}\n"
            f"🌑 ТМ: {dark} | ✨ Зар: {zar}\n"
            f"⚖️ Реп: 0 | 🏆 Ачив: {ach_count} | ⚠️: {warns}\n\n"
            f"&gt;_ [LOG_ACTIVITY]\n"
            f"💬 {d}д | {w}н | {a}всего\n"
            f"📅 init: {first_seen} | 🕓 last: {last_seen}\n"
            f"💍 Узы: {marr or 'нет'}\n\n"
            f"&gt;_ [ENTITIES_LOADER]\n"
            f"{pet1}\n{pet2}\n\n"
            f"[ID: <code>{user_id}</code>]\n"
            f"predvestnik@root:~/exit$ _"
        )

    # 2. 🖥️ HARDCORE SHELL (Bash Profile)
    if template_id == "hardcore_shell":
        _f = round(pct / 10)
        hb = "#" * _f + "." * (10 - _f)
        vip_line = "[💎 VIP: ACTIVATED]" if is_vip else "[VIP: OFFLINE]"
        l1 = f"PET_01: {_pnm(_pa)} | L:{_plv(_pa)}" if _pa else "PET_01: —"
        l2 = f"PET_02: {_pnm(_pp)} | L:{_plv(_pp)}" if _pp else "PET_02: —"
        return (
            f"┌──(<b>{nm}</b> ㉿ predvestnik)\n"
            f"└─$ cat profile.conf\n"
            f"{vip_line}\n"
            f"ID: <code>{user_id}</code>\n"
            f"LEVEL: {lvl} [{hb}] {pct}%\n"
            f"REP: 0 | ACHV: {ach_count}\n"
            f"---------------------------\n"
            f"CASH: {mora} 🪙 | CRYPT: {dia} 💎\n"
            f"DARK_M: {dark} 🌑 | ZARN: {zar} ✨\n"
            f"FIRST_SEEN: {first_seen} | LAST_SEEN: {last_seen}\n"
            f"---------------------------\n"
            f"LINK: {marr or '—'}\n"
            f"{l1}\n{l2}\n"
            f"---------------------------\n"
            f"$ ./run_predvestnik.sh\n"
            f"<i># \"Система работает. Идеально.\"</i>"
        )

    # 3. 🌌 STARLIGHT
    if template_id == "starlight":
        p1 = f"{_pnm(_pa)} (v{_plv(_pa)})" if _pa else "—"
        p2 = f"{_pnm(_pp)} (v{_plv(_pp)})" if _pp else "—"
        return (
            f"⋆ ˚｡ 🌌 S T A R L I G H T ｡˚ ⋆\n\n"
            f"┊ 🛸 Пилот: <b>{nm}</b>\n"
            f"┊ 🪐 Сектор: {g_rank}\n"
            f"┊ 🛰 Узел: {l_rank}\n"
            f"┊ 🌟 Фаза: <b>{lvl}</b> {bar} <b>{pct}%</b>\n\n"
            f"╰┈➤ ☄️ БОРТОВЫЕ ДАННЫЕ\n"
            f"  ⌑ 💫 Пыль: {mora} | ☄️ Ядра: {dia}\n"
            f"  ⌑ ⚖️ Карма: +0 | 🏆 Ачив: {ach_count}\n"
            f"  ⌑ 📡 Пинг: {d}д|{w}н|{a}вс\n"
            f"  ⌑ 🛰 Старт: {first_seen} | Сигнал: {last_seen}\n\n"
            f"╰┈➤ 🛸 ЭКИПАЖ\n"
            f"  ⌑ 💞 Связь: {marr or 'нет'}\n"
            f"  ⌑ 🦅 Дрон I: {p1}\n"
            f"  ⌑ 🐢 Дрон II: {p2}\n\n"
            f"⋆ ˚｡ 🆔 <code>{user_id}</code> ｡˚ ⋆\n"
            f"🌟 Каждая звезда — чья-то мечта…"
        )

    # 4. 🎭 Закрытый Орден (Ложа)
    if template_id == "order":
        p1 = f"{_pnm(_pa)} (L{_plv(_pa)})" if _pa else "—"
        p2 = f"{_pnm(_pp)} (L{_plv(_pp)})" if _pp else "—"
        return (
            f"🍷 ✧ ── 🎭 Л О Ж А 🎭 ── ✧ 🍷\n\n"
            f"◈ Мастер: <b>{nm}</b>\n"
            f"◈ Совет: {g_rank}\n"
            f"◈ Ранг: {l_rank}\n"
            f"◈ Ранг <b>{lvl}</b> {bar} <b>{pct}%</b>\n\n"
            f"♱ 🪙 ФОНД ОРДЕНА\n"
            f" ▫️ 🪙: {mora} | 💎: {dia} | 🌑: {dark} | ✨: {zar}\n"
            f" ▫️ ⚖️: 0 | 🏆: {ach_count} | ⚠️: {warns}\n\n"
            f"♱ 💬 СЛУХИ\n"
            f" ▫️ {d}д | {w}н | {a}всего\n"
            f" ▫️ Вступил: {first_seen} | Замечен: {last_seen}\n\n"
            f"♱ 💍 СОЮЗЫ\n"
            f" ▫️ Связь: {marr or 'нет'}\n"
            f" ▫️ Агент I: {p1}\n"
            f" ▫️ Агент II: {p2}\n\n"
            f"🍷 ✧ ── 🆔 <code>{user_id}</code>\n"
            f"🟪 Мы видим то, что скрыто…"
        )

    # 5. 💠 PRISM OS
    if template_id == "prism_os":
        _f2 = round(pct / 100 * 8)
        pb = "▒" * _f2 + "░" * (8 - _f2)
        p1 = f"{_pnm(_pa)} &lt;v{_plv(_pa)}&gt;" if _pa else "—"
        p2 = f"{_pnm(_pp)} &lt;v{_plv(_pp)}&gt;" if _pp else "—"
        return (
            f"[ 🪞 P R I S M _ O S 🪞 ]\n\n"
            f"≼ 💠 ID: <b>{nm}</b>\n"
            f"≼ 🌐 Сеть: {g_rank}\n"
            f"≼ 🪩 Хост: {l_rank}\n"
            f"≼ 🔋 Заряд: Ур.<b>{lvl}</b> {pb} <b>{pct}%</b>\n\n"
            f"░░░ [ ДАМП ПАМЯТИ ]\n"
            f"~&gt; ☀️ Фотоны: {mora}\n"
            f"~&gt; 💠 Осколки: {dia}\n"
            f"~&gt; 🌈 Резонанс: 0 | 🏆: {ach_count}\n"
            f"~&gt; 🔊 Сеанс: {d}д/{w}н/{a}вс\n"
            f"~&gt; 🕓 Аптайм: {first_seen} → {last_seen}\n\n"
            f"░░░ [ ПЕРИФЕРИЯ ]\n"
            f"~&gt; 🔗 Линк: {marr or 'нет'}\n"
            f"~&gt; ⚡ Юнит 1: {p1}\n"
            f"~&gt; 🌟 Юнит 2: {p2}\n\n"
            f"[ 🆔 <code>{user_id}</code> ]\n"
            f"💎 Свет находит путь сквозь кристалл…"
        )

    # 6. 🕊️ Астральный свет (Авангард)
    if template_id == "avangard":
        p1 = f"🦅 {_pnm(_pa)} [L{_plv(_pa)}, {_pfat(_pa)}, {_pdup(_pa)}дуб]" if _pa else "🦅 —"
        p2 = f"🐢 {_pnm(_pp)} [L{_plv(_pp)}, {_pfat(_pp)}, {_pdup(_pp)}дуб]" if _pp else "🐢 —"
        return (
            f"✧ ━━ 🕊️ АВАНГАРД 🕊️ ━━ ✧\n\n"
            f"✦ <b>{nm}</b>\n"
            f"✦ {g_rank} / {l_rank}\n"
            f"✦ Ур.<b>{lvl}</b> {bar} <b>{pct}%</b>\n\n"
            f"✧ ЭКОНОМИКА\n"
            f" 🪙: {mora} | 💎: {dia} | 🌑: {dark} | ✨: {zar}\n\n"
            f"✧ ДОСТИЖЕНИЯ\n"
            f" ⚖️ Реп: 0 | 🏆 Ачив: {ach_count} | ⚠️: {warns}\n"
            f" 💬 {d}д | {w}н | {a}всего\n"
            f" 📅 С нами: {first_seen} | Был: {last_seen}\n\n"
            f"✧ СВИТА\n"
            f" 💍 Узы: {marr or 'нет'}\n"
            f" {p1}\n {p2}\n\n"
            f"✧ ━━ 🆔 <code>{user_id}</code>\n"
            f"☀️ Сияй, пока можешь…"
        )

    # ── Декоративные премиум-темы (перенесены из bot/handlers/identity.py —
    #    единый источник правды для бота и веб-превью) ──────────────────────────
    if template_id == "starlight_classic":  # старый стиль больше не используется
        return None

    if template_id == "velvet":
        pet_lines = (f"💜 Узы: {partner_raw}\n" if marriage else "")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv = p.get("pet_level", 1) or 1
            pet_lines += f"🥀 {safe_html(p['name'])} ({sp}) ур.{lv}\n"
        return (
            f"🟪 ═【 🌹 БАРХАТ 🌹 】═ 🟪\n\n"
            f"👤 <b>{nm}</b>\n🌍 {g_rank}\n🏠 {l_rank}\n"
            f"🕯️ Покров {lvl} [{bar}] {pct}%\n\n"
            f"┄┄ 🧵 ЛАРЕЦ ┄┄\n"
            f"🧵 Нити: {mora} ⋅ 🌹 {dia}\n"
            f"🎭 Грация: +0 ⋅ 🏆 {ach_count}\n\n"
            f"┄┄ 🤫 ШЁПОТЫ ┄┄\n"
            f"{d}/д ⋅ {w}/н ⋅ {a}/всё\n"
            f"📅 {first_seen} ⋅ 🕓 {last_seen}\n\n"
            f"┄┄ 🌑 ТЕНИ ┄┄\n"
            f"{pet_lines or '🕸️ Пустота…' + chr(10)}"
            f"\n🟪 ID: <code>{user_id}</code>\n"
            f"<i>🟪 Бархат скрывает истинный характер…</i>"
        )

    if template_id == "prism":
        pet_lines = (f"💞 Связь: {partner_raw}\n" if marriage else "")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv = p.get("pet_level", 1) or 1
            pet_lines += f"🔹 {safe_html(p['name'])} ({sp}) ур.{lv}\n"
        return (
            f"✧ ═【 💎 ПРИЗМА 💎 】═ ✧\n\n"
            f"👤 <b>{nm}</b>\n🌍 {g_rank}\n🏠 {l_rank}\n"
            f"🔆 Спектр {lvl} [{bar}] {pct}%\n\n"
            f"┄┄ 🌈 ГРАНИ ┄┄\n"
            f"🌈 Лучи: {mora} ⋅ 💎 {dia}\n"
            f"🔅 Блеск: +0 ⋅ 🏆 {ach_count}\n\n"
            f"┄┄ ✨ ОТРАЖЕНИЯ ┄┄\n"
            f"{d}/д ⋅ {w}/н ⋅ {a}/всё\n"
            f"📅 {first_seen} ⋅ 🕓 {last_seen}\n\n"
            f"┄┄ 🔮 СПУТНИКИ ┄┄\n"
            f"{pet_lines or '◇ Пусто…' + chr(10)}"
            f"\n✧ ID: <code>{user_id}</code>\n"
            f"<i>💎 Свет находит путь сквозь кристалл…</i>"
        )

    if template_id == "celestial":
        pet_lines = (f"💞 Союз: {partner_raw}\n" if marriage else "")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv = p.get("pet_level", 1) or 1
            pet_lines += f"🕊️ {safe_html(p['name'])} ({sp}) ур.{lv}\n"
        return (
            f"꧁ ━━ ☀️ НЕБЕСНЫЙ ☀️ ━━ ꧂\n\n"
            f"👤 <b>{nm}</b>\n🌍 {g_rank}\n🏠 {l_rank}\n"
            f"🕊️ Полёт {lvl} [{bar}] {pct}%\n\n"
            f"┄┄ ☀️ НЕБЕСА ┄┄\n"
            f"☀️ Свет: {mora} ⋅ 🌙 {dia}\n"
            f"😇 Святость: +0 ⋅ 🏆 {ach_count}\n\n"
            f"┄┄ 🎶 ГИМНЫ ┄┄\n"
            f"{d}/д ⋅ {w}/н ⋅ {a}/всё\n"
            f"📅 {first_seen} ⋅ 🕓 {last_seen}\n\n"
            f"┄┄ 👼 ХРАНИТЕЛИ ┄┄\n"
            f"{pet_lines or '☁️ Тихо…' + chr(10)}"
            f"\n☀️ ID: <code>{user_id}</code>\n"
            f"<i>☀️ Небо для тех, кто смотрит ввысь…</i>"
        )

    if template_id == "glass":
        pet_lines = (f"💞 Узор: {partner_raw}\n" if marriage else "")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv = p.get("pet_level", 1) or 1
            pet_lines += f"🧩 {safe_html(p['name'])} ({sp}) ур.{lv}\n"
        return (
            f"💠 ═【 🕊️ ВИТРАЖ 🕊️ 】═ 💠\n\n"
            f"👤 <b>{nm}</b>\n🌍 {g_rank}\n🏠 {l_rank}\n"
            f"🖼️ Картина {lvl} [{bar}] {pct}%\n\n"
            f"┄┄ 💠 ОСКОЛКИ ┄┄\n"
            f"💠 Осколки: {mora} ⋅ 🔷 {dia}\n"
            f"🌈 Грань: +0 ⋅ 🏆 {ach_count}\n\n"
            f"┄┄ 🪞 БЛИКИ ┄┄\n"
            f"{d}/д ⋅ {w}/н ⋅ {a}/всё\n"
            f"📅 {first_seen} ⋅ 🕓 {last_seen}\n\n"
            f"┄┄ 🧩 ФРАГМЕНТЫ ┄┄\n"
            f"{pet_lines or '⬜ Пусто…' + chr(10)}"
            f"\n💠 ID: <code>{user_id}</code>\n"
            f"<i>💠 Каждый осколок — часть картины…</i>"
        )

    if template_id == "gold":
        pet_lines = (f"💞 Альянс: {partner_raw}\n" if marriage else "")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv = p.get("pet_level", 1) or 1
            pet_lines += f"🦁 {safe_html(p['name'])} ({sp}) ур.{lv}\n"
        return (
            f"⚜️ ═【 🪙 АУРУМ 🪙 】═ ⚜️\n\n"
            f"👤 <b>{nm}</b>\n🌍 {g_rank}\n🏠 {l_rank}\n"
            f"👑 Проба {lvl} [{bar}] {pct}%\n\n"
            f"┄┄ 🪙 ХРАНИЛИЩЕ ┄┄\n"
            f"🪙 Слитки: {mora} ⋅ 💛 {dia}\n"
            f"⚖️ Вес: +0 ⋅ 🏆 {ach_count}\n\n"
            f"┄┄ 🔔 ЭХО ┄┄\n"
            f"{d}/д ⋅ {w}/н ⋅ {a}/всё\n"
            f"📅 {first_seen} ⋅ 🕓 {last_seen}\n\n"
            f"┄┄ 🦁 СОКРОВИЩА ┄┄\n"
            f"{pet_lines or '🕳️ Пусто…' + chr(10)}"
            f"\n⚜️ ID: <code>{user_id}</code>\n"
            f"<i>💛 Золото молчит, но его слышат все…</i>"
        )

    if template_id == "system_override":
        pet_lines = (f"[+] 🔗 LINK: {partner_raw} 💟\n" if marriage
                     else "[+] 🔗 LINK: <i>null</i> 💔\n")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv = p.get("pet_level", 1) or 1
            pet_lines += f"[*] 🤖 PORT_0{i}: {safe_html(p['name'])} ({sp}) [v{lv}.0]\n"
        return (
            f"▼ 💻 ＳＹＳＴＥＭ_ＯＶＥＲＲＩＤＥ 💻 ▼\n\n"
            f">_ 👤 USER_ID: <b>{name}</b> 📟\n"
            f">_ 🛡️ AUTH: <b>{g_rank}</b>\n"
            f">_ 🏘️ NODE: <b>{l_rank}</b>\n"
            f">_ 🔋 SYNC: Ур.<b>{lvl}</b> [{bar}] <b>{pct}%</b> ⚡\n\n"
            f"► [ 💾 ROOT / ASSETS ] ──────────────\n"
            f"/// 🪙 CRDT: <b>{mora}</b> 🔌 /// 💎 CRYPT: <b>{dia}</b> 🌐\n\n"
            f"► [ 📡 ROOT / DATA ] ────────────────\n"
            f"/// ⚖️ REP: +0 ⚙️  /// 🏆 ACHV: <b>{ach_count}</b> 🔓\n"
            f"/// 💬 LOG: <b>{d}</b>/d 📝 | <b>{w}</b>/w 📊 | <b>{a}</b>/all 🕹️\n"
            f"/// 🕓 SEEN: init {first_seen} | last {last_seen}\n\n"
            f"► [ 🔌 ROOT / ENTITIES ] ────────────\n"
            f"{pet_lines}"
            f"\n▲ 🕹️ ID: <code>{user_id}</code> ▲\n"
            f"<i>*&gt;_ Проснись, Нео. Ты всё ещё в чате… ▮*</i> 🟢"
        )

    elif template_id == "wind_free":
        pet_lines = (f"💍 Узы: {partner_raw} 💞\n" if marriage else "")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv = p.get("pet_level", 1) or 1
            pet_lines += f"🐾 Слот {['I','II'][i-1]}: <b>{safe_html(p['name'])}</b> ({sp}) ⟡ Ранг {lv} {'🔥' if i==1 else '🌙'}\n"
        return (
            f"【 🎐 ‧̍̊˙· ВЕТЕР СВОБОДЫ ·˙‧̍̊ 🎐 】\n\n"
            f"👤 <b>{name_upper}</b> ✦ 🌍 {g_rank} 🪽\n"
            f"[ 🗺️ Ранг: 🏘 {l_rank} ]\n"
            f"╰┈➤ 🌬️ Ур. <b>{lvl}</b> [{bar}] <b>{pct}%</b> ✨\n\n"
            f"▽ 【 🎒 ИНВЕНТАРЬ И ЗАСЛУГИ 】\n"
            f"[ 🪙 {mora} Монет ] ✧ [ 💎 {dia} Кристаллов ]\n"
            f"[ ⚖️ Кармы: +0 🪷 ] ✧ [ 🏆 Ачивок: {ach_count} 📜 ]\n\n"
            f"▽ 【 🕊️ АКТИВНОСТЬ В МИРЕ 】\n"
            f"💬 Связь: <b>{d}</b>/дн 🍃 | <b>{w}</b>/нед ✉️ | <b>{a}</b>/вс 🌐\n"
            f"📅 С нами: {first_seen} 🍃 | Был: {last_seen}\n\n"
            f"▽ 【 ⚔️ СПУТНИКИ И ОТРЯД 】\n"
            f"{pet_lines or '🐾 Питомников нет…' + chr(10)}"
            f"\n【 🎐 ID: <code>{user_id}</code> 】\n"
            f"<i>«Разве не прекрасно, когда ветер сам выбирает путь?»</i> 🍃"
        )

    elif template_id == "empire":
        pet_lines = (f"💍 Узы крови: {partner_raw} 🌹\n" if marriage else "")
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp   = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv   = p.get("pet_level", 1) or 1
            role = "Телохранитель" if i == 1 else "Резерв"
            bird = "🦅" if i == 1 else "🐉"
            pet_lines += f"🐾 {role}: <b>{safe_html(p['name'])}</b> ({sp}) ✦ Ранг {lv} {bird}\n"
        return (
            f"🥂 ✧ ━━ ⚜️ ИМПЕРИЯ ⚜️ ━━ ✧ 🥂\n\n"
            f"👑 ВЛАДЕЛЕЦ: <b>{name}</b> ✦ 🌍 {g_rank}\n"
            f"╰┈➤ 💠 Ур. <b>{lvl}</b> [{bar}] <b>{pct}%</b> ✨\n\n"
            f"▼ 【 🏦 ФИНАНСОВЫЙ КАПИТАЛ 】\n"
            f"💳 Наличные: {mora} 🪙 | 💎 Брюллики: {dia} 💠\n"
            f"⚖️ Влияние: +0 🍷 | 🏆 Награды: {ach_count} 🏵️\n\n"
            f"▼ 【 🪩 СВЕТСКАЯ АКТИВНОСТЬ 】\n"
            f"💌 Чат: <b>{d}</b>/дн 🍾 | <b>{w}</b>/нед 🥂 | <b>{a}</b>/вс 🎭\n"
            f"📅 При дворе с: {first_seen} 🍷 | Замечен: {last_seen}\n\n"
            f"▼ 【 ⚜️ ПРИВИЛЕГИИ И СВИТА 】\n"
            f"{pet_lines or '🐾 Свита пуста…' + chr(10)}"
            f"\n🥂 ✧ ━━ 💳 ID: <code>{user_id}</code> ━━ ✧ 🥂\n"
            f"<i>«У роскоши нет предела, есть только цена…»</i> 💸"
        )

    return None


# ── main render function ───────────────────────────────────────────────────────

async def build_profile_text(
    db,
    user_id: int,
    chat_id: int,
    theme_id_override: str | None = None,
    developer_id: int = 0,
) -> str:
    """
    Generate the exact same HTML string that the bot sends to Telegram.
    Works for both standard and premium themes.
    The result is valid for Telegram HTML parse_mode AND browser innerHTML.
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

    # Premium template
    premium_tpl = theme.get("premium_template")
    if premium_tpl:
        result = _render_premium(
            premium_tpl, user_id, name, g_rank, l_rank, lvl, pct,
            mora_v, dia_v, d_msgs, w_msgs, a_msgs,
            streak, ach_count, warns, marriage, nursery_pets,
            partner_display, dark_v, zar_v, is_vip, join_str, last_str,
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
            + name_block + f"\n"
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
            + name_block + f"\n"
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
