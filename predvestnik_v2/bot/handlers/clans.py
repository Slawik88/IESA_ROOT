"""bot/handlers/clans.py — Кланы/гильдии в чате (паритет с мини-аппом).

Тонкий адаптер: вся логика — в services.clans (тот же источник, что и веб-роутер).
"""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from services import clans as svc
from services.utils import check_callback_owner, safe_html

router = Router(name="clans_router")


class ClanJoinCB(CallbackData, prefix="clanjoin"):
    clan_id: int
    user_id: int


class ClanLeaveCB(CallbackData, prefix="clanleave"):
    user_id: int


async def _render(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    ov = await svc.get_overview(db, user_id)
    my = ov["my_clan"]
    b = InlineKeyboardBuilder()
    if my:
        lines = [f"{my.get('emblem', '🛡')} <b>{safe_html(my['name'])}</b> [{safe_html(my['tag'])}]"]
        if my.get("description"):
            lines.append(f"<i>{safe_html(my['description'])}</i>")
        lines.append(
            f"Участников: <b>{len(my.get('members', []))}</b>/{ov['max_members']} · "
            f"XP клана: <b>{int(my.get('total_xp', 0))}</b>\n"
        )
        lines.append("<b>Состав:</b>")
        for m in my.get("members", []):
            crown = "👑 " if m["role"] == "leader" else "• "
            nm = m.get("username") or f"id{m['user_id']}"
            lines.append(f"{crown}@{safe_html(nm)}")
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
