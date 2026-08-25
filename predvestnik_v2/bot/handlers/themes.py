# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
"""
bot/handlers/themes.py
Темы профиля: просмотр по редкостям, покупка, надевание.
  бот темы            → каталог + активная тема
  бот мои темы        → только купленные
"""
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.themes import THEMES, THEME_RARITY_META, RARITY_ORDER, DEFAULT_THEME
from infrastructure.repositories import themes as themes_repo
from services.themes import (
    WEB_DIRECT_THEME_SOURCES,
    ThemePurchaseError,
    get_all_effective_themes,
    get_effective_theme,
    purchase_direct_theme,
)
from services.utils import check_callback_owner, safe_html
from bot.keyboards.cta import answer_group_only

router = Router(name="themes_router")


class ThemeCB(CallbackData, prefix="theme"):
    action: str           # "menu" | "rarity" | "view" | "buy" | "equip" | "mine"
    rarity: str = ""
    theme_id: str = ""
    user_id: int = 0


def _source_label(theme: dict) -> str:
    src = theme.get("source", "")
    if src == "start":          return "Стартовая (бесплатно)"
    if src == "shop_mora":      return f"Магазин · {int(theme.get('price_mora', 0))} 🪙"
    if src == "shop_diamond":   return f"Магазин · {int(theme.get('price_diamonds', 0))} 💎"
    if src == "dark":           return f"Чёрный рынок · {int(theme.get('price_dark', 0))} 🌑"
    if src == "zarniki":        return f"Донат · {int(theme.get('price_zarniki', 0))} ✨"
    if src == "auction":        return "Легендарный аукцион"
    if src == "event":          return "Мировой ивент"
    if src.startswith("gacha"): return f"Гача ({src.split('_')[1]})"
    return "—"


def _price_and_currency(theme: dict):
    """Return (currency, amount) or (None, 0) if not directly purchasable."""
    if theme.get("price_mora"):     return ("mora", theme["price_mora"])
    if theme.get("price_diamonds"): return ("diamonds", theme["price_diamonds"])
    if theme.get("price_dark"):     return ("dark", theme["price_dark"])
    if theme.get("price_zarniki"):  return ("zarniki", theme["price_zarniki"])
    return (None, 0)


# ── Main catalog ──────────────────────────────────────────────────────────────

async def _render_menu(db, user_id: int, target, is_edit: bool):
    active = await themes_repo.get_active_theme(db, user_id)
    owned = await themes_repo.list_owned(db, user_id)
    effective = await get_all_effective_themes(db)
    atheme = effective.get(active, effective[DEFAULT_THEME])

    total = len(effective)
    lines = [
        "🎨 <b>ТЕМЫ ПРОФИЛЯ</b>",
        f"<i>Открыто: {len(owned)}/{total}</i>\n",
        atheme.get("top", ""),
        f"   Активная: <b>{atheme['name']}</b>",
        atheme.get("bot", ""),
        "\n<i>Выбери редкость для просмотра:</i>",
    ]

    b = InlineKeyboardBuilder()
    # Rarity tabs — show count owned/total per rarity (редкость может быть переопределена в БД)
    for rar in RARITY_ORDER:
        meta = THEME_RARITY_META[rar]
        in_rar = [t for t, d in effective.items() if d["rarity"] == rar]
        if not in_rar:
            continue
        owned_cnt = sum(1 for t in in_rar if t in owned)
        b.button(
            text=f"{meta['badge']} {meta['name']} {owned_cnt}/{len(in_rar)}",
            callback_data=ThemeCB(action="rarity", rarity=rar, user_id=user_id),
        )
    b.button(text="🎒 Мои темы", callback_data=ThemeCB(action="mine", user_id=user_id))
    b.adjust(1, 1, 1, 2, 2, 1, 1)

    text = "\n".join(lines)
    if is_edit:
        try:
            await target.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")
        except Exception:
            pass
    else:
        await target.answer(text, reply_markup=b.as_markup(), parse_mode="HTML")


@router.message(TextCmd(["темы", "тема профиля", "профиль темы"]))
async def cmd_themes(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)
    await _render_menu(db, message.from_user.id, message, is_edit=False)


@router.callback_query(ThemeCB.filter(F.action == "menu"))
async def cb_menu(query: types.CallbackQuery, callback_data: ThemeCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await _render_menu(db, query.from_user.id, query.message, is_edit=True)
    await query.answer()


# ── Browse a rarity ───────────────────────────────────────────────────────────

@router.callback_query(ThemeCB.filter(F.action == "rarity"))
async def cb_rarity(query: types.CallbackQuery, callback_data: ThemeCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    user_id = query.from_user.id
    rar = callback_data.rarity
    meta = THEME_RARITY_META.get(rar, {"badge": "", "name": rar})
    owned = await themes_repo.list_owned(db, user_id)
    active = await themes_repo.get_active_theme(db, user_id)
    effective = await get_all_effective_themes(db)

    in_rar = [(t, d) for t, d in effective.items() if d["rarity"] == rar]
    lines = [f"{meta['badge']} <b>{meta['name'].upper()} ТЕМЫ</b>\n"]

    b = InlineKeyboardBuilder()
    for tid, theme in in_rar:
        if tid == active:
            mark = "🟢"
        elif tid in owned:
            mark = "✅"
        else:
            mark = "🔒"
        lines.append(f"{mark} {theme['name']} — <i>{_source_label(theme)}</i>")
        b.button(text=f"{mark} {theme['name']}",
                 callback_data=ThemeCB(action="view", theme_id=tid, rarity=rar, user_id=user_id))

    b.button(text="⬅️ К редкостям", callback_data=ThemeCB(action="menu", user_id=user_id))
    b.adjust(1)

    try:
        await query.message.edit_text("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")
    except Exception:
        pass
    await query.answer()


# ── View a single theme ───────────────────────────────────────────────────────

@router.callback_query(ThemeCB.filter(F.action == "view"))
async def cb_view(query: types.CallbackQuery, callback_data: ThemeCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    user_id = query.from_user.id
    tid = callback_data.theme_id
    theme = await get_effective_theme(db, tid)
    if not theme:
        return await query.answer("❌ Тема не найдена.", show_alert=True)

    owned = await themes_repo.owns_theme(db, user_id, tid)
    active = await themes_repo.get_active_theme(db, user_id)
    meta = THEME_RARITY_META.get(theme["rarity"], {})

    # Live preview of how the profile header will look
    name = safe_html(query.from_user.first_name)
    lines = [
        f"{meta.get('badge','')} <b>{theme['name']}</b>  <i>({meta.get('name','')})</i>",
        f"<i>{safe_html(theme.get('desc',''))}</i>",
        f"📍 {_source_label(theme)}\n",
        "<b>Предпросмотр:</b>",
        theme.get("top", ""),
        f"👤 <b>{name}</b> {theme.get('accent','')}",
        theme.get("bot", ""),
    ]

    b = InlineKeyboardBuilder()
    if tid == active:
        lines.append("\n🟢 <i>Это ваша активная тема.</i>")
    elif owned:
        b.button(text="✅ Надеть", callback_data=ThemeCB(action="equip", theme_id=tid, rarity=callback_data.rarity, user_id=user_id))
    else:
        currency, amount = _price_and_currency(theme)
        if currency:
            cur_icon = {"mora": "🪙", "diamonds": "💎", "dark": "🌑", "zarniki": "✨"}[currency]
            b.button(text=f"🛒 Купить за {int(amount)} {cur_icon}",
                     callback_data=ThemeCB(action="buy", theme_id=tid, rarity=callback_data.rarity, user_id=user_id))
        else:
            lines.append("\n🔒 <i>Эту тему нельзя купить — только особым способом.</i>")

    b.button(text="⬅️ Назад", callback_data=ThemeCB(action="rarity", rarity=callback_data.rarity, user_id=user_id))
    b.adjust(1)

    try:
        await query.message.edit_text("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")
    except Exception:
        pass
    await query.answer()


# ── Buy ───────────────────────────────────────────────────────────────────────

@router.callback_query(ThemeCB.filter(F.action == "buy"))
async def cb_buy(query: types.CallbackQuery, callback_data: ThemeCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    user_id = query.from_user.id
    tid = callback_data.theme_id
    theme = await get_effective_theme(db, tid)
    if not theme:
        return await query.answer("❌ Тема не найдена.", show_alert=True)

    if await themes_repo.owns_theme(db, user_id, tid):
        return await query.answer("✅ У вас уже есть эта тема.", show_alert=True)

    currency, amount = _price_and_currency(theme)
    if not currency:
        return await query.answer("🔒 Эту тему нельзя купить.", show_alert=True)

    # The router is currently unregistered (Web First), but retain it as a
    # safe adapter: any future reactivation must use the same atomic service as
    # the Mini App, never a separate debit → grant sequence.
    try:
        result = await purchase_direct_theme(
            db,
            user_id,
            tid,
            idempotency_key=f"theme:callback:{query.id}",
            allowed_sources=WEB_DIRECT_THEME_SOURCES,
        )
    except ThemePurchaseError as exc:
        return await query.answer(f"❌ {exc}", show_alert=True)

    if result.already_owned:
        return await query.answer("✅ Эта тема уже есть в коллекции.", show_alert=True)
    if result.replayed:
        return await query.answer(f"✅ Покупка уже обработана: {result.theme_name}.", show_alert=True)
    await query.answer(f"🎉 Куплено: {result.theme_name}! Нажми «Надеть».", show_alert=True)

    # Refresh view
    callback_data.action = "view"
    await cb_view(query, callback_data, db)


# ── Equip ─────────────────────────────────────────────────────────────────────

@router.callback_query(ThemeCB.filter(F.action == "equip"))
async def cb_equip(query: types.CallbackQuery, callback_data: ThemeCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    user_id = query.from_user.id
    tid = callback_data.theme_id

    if not await themes_repo.owns_theme(db, user_id, tid):
        return await query.answer("🔒 Сначала купите эту тему.", show_alert=True)

    await themes_repo.set_active_theme(db, user_id, tid)
    theme = THEMES.get(tid, {})
    await query.answer(f"✅ Тема «{theme.get('name', tid)}» надета!", show_alert=True)

    callback_data.action = "view"
    await cb_view(query, callback_data, db)


# ── My themes ─────────────────────────────────────────────────────────────────

@router.callback_query(ThemeCB.filter(F.action == "mine"))
async def cb_mine(query: types.CallbackQuery, callback_data: ThemeCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    user_id = query.from_user.id
    owned = await themes_repo.list_owned(db, user_id)
    active = await themes_repo.get_active_theme(db, user_id)

    owned_themes = [(t, THEMES[t]) for t in THEMES if t in owned]
    lines = [f"🎒 <b>МОИ ТЕМЫ</b> ({len(owned_themes)})\n"]

    b = InlineKeyboardBuilder()
    for tid, theme in owned_themes:
        mark = "🟢" if tid == active else "✅"
        meta = THEME_RARITY_META.get(theme["rarity"], {})
        lines.append(f"{mark} {meta.get('badge','')} {theme['name']}")
        b.button(text=f"{mark} {theme['name']}",
                 callback_data=ThemeCB(action="view", theme_id=tid, rarity=theme["rarity"], user_id=user_id))

    b.button(text="⬅️ В каталог", callback_data=ThemeCB(action="menu", user_id=user_id))
    b.adjust(1)

    try:
        await query.message.edit_text("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")
    except Exception:
        pass
    await query.answer()
