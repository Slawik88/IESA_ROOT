# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
"""bot/handlers/relics.py — Реликвии: коллекция за Тёмную Мору (Block 13)."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import RELICS, RELIC_RARITY_META
from infrastructure.repositories import relics as relics_db
from services.utils import check_callback_owner

router = Router(name="relics_router")


class RelicBuyCB(CallbackData, prefix="relicbuy"):
    relic_id: str
    user_id: int


async def _render(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    owned = await relics_db.list_owned(db, user_id)
    power = sum(RELIC_RARITY_META.get(RELICS[r]["rarity"], {}).get("power", 0) for r in owned if r in RELICS)
    total_bonus = await relics_db.get_expedition_mora_bonus(db, user_id)

    lines = [
        "🏛 <b>РЕЛИКВИИ</b>",
        f"Коллекция: <b>{len(owned)}/{len(RELICS)}</b> · Сила: <b>{power}</b> · "
        f"Бонус походов: <b>+{int(total_bonus * 100)}%</b> 🪙\n",
        "<i>Покупаются за Тёмную Мору 🌑 (+ другие валюты). Каждая даёт +% к моро-награде экспедиций.</i>\n",
    ]
    b = InlineKeyboardBuilder()
    for rid, r in RELICS.items():
        meta = RELIC_RARITY_META.get(r["rarity"], {})
        mark = "✅" if rid in owned else meta.get("badge", "")
        lines.append(f"{mark} {r['name']} — +{int(r['exp_mora_pct'] * 100)}% поход · {relics_db.price_str(r['price'])}")
        lines.append(f"   <i>{r['desc']}</i>")
        if rid not in owned:
            b.button(text=f"Купить {r['name']} ({relics_db.price_str(r['price'])})",
                     callback_data=RelicBuyCB(relic_id=rid, user_id=user_id))
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


@router.message(TextCmd(["реликвии", "реликвия", "relics"]))
async def cmd_relics(message: types.Message, db):
    if message.chat.type == "private":
        return
    text, kb = await _render(db, message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(RelicBuyCB.filter())
async def cb_relic_buy(query: types.CallbackQuery, callback_data: RelicBuyCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    ok, msg = await relics_db.buy_relic(db, query.from_user.id, callback_data.relic_id)
    if not ok:
        return await query.answer(msg, show_alert=True)
    text, kb = await _render(db, query.from_user.id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await query.answer(msg, show_alert=True)
