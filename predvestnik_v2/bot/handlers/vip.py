"""Read-only chat surface for preserved VIP entitlements."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd
from services.vip import get_vip_info, get_vip_seniority_days

router=Router(name="vip_router")

# Parsers remain only so buttons in already-sent Telegram messages fail closed.
class VipBuyCB(CallbackData,prefix="vipbuy"):
    action:str; tier:str; user_id:int

class VipGiftCB(CallbackData,prefix="vipgift"):
    tier:str; target_id:int; buyer_id:int

_CLOSED=("Новые VIP-покупки закрыты: legacy VIP открывал платный progression-трек. "
         "Существующий срок и уже полученные права сохранены. Новая монетизация — только постоянная косметика.")
_CLOSED_SHORT="Новые VIP-покупки закрыты из-за legacy paid-power. Существующий срок сохранён."

@router.message(TextCmd(["vip","вип"]))
async def cmd_vip(message:types.Message,db):
    info=await get_vip_info(db,int(message.from_user.id))
    seniority=await get_vip_seniority_days(db,int(message.from_user.id))
    lines=["👑 <b>VIP-АРХИВ</b>"]
    if info:
        lines.extend([f"Тариф: <b>{info['tier_label']}</b>",f"Сохранённый срок: <b>{info['days_left']} дн.</b>"])
    else:
        lines.append("Активной legacy-подписки нет.")
    if seniority: lines.append(f"Исторический стаж: <b>{seniority} дн.</b>")
    lines.extend(["",f"<i>{_CLOSED}</i>"])
    await message.answer("\n".join(lines),parse_mode="HTML")

@router.message(TextCmd(["подарить вип","подарить vip","вип в подарок"]))
async def cmd_gift_vip(message:types.Message):
    await message.answer(_CLOSED)

@router.callback_query(VipBuyCB.filter())
async def cb_vip_buy(query:types.CallbackQuery):
    await query.answer(_CLOSED_SHORT,show_alert=True)

@router.callback_query(VipGiftCB.filter())
async def cb_vip_gift(query:types.CallbackQuery):
    await query.answer(_CLOSED_SHORT,show_alert=True)
