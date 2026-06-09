import asyncio

from aiogram import Router, types, F
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import (
    SPIN_COSTS, PITY_SOFT, PITY_HARD,
    SPIN_MULTI_DISCOUNT, SPIN_MULTI_COUNT,
    SPIN_TYPE_LABELS, SPIN_TOKEN_IDS,
)
from core.registry import GACHA_TABLES, PITY_HARD_REWARD, PET_SPECIES, ITEMS_REGISTRY
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.gacha import get_all_pity, get_recent_history
from services.gacha import roll_single, roll_multi, get_token_count
from services.quests import increment_metric as quest_increment
from services.utils import format_currency, safe_html, check_callback_owner

router = Router(name="gacha_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_gacha"))

_SPIN_ORDER = ["novice", "standard", "premium", "diamond"]

_RARITY_EMOJI = {"common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
_OUTCOME_EMOJI = {
    "first_copy_created": "🆕",
    "new_copy_created":   "🆕",
    "leveled_up":         "⬆️",
    "added":              "➕",
    "overflow":           "💰",
}


class GachaCB(CallbackData, prefix="gacha"):
    action: str        # menu | type | spin1 | spin10 | token | history | pity | chances | close
    spin_type: str = ""
    user_id: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _maybe_theme_drop(db, user_id: int, spin_type: str) -> str:
    """Small chance to unlock a profile theme from this spin tier's pool.
    Returns a notice string to append, or '' if nothing dropped."""
    import random as _r
    from core.themes import THEME_GACHA_DROPS, THEMES
    from infrastructure.repositories.themes import list_owned, grant_theme
    pool = THEME_GACHA_DROPS.get(spin_type, [])
    if not pool:
        return ""
    chance = {"novice": 0.02, "standard": 0.03, "premium": 0.05, "diamond": 0.08}.get(spin_type, 0.02)
    if _r.random() >= chance:
        return ""
    try:
        owned = await list_owned(db, user_id)
        available = [t for t in pool if t not in owned]
        if not available:
            return ""
        tid = _r.choice(available)
        await grant_theme(db, user_id, tid)
        await db.commit()
        name = THEMES.get(tid, {}).get("name", tid)
        return f"\n\n🎨 <b>РЕДКИЙ ДРОП — ТЕМА ПРОФИЛЯ!</b>\n└ {name} <i>(надеть: «бот темы»)</i>"
    except Exception:
        return ""


async def _safe_edit(msg: types.Message, text: str, **kwargs) -> types.Message:
    """edit_text с обработкой TelegramRetryAfter — ждёт и повторяет один раз."""
    try:
        return await msg.edit_text(text, **kwargs)
    except TelegramRetryAfter as e:
        await asyncio.sleep(min(e.retry_after, 30))
        try:
            return await msg.edit_text(text, **kwargs)
        except Exception:
            return msg
    except Exception:
        return msg


# ── Text formatters ───────────────────────────────────────────────────────────

def _fmt_cost(spin_type: str) -> str:
    c = SPIN_COSTS[spin_type]
    if c["mora"] > 0:
        return f"{int(c['mora'])} 🪙"
    return f"{int(c['diamonds'])} 💎"


def _fmt_cost_multi(spin_type: str) -> str:
    c = SPIN_COSTS[spin_type]
    n = SPIN_MULTI_COUNT
    disc = 1.0 - SPIN_MULTI_DISCOUNT
    if c["mora"] > 0:
        total = int(c["mora"] * n * disc)
        return f"{total} 🪙"
    total = round(c["diamonds"] * n * disc, 1)
    return f"{total} 💎"


def _pity_bar(current: int, hard: int) -> str:
    filled = round((current / hard) * 8)
    return "█" * filled + "░" * (8 - filled)


def _format_single_result(r: dict) -> str:
    lines = []

    if r.get("hard_pity_triggered"):
        lines.append("🛡 <b>ГАРАНТИЯ ПИТИ СРАБОТАЛА!</b>")

    # Mora/diamonds totals
    if r["mora"] > 0:
        lines.append(f"🪙 +{format_currency(r['mora'])} Моры")
    if r["diamonds"] > 0:
        lines.append(f"💎 +{format_currency(r['diamonds'])} Алмазов")

    # Items
    for it in r.get("items", []):
        lines.append(f"📦 {it['name']} × {it['qty']}")

    # Pet duplicates
    for dup in r.get("dup_outcomes", []):
        sp = PET_SPECIES.get(dup.get("species_id") or "", {})
        sp_name = sp.get("name", "?")
        outcome = dup.get("outcome", "added")
        icon = _OUTCOME_EMOJI.get(outcome, "•")
        rarity = dup.get("rarity", "common")
        r_icon = _RARITY_EMOJI.get(rarity, "•")

        if outcome == "overflow":
            lines.append(f"{r_icon} {sp_name} — {icon} Все копии Lv10! (+Мора / Пыль)")
        elif outcome in ("first_copy_created", "new_copy_created"):
            lines.append(
                f"{r_icon} {sp_name} — {icon} Копия {dup.get('copy_index', 1)}/3 появилась!"
            )
        elif outcome == "leveled_up":
            lines.append(
                f"{r_icon} {sp_name} — {icon} Lv{dup.get('prev_level', '?')} → Lv{dup.get('new_level', '?')}!"
            )
        else:
            lines.append(
                f"{r_icon} {sp_name} — {icon} дубликат "
                f"(Lv{dup.get('new_level', '?')}, {dup.get('new_duplicates', '?')} / ...)"
            )

    if not lines:
        lines.append("— (пусто)")

    prefix = "🎉" if r.get("is_valuable") or r.get("hard_pity_triggered") else "✨"
    return f"{prefix} <b>ВЫПАЛО:</b>\n" + "\n".join(f"└ {l}" for l in lines)


def _format_multi_results(results: list) -> str:
    """Consolidated summary of 10× spins."""
    total_mora = sum(r["mora"] for r in results)
    total_dia = sum(r["diamonds"] for r in results)
    item_counts: dict[str, int] = {}
    dup_lines: list[str] = []
    hard_pities = sum(1 for r in results if r.get("hard_pity_triggered"))

    for r in results:
        for it in r.get("items", []):
            item_counts[it["name"]] = item_counts.get(it["name"], 0) + it["qty"]
        for dup in r.get("dup_outcomes", []):
            sp = PET_SPECIES.get(dup.get("species_id") or "", {})
            sp_name = sp.get("name", "?")
            outcome = dup.get("outcome", "added")
            icon = _OUTCOME_EMOJI.get(outcome, "•")
            rarity = dup.get("rarity", "common")
            r_icon = _RARITY_EMOJI.get(rarity, "•")
            dup_lines.append(f"{r_icon} {sp_name} {icon}")

    lines = [f"🎰 <b>{SPIN_MULTI_COUNT}× {SPIN_TYPE_LABELS.get(results[0]['spin_type'], '?')} — ИТОГИ</b>"]

    if hard_pities:
        lines.append(f"🛡 Гарантия пити: <b>{hard_pities}×</b>")
    if total_mora > 0:
        lines.append(f"🪙 Мора: <b>+{format_currency(total_mora)}</b>")
    if total_dia > 0:
        lines.append(f"💎 Алмазы: <b>+{format_currency(total_dia)}</b>")
    for name, qty in item_counts.items():
        lines.append(f"📦 {name} × {qty}")
    for dl in dup_lines:
        lines.append(f"🐾 {dl}")

    return "\n".join(lines)


def _format_chances(spin_type: str) -> str:
    table = GACHA_TABLES.get(spin_type, [])
    total = sum(e["weight"] for e in table)
    label = SPIN_TYPE_LABELS.get(spin_type, spin_type)
    lines = [f"❓ <b>ШАНСЫ: {label}</b>\n"]
    for entry in sorted(table, key=lambda e: e["weight"], reverse=True):
        pct = round(entry["weight"] / total * 100, 1)
        t = entry["type"]
        if t == "mora":
            desc = f"🪙 {entry['min']}–{entry['max']} Моры"
        elif t == "item":
            name = ITEMS_REGISTRY.get(entry["id"], {}).get("name", entry["id"])
            desc = f"{name} × {entry.get('qty', 1)}"
        elif t == "combo":
            parts = [
                f"{ITEMS_REGISTRY.get(i['id'], {}).get('name', i['id'])} × {i.get('qty', 1)}"
                for i in entry.get("items", [])
            ]
            desc = " + ".join(parts)
        elif t == "diamond":
            desc = f"💎 × {entry.get('qty', 1)}"
        elif t in ("pet_dup", "pet_dup_multi"):
            cnt = entry.get("count", 1)
            desc = f"🐾 Дубликат {entry['rarity'].capitalize()} × {cnt}"
        else:
            desc = t
        star = " ⭐" if entry.get("valuable") else ""
        lines.append(f"├ <code>{pct}%</code> {desc}{star}")
    if lines[-1].startswith("├"):
        lines[-1] = "└" + lines[-1][1:]
    hard_rw = PITY_HARD_REWARD.get(spin_type, {})
    hard_rw_desc = f"Дубликат {hard_rw.get('rarity', '?')} питомца" if hard_rw else "—"
    lines.append(
        f"\n<i>⭐ = учитывается в пити</i>\n"
        f"<i>Мягкий порог: {PITY_SOFT[spin_type]} спинов → ×2 шанс ⭐-дропов</i>\n"
        f"<i>Жёсткий порог: {PITY_HARD[spin_type]} спинов → гарантия: {hard_rw_desc}</i>"
    )
    return "\n".join(lines)


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _main_menu_kb(user_id: int = 0) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for st in _SPIN_ORDER:
        label = SPIN_TYPE_LABELS[st]
        cost = _fmt_cost(st)
        # Main spin button + 📋 quick loot preview side by side
        b.button(text=f"{label}  {cost}",
                 callback_data=GachaCB(action="type",    spin_type=st, user_id=user_id))
        b.button(text="📋",
                 callback_data=GachaCB(action="chances", spin_type=st, user_id=user_id))
    b.button(text="📊 Мои пити",  callback_data=GachaCB(action="pity",    user_id=user_id))
    b.button(text="📜 История",   callback_data=GachaCB(action="history", user_id=user_id))
    # 4 spin rows × 2 cols, then 2-wide footer
    b.adjust(2, 2, 2, 2, 2)
    return b.as_markup()


def _spin_type_kb(spin_type: str, token_count: int, pity: int, user_id: int = 0) -> types.InlineKeyboardMarkup:
    """token_count > 0 → кнопка 1× показывает жетон и пишет '(бесплатно)'."""
    b = InlineKeyboardBuilder()
    if token_count > 0:
        spin1_label = f"🎟 Крутить 1×  БЕСПЛАТНО (жетонов: {token_count})"
    else:
        spin1_label = f"🎲 Крутить 1×  {_fmt_cost(spin_type)}"
    cost10 = _fmt_cost_multi(spin_type)
    b.button(text=spin1_label,                     callback_data=GachaCB(action="spin1",   spin_type=spin_type, user_id=user_id))
    b.button(text=f"🎰 Крутить 10×  {cost10}",     callback_data=GachaCB(action="spin10",  spin_type=spin_type, user_id=user_id))
    b.button(text="👀 Шансы",                       callback_data=GachaCB(action="chances", spin_type=spin_type, user_id=user_id))
    b.button(text="⬅️ Назад",                       callback_data=GachaCB(action="menu",    user_id=user_id))
    b.adjust(1, 1, 2)
    return b.as_markup()


def _back_kb(spin_type: str = "", user_id: int = 0) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if spin_type:
        b.button(text="⬅️ Назад к крутке",
                 callback_data=GachaCB(action="type", spin_type=spin_type, user_id=user_id))
    b.button(text="🏠 Меню гачи", callback_data=GachaCB(action="menu", user_id=user_id))
    b.adjust(1)
    return b.as_markup()


# ── Main menu text ────────────────────────────────────────────────────────────

async def _build_main_text(db, user_id: int) -> str:
    bal = await eco_repo.get_balance(db, user_id)
    mora = format_currency(bal["user_balance_mora"])
    dias = format_currency(bal["user_balance_diamonds"])
    pity_all = await get_all_pity(db, user_id)

    token_lines = []
    for st in _SPIN_ORDER:
        token_id = SPIN_TOKEN_IDS.get(st, "")
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
            (user_id, token_id),
        ) as c:
            row = await c.fetchone()
        if row:
            label = SPIN_TYPE_LABELS[st]
            token_lines.append(f"{label} × {row[0]}")

    lines = [
        "🎰 <b>ЗАЛ ГАЧИ</b>\n",
        f"└ 💰 Баланс: <code>{mora} 🪙</code> · <code>{dias} 💎</code>",
    ]
    if token_lines:
        lines.append("└ 🎟 Жетоны: " + " | ".join(token_lines))

    pity_str = " · ".join(
        f"{SPIN_TYPE_LABELS[st].split()[1]}: {pity_all[st]}/{PITY_HARD[st]}"
        for st in _SPIN_ORDER
    )
    lines.append(f"\n<i>Пити: {pity_str}</i>")
    lines.append("\n<i>Выберите тип крутки:</i>")
    return "\n".join(lines)


async def _build_spin_type_text(db, user_id: int, spin_type: str) -> tuple[str, int]:
    """Returns (text, token_count)."""
    pity_all = await get_all_pity(db, user_id)
    pity = pity_all.get(spin_type, 0)
    hard = PITY_HARD[spin_type]
    soft = PITY_SOFT[spin_type]

    token_count = await get_token_count(db, user_id, spin_type)

    bar = _pity_bar(pity, hard)
    label = SPIN_TYPE_LABELS[spin_type]
    hard_rw = PITY_HARD_REWARD.get(spin_type, {})
    hard_rw_desc = f"Дубликат {hard_rw.get('rarity', '?').capitalize()}" if hard_rw else "—"

    bal = await eco_repo.get_balance(db, user_id)
    cost = SPIN_COSTS[spin_type]
    can_afford = (
        token_count > 0 or (
            (bal["user_balance_mora"] >= cost["mora"] if cost["mora"] > 0 else True) and
            (bal["user_balance_diamonds"] >= cost["diamonds"] if cost["diamonds"] > 0 else True)
        )
    )

    token_note = f"🎟 Жетонов: <b>{token_count}</b> — следующий спин бесплатный!\n" if token_count > 0 else ""

    text = (
        f"{label}\n"
        f"├ Стоимость: <b>{_fmt_cost(spin_type)}</b>\n"
        f"{token_note}"
        f"├ Пити: <code>{pity}/{hard}</code> [{bar}]\n"
        f"│  ├ Мягкий ({soft}+): ×2 шанс ⭐-дропов\n"
        f"│  └ Гарантия ({hard}): {hard_rw_desc}\n"
        + (f"⚠️ <i>Недостаточно средств для крутки.</i>\n" if not can_afford else "")
    )
    return text, token_count


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(TextCmd(["пити", "pity", "мои пити"]))
async def cmd_pity(message: types.Message, db):
    if message.chat.type == "private":
        return
    pity_all = await get_all_pity(db, message.from_user.id)
    lines = ["📊 <b>МОИ СЧЁТЧИКИ ПИТИ</b>\n"]
    for st in _SPIN_ORDER:
        pity = pity_all[st]
        hard = PITY_HARD[st]
        soft = PITY_SOFT[st]
        bar = _pity_bar(pity, hard)
        soft_active = "✅" if pity >= soft else "  "
        label = SPIN_TYPE_LABELS[st]
        lines.append(
            f"├ {label}\n"
            f"│  {pity}/{hard} [{bar}]  {soft_active} мягкий"
        )
    lines[-1] = lines[-1].replace("├", "└", 1)
    lines.append("\n<i>Пити сбрасывается при выпадении ⭐-дропа или жёсткой гарантии.</i>")
    await message.answer("\n".join(lines), reply_markup=_back_kb(), parse_mode="HTML")


@router.message(TextCmd(["крутка", "гача", "гаша", "лутбокс"]))
async def cmd_gacha(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return

    args = (text_args or "").strip().lower()
    if args in ("novice", "standard", "premium", "diamond"):
        spin_type = args
    elif args in ("ученическая", "учен"):
        spin_type = "novice"
    elif args in ("стандартная", "стандарт"):
        spin_type = "standard"
    elif args in ("премиум", "прем"):
        spin_type = "premium"
    elif args in ("алмазная", "алмаз"):
        spin_type = "diamond"
    else:
        spin_type = None

    if spin_type:
        text, token_count = await _build_spin_type_text(db, message.from_user.id, spin_type)
        await message.answer(
            text,
            reply_markup=_spin_type_kb(spin_type, token_count, 0),
            parse_mode="HTML",
        )
    else:
        text = await _build_main_text(db, message.from_user.id)
        await message.answer(text, reply_markup=_main_menu_kb(message.from_user.id), parse_mode="HTML")


@router.callback_query(GachaCB.filter(F.action == "menu"))
async def cb_gacha_menu(query: types.CallbackQuery, callback_data: GachaCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text = await _build_main_text(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=_main_menu_kb(query.from_user.id), parse_mode="HTML")
    await query.answer()


@router.callback_query(GachaCB.filter(F.action == "type"))
async def cb_gacha_type(query: types.CallbackQuery, callback_data: GachaCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text, token_count = await _build_spin_type_text(db, query.from_user.id, callback_data.spin_type)
    await query.message.edit_text(
        text,
        reply_markup=_spin_type_kb(callback_data.spin_type, token_count, 0, user_id=callback_data.user_id),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(GachaCB.filter(F.action == "spin1"))
async def cb_gacha_spin1(query: types.CallbackQuery, callback_data: GachaCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await query.answer()
    spin_type = callback_data.spin_type

    # Check tokens BEFORE showing animation (for the label)
    has_token_before = await get_token_count(db, query.from_user.id, spin_type) > 0
    token_note = " 🎟" if has_token_before else ""

    # Animate: show spinner, then result
    sent = await _safe_edit(
        query.message,
        f"🎰 <b>КРУТИМ БАРАБАН...{token_note}</b>\n[████░░░░░░]",
        parse_mode="HTML",
    )
    await asyncio.sleep(0.7)
    await _safe_edit(
        sent,
        f"🎰 <b>ЗАМЕДЛЯЕТСЯ...{token_note}</b>\n[████████░░]",
        parse_mode="HTML",
    )
    await asyncio.sleep(0.7)

    ok, result = await roll_single(db, query.from_user.id, spin_type)

    if not ok:
        await _safe_edit(
            sent,
            f"❌ <b>Отказ:</b> {result}",
            parse_mode="HTML",
            reply_markup=_back_kb(spin_type, user_id=callback_data.user_id),
        )
        return

    text = _format_single_result(result)
    pity_after = result["pity_after"]
    hard = PITY_HARD[spin_type]
    if result.get("used_token"):
        text += "\n\n<i>🎟 Жетон использован (спин бесплатный)</i>"
    text += f"\n<i>Пити: {pity_after}/{hard} [{_pity_bar(pity_after, hard)}]</i>"

    # Theme drop (rare cosmetic bonus)
    theme_note = await _maybe_theme_drop(db, query.from_user.id, spin_type)
    if theme_note:
        text += theme_note

    # Quest: gacha_spins_today
    try:
        await quest_increment(db, query.from_user.id, query.message.chat.id, "gacha_spins_today", delta=1.0)
        await db.commit()
    except Exception:
        pass

    # Show next spin cost (auto-token if still available)
    token_count_now = await get_token_count(db, query.from_user.id, spin_type)
    if token_count_now > 0:
        again_label = f"🔁 Ещё раз  🎟×{token_count_now} (бесплатно)"
    else:
        again_label = f"🔁 Ещё раз  {_fmt_cost(spin_type)}"

    uid = callback_data.user_id
    b = InlineKeyboardBuilder()
    b.button(text=again_label,        callback_data=GachaCB(action="spin1", spin_type=spin_type, user_id=uid))
    b.button(text="⬅️ К крутке",      callback_data=GachaCB(action="type",  spin_type=spin_type, user_id=uid))
    b.button(text="🏠 Меню",          callback_data=GachaCB(action="menu",  user_id=uid))
    b.adjust(1, 2)

    await _safe_edit(sent, text, reply_markup=b.as_markup(), parse_mode="HTML")


@router.callback_query(GachaCB.filter(F.action == "spin10"))
async def cb_gacha_spin10(query: types.CallbackQuery, callback_data: GachaCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await query.answer()
    spin_type = callback_data.spin_type

    await query.message.edit_text(
        "🎰 <b>МУЛЬТИ-КРУТКА 10×...</b>\nЖдите секунду...",
        parse_mode="HTML",
    )

    ok, results = await roll_multi(db, query.from_user.id, spin_type, count=SPIN_MULTI_COUNT)

    if not ok:
        await query.message.edit_text(
            f"❌ <b>Отказ:</b> {results}",
            parse_mode="HTML",
            reply_markup=_back_kb(spin_type, user_id=callback_data.user_id),
        )
        return

    text = _format_multi_results(results)
    pity_final = results[-1]["pity_after"]
    hard = PITY_HARD[spin_type]
    text += f"\n\n<i>Пити после: {pity_final}/{hard}</i>"

    # Theme drop — 10× spins roll the chance 10 times (slightly better odds)
    for _ in range(SPIN_MULTI_COUNT):
        theme_note = await _maybe_theme_drop(db, query.from_user.id, spin_type)
        if theme_note:
            text += theme_note
            break

    await query.message.edit_text(
        text,
        reply_markup=_back_kb(spin_type, user_id=callback_data.user_id),
        parse_mode="HTML",
    )


@router.callback_query(GachaCB.filter(F.action == "pity"))
async def cb_gacha_pity(query: types.CallbackQuery, callback_data: GachaCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    pity_all = await get_all_pity(db, query.from_user.id)
    lines = ["📊 <b>МОИ СЧЁТЧИКИ ПИТИ</b>\n"]
    for st in _SPIN_ORDER:
        pity = pity_all[st]
        hard = PITY_HARD[st]
        soft = PITY_SOFT[st]
        bar = _pity_bar(pity, hard)
        soft_active = "✅" if pity >= soft else "  "
        label = SPIN_TYPE_LABELS[st]
        lines.append(
            f"├ {label}\n"
            f"│  {pity}/{hard} [{bar}]  {soft_active} мягкий"
        )
    lines[-1] = lines[-1].replace("├", "└", 1)
    lines.append("\n<i>Пити сбрасывается при выпадении ⭐-дропа или жёсткой гарантии.</i>")
    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_kb(user_id=callback_data.user_id),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(GachaCB.filter(F.action == "history"))
async def cb_gacha_history(query: types.CallbackQuery, callback_data: GachaCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await query.answer()
    history = await get_recent_history(db, query.from_user.id, limit=20)
    if not history:
        text = "📜 <b>ИСТОРИЯ КРУТКИ</b>\n\n<i>Вы ещё ничего не крутили.</i>"
    else:
        lines = ["📜 <b>ПОСЛЕДНИЕ 20 КРУТОК</b>\n"]
        for h in history:
            r = h["reward"]
            st_label = SPIN_TYPE_LABELS.get(h["spin_type"], h["spin_type"])
            mora = r.get("mora", 0)
            dias = r.get("diamonds", 0)
            dups = r.get("dup_count", 0)
            items_str = ", ".join(r.get("items", [])) or "—"
            date = h["rolled_at"][:16] if h["rolled_at"] else ""
            parts = []
            if mora > 0:
                parts.append(f"{int(mora)} 🪙")
            if dias > 0:
                parts.append(f"{dias} 💎")
            if dups > 0:
                parts.append(f"{dups}× 🐾")
            if items_str != "—":
                parts.append(items_str)
            lines.append(f"├ <code>{date}</code> {st_label} → {', '.join(parts) or '—'}")
        lines[-1] = "└" + lines[-1][1:]
        text = "\n".join(lines)

    await query.message.edit_text(text, reply_markup=_back_kb(user_id=callback_data.user_id), parse_mode="HTML")


@router.callback_query(GachaCB.filter(F.action == "chances"))
async def cb_gacha_chances(query: types.CallbackQuery, callback_data: GachaCB):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text = _format_chances(callback_data.spin_type)
    await query.message.edit_text(
        text,
        reply_markup=_back_kb(callback_data.spin_type, user_id=callback_data.user_id),
        parse_mode="HTML",
    )
    await query.answer()
