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
from services.utils import safe_html


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
                    streak, ach_count, warns, marriage, nursery_pets) -> str | None:
    bar  = _premium_bar(pct)
    mora = _compact(mora_v)
    dia  = _compact(dia_v)
    d, w, a = _compact(d_msgs), _compact(w_msgs), _compact(a_msgs)
    name_upper = name.upper()

    if marriage:
        p_nm = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur  = _marriage_duration(marriage.get("marriage_date"))
        partner_raw = f"{safe_html(p_nm)} ({dur})"
    else:
        partner_raw = None

    pets_active  = [p for p in nursery_pets if p.get("placement") == "active"]
    pets_passive = [p for p in nursery_pets if p.get("placement") == "passive"]

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
            f"/// 💬 LOG: <b>{d}</b>/d 📝 | <b>{w}</b>/w 📊 | <b>{a}</b>/all 🕹️\n\n"
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
            f"💬 Связь: <b>{d}</b>/дн 🍃 | <b>{w}</b>/нед ✉️ | <b>{a}</b>/вс 🌐\n\n"
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
            f"💌 Чат: <b>{d}</b>/дн 🍾 | <b>{w}</b>/нед 🥂 | <b>{a}</b>/вс 🎭\n\n"
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

    # Fetch data
    nickname       = await users_repo.get_nickname(db, user_id, chat_id)
    name           = safe_html(nickname or f"user_{user_id}")
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

    if marriage:
        p_nm = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur  = _marriage_duration(marriage.get("marriage_date"))
        partner_line = f"💍 Брак: {safe_html(p_nm)} ({dur})"
    else:
        partner_line = "💍 Не в браке"

    join_str = "—"
    if first_seen_raw:
        dt = parse_dt(first_seen_raw)
        if dt:
            join_str = dt.strftime("%d.%m.%Y")

    # Premium template
    premium_tpl = theme.get("premium_template")
    if premium_tpl:
        result = _render_premium(
            premium_tpl, user_id, name, g_rank, l_rank, lvl, pct,
            mora_v, dia_v, d_msgs, w_msgs, a_msgs,
            streak, ach_count, warns, marriage, nursery_pets,
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
            + f"{partner_line}\n"
            + (f"{shield_line}\n" if shield_line else "")
            + f"🎨 Тема: {t_name}\n\n"
            + f"{t_sep}\n\n"
            + f"🐾 <b>Питомцы:</b>\n"
            + pets_str + tail
        )
