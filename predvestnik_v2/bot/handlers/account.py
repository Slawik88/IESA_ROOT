"""Telegram account-deletion recovery commands kept in the release scope."""
from __future__ import annotations

from aiogram import Router, types

from bot.filters.text_commands import TextCmd
from services import account_deletion

router = Router(name="account_router")


@router.message(TextCmd(["отменить удаление", "отмена удаления"]))
async def cmd_cancel_deletion(message: types.Message, db):
    ok, text = await account_deletion.cancel_deletion(db, message.from_user.id)
    await message.answer(text, parse_mode="HTML")


@router.message(TextCmd(["восстановить аккаунт", "восстановление аккаунта"]))
async def cmd_restore_account(message: types.Message, db):
    ok, text = await account_deletion.restore_account(db, message.from_user.id)
    suffix = "\n<i>Профиль: <code>бот я</code> · Сайт: <code>бот сайт</code></i>" if ok else ""
    await message.answer(text + suffix, parse_mode="HTML")
