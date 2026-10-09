"""«бот вип» — статус VIP и покупка за Зарники прямо в чате (тот же VIP, что в мини-приложении)."""
from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from core.economy_contract import InsufficientBalance
from bot.chat.framework import Ctx, registry
from bot.chat.targets import resolve_target
from services import vip as vip_service

router = Router(name="chat_vip")


class VipCB(CallbackData, prefix="vip"):
    uid: int
    days: int     # 0 — отмена
    ok: bool      # False — выбор срока, True — подтверждение


def fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"


def packages_keyboard(uid: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"👑 {d} {days_word(d)} — {fmt(p)} ✨",
                                  callback_data=VipCB(uid=uid, days=d, ok=False).pack())]
            for d, p in vip_service.VIP_PACKAGES.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def status_line(db, user_id: int) -> str:
    info = await vip_service.get_vip_info(db, user_id)
    if not info:
        return "VIP не активен"
    until = info["expires_at"].strftime("%d.%m.%Y")
    return f"👑 VIP до {until} · осталось {info['days_left']} {days_word(info['days_left'])}"


@registry.command("вип", aliases=("vip", "купить вип"), usage="бот вип [@ник]", section="profile",
                  summary="Статус VIP и покупка за Зарники.")
async def cmd_vip(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target and target.user_id != ctx.user_id:
        await ctx.reply(f"{html.escape(target.label())}: {await status_line(ctx.db, target.user_id)}")
        return
    await ctx.reply(
        f"👑 <b>VIP</b>\n<blockquote>{await status_line(ctx.db, ctx.user_id)}</blockquote>\n"   # СТИЛЬ v1 (оформлено)
        "Ваш образ видят все игроки, плюс удобства в приложении. Новый срок добавляется к текущему.\n\n"
        "Выберите срок — оплата Зарниками (пополнить: <code>бот купить зарники</code>).",
        reply_markup=packages_keyboard(ctx.user_id))


@router.callback_query(VipCB.filter())
async def on_vip(call: CallbackQuery, callback_data: VipCB, db) -> None:
    cb = callback_data
    if call.from_user.id != cb.uid:
        await call.answer("Это не ваша покупка.", show_alert=True)
        return
    if cb.days == 0:
        await call.message.edit_text("✖️ Покупка VIP отменена.")
        await call.answer()
        return
    price = vip_service.VIP_PACKAGES.get(cb.days)
    if price is None:
        await call.answer("Такого срока больше нет.", show_alert=True)
        return
    if not cb.ok:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"✅ Купить за {fmt(price)} ✨", callback_data=VipCB(uid=cb.uid, days=cb.days, ok=True).pack()),
            InlineKeyboardButton(text="✖️ Отмена", callback_data=VipCB(uid=cb.uid, days=0, ok=False).pack()),
        ]])
        await call.message.edit_text(f"👑 VIP на {cb.days} {days_word(cb.days)} за <b>{fmt(price)}</b> ✨ Зарников?",
                                     parse_mode="HTML", reply_markup=kb)
        await call.answer()
        return
    # Ключ покупки — сообщение с кнопками: повторное нажатие не спишет второй раз.
    action_id = f"chat:{call.message.chat.id}:{call.message.message_id}:{cb.days}"
    try:
        result = await vip_service.purchase_vip(db, user_id=cb.uid, package_days=cb.days, action_id=action_id)
    except InsufficientBalance:
        await call.answer(f"Не хватает Зарников: нужно {fmt(price)}. Пополнить — «бот купить зарники».", show_alert=True)
        return
    except vip_service.VipError as exc:
        await call.answer(str(exc)[:190], show_alert=True)
        return
    except Exception:
        logger.exception("chat vip purchase failed")
        await call.answer("Не получилось купить VIP. Зарники не списаны, попробуйте позже.", show_alert=True)
        return
    await call.message.edit_text(
        f"✅ VIP продлён на {cb.days} {days_word(cb.days)}.\n{html.escape(await status_line(db, cb.uid))}")
    await call.answer("Готово")
