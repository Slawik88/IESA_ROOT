"""
bot/handlers/identity.py
Profile display commands (unified design).

  бот я / бот профиль → full own profile card
  бот кто, @user       → target's card using their active theme
  бот анкета           → own detailed card with shareable tg-link

Profile layout (standard themes):
  {top}  ← header + sep embedded
  name · ranks · join-date
  {sep}
  level · rep · balance · streak
  {sep}
  messages · partner · theme name
  {sep}
  pets
  {sep}
  id
  {bot}  ← thematic phrase

Zarniki themes use a bordered frame with prefix on each line
and 2 explicit seps instead of 4.
"""
from datetime import datetime

from aiogram import Router, types
from bot.filters.text_commands import TextCmd
from core.constants import XP_PER_LEVEL
from core.registry import ACHIEVEMENTS, PET_SPECIES
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories import dark_mora as dark_mora_repo
from infrastructure.repositories import achievements as ach_repo
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import marriages as marriage_repo
from infrastructure.repositories import users as users_repo
from infrastructure.repositories import zoo as zoo_db
from infrastructure.repositories.streak import get_streak
from services import roles
from services.formatting import parse_dt
from services.utils import safe_html, resolve_target

router = Router(name="identity_router")

_RARITY_BADGE = {
    "common": "⚪️", "uncommon": "🟩", "rare": "🔵",
    "epic": "🟣", "legendary": "🟡",
}
ACH_TOTAL = len(ACHIEVEMENTS)


# ── helpers ───────────────────────────────────────────────────────────────────

def _compact(n) -> str:
    """1_500 → '1.5k'  |  12_345 → '12.3k'  |  215 → '215'"""
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


def _marriage_duration(val) -> str:
    if not val:
        return "?"
    dt = parse_dt(val)
    if not dt:
        return "?"
    delta = datetime.now() - dt
    d, h = delta.days, delta.seconds // 3600
    return f"{d} дн." if d > 0 else f"{h} ч."


def _fatigue_icon(fatigue: int) -> str:
    if fatigue >= 100: return "⛔"
    if fatigue >= 80:  return "🔴"
    if fatigue >= 40:  return "🟡"
    return "🟢"


def _load_theme(theme_id: str) -> dict:
    from core.themes import THEMES, DEFAULT_THEME
    return THEMES.get(theme_id, THEMES[DEFAULT_THEME])


def _premium_bar(pct: int, length: int = 7) -> str:
    """▰▰▰▰▰▱▱ style bar for premium templates."""
    filled = round(pct / 100 * length)
    return "▰" * filled + "▱" * (length - filled)


def _render_premium_profile(
    template_id: str,
    user_id: int,
    name: str,
    g_rank: str, l_rank: str,
    lvl: int, pct: int,
    mora_v: float, dia_v: float,
    d_msgs: int, w_msgs: int, a_msgs: int,
    streak: int, ach_count: int, warns: int,
    marriage, nursery_pets: list,
) -> str:
    """Render a premium zarniki profile with tematicheskaya terminologiya."""
    bar  = _premium_bar(pct)
    mora = _compact(mora_v)
    dia  = _compact(dia_v)
    d    = _compact(d_msgs)
    w    = _compact(w_msgs)
    a    = _compact(a_msgs)

    # Partner line
    if marriage:
        p_nm = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur  = _marriage_duration(marriage.get("marriage_date"))
        partner_raw = f"{safe_html(p_nm)} ({dur})"
    else:
        partner_raw = None

    # Pets
    pets_active  = [p for p in nursery_pets if p.get("placement") == "active"]
    pets_passive = [p for p in nursery_pets if p.get("placement") == "passive"]

    def _pet_str(p, slot_label: str, port_label: str) -> str:
        sp  = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
        lv  = p.get("pet_level", 1) or 1
        return slot_label, sp, lv, port_label

    name_upper = name.upper()

    # ── SYSTEM OVERRIDE ───────────────────────────────────────────────────────
    if template_id == "system_override":
        pet_lines = ""
        if marriage:
            pet_lines += f"[+] 🔗 LINK: {partner_raw} 💟\n"
        else:
            pet_lines += "[+] 🔗 LINK: <i>null</i> 💔\n"
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp  = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv  = p.get("pet_level", 1) or 1
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

    # ── ВЕТЕР СВОБОДЫ ─────────────────────────────────────────────────────────
    elif template_id == "wind_free":
        pet_lines = ""
        if marriage:
            pet_lines += f"💍 Узы: {partner_raw} 💞\n"
        for i, p in enumerate(pets_active[:1] + pets_passive[:1], 1):
            sp  = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
            lv  = p.get("pet_level", 1) or 1
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

    # ── ИМПЕРИЯ ───────────────────────────────────────────────────────────────
    elif template_id == "empire":
        pet_lines = ""
        if marriage:
            pet_lines += f"💍 Узы крови: {partner_raw} 🌹\n"
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

    return None  # unknown template → use standard renderer


def _pets_block(pets: list, prefix: str = "") -> str:
    """Compact active/passive slots for profile card."""
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
        pet_name = p['name']
        sp_part  = f" ({sp})" if sp and sp != pet_name else ""
        is_last  = (i == len(slots) - 1)
        cont     = "   " if is_last else "│  "
        # Two-line format: name on line 1, stats on line 2 — prevents mobile wrap
        lines.append(
            f"{prefix}{sym} {icon} <b>{pet_name}</b>{sp_part}\n"
            f"{prefix}{cont}Lv{lvl}  {_fatigue_icon(fat)} {fat}/100  📦×{dups}"
        )
    return "\n".join(lines) + "\n"


def _active_pet_str(pets: list) -> str:
    p = next((p for p in pets if p.get("placement") == "active"), None)
    if not p:
        return "нет"
    sp  = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
    lvl = p.get("pet_level", 1) or 1
    fat = p.get("fatigue", 0)
    return f"{p['name']} ({sp}) · Lv{lvl} · {_fatigue_icon(fat)}"


def _theme_fields(theme: dict) -> tuple:
    """Unpack all relevant theme fields."""
    return (
        theme.get("top", ""),
        theme.get("sep", "─" * 8),
        theme.get("bot", ""),
        theme.get("accent", ""),
        theme.get("side", ""),
        theme.get("prefix", ""),
        theme.get("id_in_bot", False),
        theme.get("name", "?"),
    )


def _build_name_lines(
    name: str, g_rank: str, l_rank: str, join_str: str,
    t_accent: str, t_side: str, t_prefix: str,
) -> str:
    P = t_prefix
    if t_side:
        return (
            f"{P}{t_side} {t_accent} <b>{name}</b> {t_accent}\n"
            f"{P}{t_side} 🌍 {g_rank}  |  🏘 {l_rank}\n"
            f"{P}{t_side} 📅 В чате с: {join_str}\n"
        )
    return (
        f"{P}{t_accent} <b>{name}</b>\n"
        f"{P}🌍 {g_rank}  |  🏘 {l_rank}\n"
        f"{P}📅 В чате с: {join_str}\n"
    )


def _build_tail(t_bot: str, t_sep: str, t_id_in_bot: bool, user_id: int, t_prefix: str) -> str:
    P = t_prefix
    if t_id_in_bot:
        return f"{t_sep}\n" + t_bot.replace("{id}", str(user_id))
    return f"{t_sep}\n{P}🆔 <code>{user_id}</code>\n{t_bot}"


# ── бот я / бот профиль ──────────────────────────────────────────────────────

@router.message(TextCmd(["я", "профиль", "стата", "стат", "мой профиль"]))
async def cmd_profile_unified(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return await message.answer("❌ Эта команда доступна только в группах.")

    user_id = message.from_user.id
    chat_id = message.chat.id

    nickname       = await users_repo.get_nickname(db, user_id, chat_id)
    name           = safe_html(nickname or message.from_user.first_name)
    bal            = await eco_repo.get_balance(db, user_id)
    dark_mora      = await dark_mora_repo.get_dark_mora_balance(db, user_id)
    stats          = await chat_repo.get_chat_stats(db, user_id, chat_id)
    global_rank_id = await users_repo.get_global_rank(db, user_id)
    first_seen_raw = await users_repo.get_first_seen(db, user_id)
    nursery_pets   = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    streak_row     = await get_streak(db, user_id, chat_id)
    marriage       = await marriage_repo.get_user_marriage(db, chat_id, user_id)
    hamster_inc    = await zoo_db.get_pending_hamster_income(db, user_id)
    ach_count      = await ach_repo.get_user_achievements_count(db, user_id)

    await zoo_db.apply_fatigue_decay(db, user_id)

    from infrastructure.repositories.themes import get_active_theme
    theme_id = await get_active_theme(db, user_id)
    theme    = _load_theme(theme_id)
    t_top, t_sep, t_bot, t_accent, t_side, t_prefix, t_id_in_bot, t_name = _theme_fields(theme)
    P = t_prefix

    # ── ranks ──────────────────────────────────────────────────────────────────
    g_rank = roles.get_global_rank_name(user_id, global_rank_id, developer_id=developer_id)
    l_rank = roles.get_local_rank_name(user_id, stats.get("local_rank", 0), developer_id=developer_id)

    # ── xp ────────────────────────────────────────────────────────────────────
    lvl       = stats.get("user_level", 1)
    xp        = stats.get("user_xp", 0)
    xp_in_lvl = xp % XP_PER_LEVEL
    bar       = _xp_bar(xp_in_lvl, XP_PER_LEVEL)
    pct       = _xp_pct(xp_in_lvl, XP_PER_LEVEL)
    xp_str    = f"({_compact(xp_in_lvl)}/{_compact(XP_PER_LEVEL)})"

    # ── balance ───────────────────────────────────────────────────────────────
    mora_v = float(bal["user_balance_mora"])
    dia_v  = float(bal["user_balance_diamonds"])
    zar_v  = float(bal.get("user_balance_zarniki", 0))
    dark_v = float(dark_mora)
    ham_note = f" +{_compact(hamster_inc)}🐹" if hamster_inc > 0 else ""

    # Exact numbers — no compact abbreviation. Two lines for all 4 currencies.
    def _fmt_exact(n: float) -> str:
        return f"{int(n):,}".replace(",", " ")  # 47330 → "47 330"
    ham = ham_note
    _bal1 = f"💰 {_fmt_exact(mora_v)} 🪙  |  💎 {dia_v:.1f}{ham}"
    _bal2 = f"🌑 {_fmt_exact(dark_v)} Тёмная  |  ✨ {zar_v:.0f} Зарники"

    # ── social ────────────────────────────────────────────────────────────────
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

    # ── join date ─────────────────────────────────────────────────────────────
    join_str = "—"
    if first_seen_raw:
        dt = parse_dt(first_seen_raw)
        if dt:
            join_str = dt.strftime("%d.%m.%Y")

    # ── premium template override ─────────────────────────────────────────────
    premium_tpl = theme.get("premium_template")
    if premium_tpl:
        premium_text = _render_premium_profile(
            premium_tpl, user_id, name,
            g_rank, l_rank,
            lvl, pct,
            mora_v, dia_v,
            d_msgs, w_msgs, a_msgs,
            streak, ach_count, warns,
            marriage, nursery_pets,
        )
        if premium_text:
            await message.answer(premium_text, parse_mode="HTML")
            return

    name_block = _build_name_lines(name, g_rank, l_rank, join_str, t_accent, t_side, P)
    pets_str   = _pets_block(nursery_pets, P)
    tail       = _build_tail(t_bot, t_sep, t_id_in_bot, user_id, P)

    # ── assemble ─────────────────────────────────────────────────────────────
    if t_prefix:
        # ZARNIKI — bordered layout, 2 explicit seps + empty line between blocks
        text = (
            f"{t_top}\n"
            + name_block
            + f"\n"
            + f"{t_sep}\n"
            + f"\n"
            + f"{P}🌟 Ур.<b>{lvl}</b>  [{bar}] {pct}% {xp_str}\n"
            + f"{P}{_bal1}\n"
            + f"{P}{_bal2}\n"
            + f"{P}🏆 {ach_count} ачив.  |  ⚖️ Реп: +0  |  ⚠️ Варны: {warns}\n"
            + (f"{P}🔥 Стрик: <b>{streak}</b> дн.\n" if streak else "")
            + f"\n"
            + f"{t_sep}\n"
            + f"\n"
            + f"{P}{partner_line}\n"
            + (f"{P}{shield_line}\n" if shield_line else "")
            + f"{P}🎨 Тема: {t_name}\n"
            + f"{P}💬 {d_msgs} д  |  {w_msgs} н  |  {a_msgs} всего\n"
            + f"\n"
            + f"{P}🐾 <b>Питомцы:</b>\n"
            + pets_str
            + tail
        )
    else:
        # STANDARD — 4 explicit seps + empty line between blocks
        text = (
            f"{t_top}\n"
            + name_block
            + f"\n"
            + f"{t_sep}\n"
            + f"\n"
            + f"🌟 Ур.<b>{lvl}</b>  [{bar}] {pct}% {xp_str}\n"
            + f"{_bal1}\n"
            + f"{_bal2}\n"
            + f"🏆 {ach_count} ачив.  |  ⚖️ Реп: +0  |  ⚠️ Варны: {warns}\n"
            + f"🔥 Стрик: <b>{streak}</b> дн.\n"
            + f"\n"
            + f"{t_sep}\n"
            + f"\n"
            + f"💬 {d_msgs} д  |  {w_msgs} н  |  {a_msgs} всего\n"
            + f"{partner_line}\n"
            + (f"{shield_line}\n" if shield_line else "")
            + f"🎨 Тема: {t_name}\n"
            + f"\n"
            + f"{t_sep}\n"
            + f"\n"
            + f"🐾 <b>Питомцы:</b>\n"
            + pets_str
            + tail
        )

    await message.answer(text, parse_mode="HTML")


# ── бот кто ───────────────────────────────────────────────────────────────────

@router.message(TextCmd(["кто"]))
async def cmd_kto(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return

    target_id, target_name, extra = await resolve_target(message, db, text_args)
    if extra == "error_user_not_found":
        return await message.answer(
            "❌ <b>Пользователь не найден.</b> Пусть напишет хоть одно сообщение.",
            parse_mode="HTML",
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот кто, @юзер</code> или ответом на сообщение.",
            parse_mode="HTML",
        )

    chat_id = message.chat.id

    nickname   = await users_repo.get_nickname(db, target_id, chat_id)
    name       = safe_html(nickname or target_name)
    stats      = await chat_repo.get_chat_stats(db, target_id, chat_id)
    g_rank_id  = await users_repo.get_global_rank(db, target_id)
    pets       = await zoo_db.get_user_pets(db, target_id, placement="nursery")
    marriage   = await marriage_repo.get_user_marriage(db, chat_id, target_id)
    streak_row = await get_streak(db, target_id, chat_id)

    from infrastructure.repositories.themes import get_active_theme
    theme_id = await get_active_theme(db, target_id)
    theme    = _load_theme(theme_id)
    t_top, t_sep, t_bot, t_accent, t_side, t_prefix, t_id_in_bot, _ = _theme_fields(theme)
    P = t_prefix

    g_rank = roles.get_global_rank_name(target_id, g_rank_id, developer_id=developer_id)
    l_rank = roles.get_local_rank_name(target_id, stats.get("local_rank", 0), developer_id=developer_id)

    lvl       = stats.get("user_level", 1)
    xp_in_lvl = stats.get("user_xp", 0) % XP_PER_LEVEL
    bar       = _xp_bar(xp_in_lvl, XP_PER_LEVEL)
    pct       = _xp_pct(xp_in_lvl, XP_PER_LEVEL)
    d_msgs    = stats.get("user_messages_count_per_day", 0)
    w_msgs    = stats.get("user_messages_count_per_week", 0)
    a_msgs    = stats.get("user_messages_count_all_time", 0)
    streak    = streak_row.get("streak", 0)

    if marriage:
        p_nm = marriage["user2_name"] if marriage["user1_id"] == target_id else marriage["user1_name"]
        dur  = _marriage_duration(marriage.get("marriage_date"))
        partner_line = f"💍 Брак: {safe_html(p_nm)} ({dur})"
    else:
        partner_line = "💍 Не в браке"

    if t_side:
        name_line = f"{P}{t_side} {t_accent} <b>{name}</b> {t_accent}\n"
        rank_line = f"{P}{t_side} 🌍 {g_rank}  |  🏘 {l_rank}\n"
    else:
        name_line = f"{P}{t_accent} <b>{name}</b>\n"
        rank_line = f"{P}🌍 {g_rank}  |  🏘 {l_rank}\n"

    tail = _build_tail(t_bot, t_sep, t_id_in_bot, target_id, P)

    text = (
        f"{t_top}\n"
        + name_line
        + rank_line
        + f"{t_sep}\n"
        + f"{P}🌟 Ур.<b>{lvl}</b>  [{bar}] {pct}%\n"
        + f"{P}💬 {d_msgs} д  |  {w_msgs} н  |  {a_msgs} всего\n"
        + f"{P}🔥 Стрик: <b>{streak}</b> дн.\n"
        + f"{t_sep}\n"
        + f"{P}{partner_line}\n"
        + f"{P}🐾 Активный: {_active_pet_str(pets)}\n"
        + tail
    )

    await message.answer(text, parse_mode="HTML")


# ── бот анкета ────────────────────────────────────────────────────────────────

@router.message(TextCmd(["анкета"]))
async def cmd_anketa(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    nickname    = await users_repo.get_nickname(db, user_id, chat_id)
    display_name = safe_html(nickname or message.from_user.first_name)
    self_link   = f'<a href="tg://user?id={user_id}">{display_name}</a>'

    stats        = await chat_repo.get_chat_stats(db, user_id, chat_id)
    g_rank_id    = await users_repo.get_global_rank(db, user_id)
    pets         = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    marriage     = await marriage_repo.get_user_marriage(db, chat_id, user_id)
    streak_row   = await get_streak(db, user_id, chat_id)
    global_msgs  = await users_repo.get_messages_global(db, user_id)
    first_seen   = await users_repo.get_first_seen(db, user_id)
    bal          = await eco_repo.get_balance(db, user_id)

    from infrastructure.repositories.themes import get_active_theme
    theme_id = await get_active_theme(db, user_id)
    theme    = _load_theme(theme_id)
    t_top, t_sep, t_bot, t_accent, t_side, t_prefix, t_id_in_bot, _ = _theme_fields(theme)
    P = t_prefix

    g_rank = roles.get_global_rank_name(user_id, g_rank_id, developer_id=developer_id)
    l_rank = roles.get_local_rank_name(user_id, stats.get("local_rank", 0), developer_id=developer_id)

    lvl       = stats.get("user_level", 1)
    xp_in_lvl = stats.get("user_xp", 0) % XP_PER_LEVEL
    bar       = _xp_bar(xp_in_lvl, XP_PER_LEVEL)
    pct       = _xp_pct(xp_in_lvl, XP_PER_LEVEL)

    mora_v = float(bal["user_balance_mora"])
    dia_v  = float(bal["user_balance_diamonds"])

    if marriage:
        p_nm = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur  = _marriage_duration(marriage.get("marriage_date"))
        partner_line = f"💍 {safe_html(p_nm)} ({dur})"
    else:
        partner_line = "💍 Не в браке"

    join_str = "—"
    eco_days = 0
    if first_seen:
        dt = parse_dt(first_seen)
        if dt:
            join_str = dt.strftime("%d.%m.%Y")
            eco_days = (datetime.now() - dt).days

    d_local = stats.get("user_messages_count_per_day", 0)
    w_local = stats.get("user_messages_count_per_week", 0)
    a_local = stats.get("user_messages_count_all_time", 0)
    gd = global_msgs.get("day", 0)
    gw = global_msgs.get("week", 0)
    ga = global_msgs.get("all_time", 0)

    tail = _build_tail(t_bot, t_sep, t_id_in_bot, user_id, P)

    text = (
        f"{t_top}\n"
        f"{P}{t_accent} {self_link}\n"
        f"{P}🌍 {g_rank}  |  🏘 {l_rank}\n"
        f"{P}📅 В Предвестнике: {join_str} ({eco_days} дн.)\n"
        f"{t_sep}\n"
        f"{P}🌟 Ур.<b>{lvl}</b>  [{bar}] {pct}%\n"
        f"{P}💰 {_compact(mora_v)} 🪙  |  💎 {_compact(dia_v)}\n"
        f"{P}{partner_line}\n"
        f"{P}🐾 Питомцев: <b>{len(pets)}</b>  ·  Акт: {_active_pet_str(pets)}\n"
        f"{t_sep}\n"
        f"{P}💬 Чат:   {d_local}д  ·  {w_local}н  ·  {a_local} всего\n"
        f"{P}🌐 Глоб.: {gd}д  ·  {gw}н  ·  {ga} всего\n"
        f"{P}🔥 Стрик: <b>{streak_row.get('streak', 0)}</b> дн.\n"
        + tail
    )

    await message.answer(text, parse_mode="HTML")
