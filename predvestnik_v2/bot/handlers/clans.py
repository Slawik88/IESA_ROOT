# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
"""bot/handlers/clans.py — Кланы/гильдии в чате (паритет с мини-аппом).

Тонкий адаптер: вся логика — в services.clans (тот же источник, что и веб-роутер).
"""
import os

from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY
from services import clans as svc
from services.utils import check_callback_owner, safe_html

router = Router(name="clans_router")


class ClanJoinCB(CallbackData, prefix="clanjoin"):
    clan_id: int
    user_id: int


class ClanLeaveCB(CallbackData, prefix="clanleave"):
    user_id: int


class ClanBoardCB(CallbackData, prefix="clanboard"):
    user_id: int


class ClanFillCB(CallbackData, prefix="clanfill"):
    request_id: int
    user_id: int


async def _render(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    ov = await svc.get_overview(db, user_id)
    my = ov["my_clan"]
    b = InlineKeyboardBuilder()
    if my:
        emax = my.get("effective_max", ov["max_members"])
        lines = [f"{my.get('emblem', '🛡')} <b>{safe_html(my['name'])}</b> [{safe_html(my['tag'])}]"]
        if my.get("description"):
            lines.append(f"<i>{safe_html(my['description'])}</i>")
        lines.append(
            f"🏛 Уровень <b>{my.get('level', 1)}</b> · "
            f"Участников: <b>{len(my.get('members', []))}</b>/{emax} · "
            f"XP клана: <b>{int(my.get('total_xp', 0))}</b>"
        )
        lines.append(f"🎖 Твои клан-монеты: <b>{my.get('clan_coins', 0):g}</b>\n")
        reqs = my.get("requests", [])
        if reqs:
            lines.append(f"📋 Доска: <b>{len(reqs)}</b> откр. запрос(ов) — жми «Доска Запросов».")
        lines.append("<b>Состав:</b>")
        for m in my.get("members", []):
            crown = "👑 " if m["role"] == "owner" else "• "
            nm = m.get("username") or f"id{m['user_id']}"
            lines.append(f"{crown}@{safe_html(nm)}")
        b.button(text="📋 Доска Запросов", callback_data=ClanBoardCB(user_id=user_id))
        b.button(text="🚪 Покинуть клан", callback_data=ClanLeaveCB(user_id=user_id))
    else:
        cost = f"{ov['create_cost']:,}".replace(",", " ")
        lines = [
            "🛡 <b>КЛАНЫ</b>",
            f"<i>Ты пока не в клане. Создай свой:</i> <code>бот клан создать, Название ТЕГ</code> "
            f"<i>(стоит {cost} 🪙).</i>\n",
        ]
        top = ov["top"]
        if top:
            lines.append("<b>🏆 Топ кланов</b> (жми, чтобы вступить):")
            for i, c in enumerate(top[:10], 1):
                lines.append(
                    f"{i}. {c.get('emblem', '🛡')} {safe_html(c['name'])} [{safe_html(c['tag'])}] — "
                    f"{int(c['total_xp'])} XP · {c['member_count']}/{ov['max_members']}"
                )
                b.button(text=f"Вступить: {c['name']}",
                         callback_data=ClanJoinCB(clan_id=c["clan_id"], user_id=user_id))
        else:
            lines.append("<i>Кланов ещё нет — стань первым!</i>")
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


class ClanHomeCB(CallbackData, prefix="clanhome"):
    user_id: int


async def _render_board(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    """Доска Запросов клана: открытые запросы + помощь (web-first: создание — на сайте)."""
    ov = await svc.get_overview(db, user_id)
    my = ov["my_clan"]
    b = InlineKeyboardBuilder()
    if not my:
        return "🛡 Ты пока не в клане. Вступи, чтобы пользоваться Доской.", b.as_markup()
    reqs = my.get("requests", [])
    lines = [
        f"📋 <b>ДОСКА ЗАПРОСОВ</b> · {my.get('emblem', '🛡')} {safe_html(my['name'])}",
        "<i>Скинь согильдийцу нужный ресурс — получишь 🎖 клан-монеты и XP клану.</i>",
        f"Партия до <b>{my.get('request_qty_cap', 5)}</b> шт · "
        f"твои монеты: <b>{my.get('clan_coins', 0):g}</b> 🎖\n",
    ]
    if not reqs:
        lines.append("<i>Открытых запросов нет. Создать можно на сайте (➕ ниже).</i>")
    else:
        for r in reqs:
            iname = ITEMS_REGISTRY.get(r["item_id"], {}).get("name", r["item_id"])
            author = r.get("author_name") or f"id{r['author_id']}"
            need, filled = r["qty_need"], r["qty_filled"]
            mine = r["author_id"] == user_id
            tag = " <i>(твой)</i>" if mine else ""
            lines.append(f"├ <b>{safe_html(iname)}</b> {filled}/{need} — @{safe_html(author)}{tag}")
            if not mine:
                b.button(text=f"🤝 Помочь: {iname}",
                         callback_data=ClanFillCB(request_id=r["request_id"], user_id=user_id))
    bu = os.getenv("BOT_USERNAME", "")
    if bu:
        b.button(text="➕ Создать запрос (на сайте)", url=f"https://t.me/{bu}?startapp=clans")
    b.button(text="🛡 К клану", callback_data=ClanHomeCB(user_id=user_id))
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


@router.message(TextCmd(["клан создать", "клан основать"]))
async def cmd_clan_create(message: types.Message, db, text_args: str = ""):
    args = (text_args or "").strip()
    parts = args.split()
    if len(parts) < 2:
        return await message.answer(
            "Использование: <code>бот клан создать, Название ТЕГ</code>\n"
            "<i>Пример: бот клан создать, Волчья Стая WOLF</i>",
            parse_mode="HTML",
        )
    tag = parts[-1]
    name = " ".join(parts[:-1])
    ok, msg, _ = await svc.create(db, message.from_user.id, name, tag)
    await message.answer(("✅ " if ok else "❌ ") + safe_html(msg), parse_mode="HTML")


@router.message(TextCmd(["клан выйти", "клан покинуть"]))
async def cmd_clan_leave(message: types.Message, db, text_args: str = ""):
    ok, msg = await svc.leave(db, message.from_user.id)
    await message.answer(("✅ " if ok else "❌ ") + safe_html(msg), parse_mode="HTML")


@router.message(TextCmd(["клан доска", "доска клана", "клан запросы"]))
async def cmd_clan_board(message: types.Message, db, text_args: str = ""):
    # R3: Доска Запросов удалена — кооперация переехала в Бездну клана (мини-апп)
    import os
    bot_username = os.getenv("BOT_USERNAME", "")
    kb = None
    if bot_username:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="🌀 Открыть Бездну клана",
            url=f"https://t.me/{bot_username}?startapp=clans")]])
    await message.answer(
        "🌀 <b>Доска Запросов ушла в историю.</b>\n"
        "Теперь клан копает <b>Бездну</b>: общая карта 7×7, туман войны, сундуки "
        "с 🔷 Осколками Бездны, монстры и босс этажа. Добыча идёт в казну клана — "
        "на неё строятся здания с баффами всем соклановцам.\n"
        "Всё это — в мини-аппе, вкладка Кланы.",
        reply_markup=kb, parse_mode="HTML")


@router.message(TextCmd(["кланы", "клан", "гильдия", "гильдии"]))
async def cmd_clans(message: types.Message, db, text_args: str = ""):
    text, kb = await _render(db, message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(ClanJoinCB.filter())
async def cb_clan_join(query: types.CallbackQuery, callback_data: ClanJoinCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    ok, msg = await svc.join(db, query.from_user.id, callback_data.clan_id)
    await query.answer(msg, show_alert=True)
    if ok:
        text, kb = await _render(db, query.from_user.id)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(ClanLeaveCB.filter())
async def cb_clan_leave(query: types.CallbackQuery, callback_data: ClanLeaveCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    ok, msg = await svc.leave(db, query.from_user.id)
    await query.answer(msg, show_alert=True)
    text, kb = await _render(db, query.from_user.id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


async def _edit_board(query: types.CallbackQuery, db):
    text, kb = await _render_board(db, query.from_user.id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(ClanBoardCB.filter())
async def cb_clan_board(query: types.CallbackQuery, callback_data: ClanBoardCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await query.answer()
    await _edit_board(query, db)


@router.callback_query(ClanFillCB.filter())
async def cb_clan_fill(query: types.CallbackQuery, callback_data: ClanFillCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    # qty=большое → репо отдаст min(остаток запроса, что есть у донора)
    ok, msg = await svc.request_fill(db, query.from_user.id, callback_data.request_id, 10**9)
    await query.answer(msg, show_alert=True)
    await _edit_board(query, db)


@router.callback_query(ClanHomeCB.filter())
async def cb_clan_home(query: types.CallbackQuery, callback_data: ClanHomeCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await query.answer()
    text, kb = await _render(db, query.from_user.id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
