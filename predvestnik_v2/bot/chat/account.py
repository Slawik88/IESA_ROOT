"""Отмена удаления аккаунта и восстановление в срок (services.account_deletion)."""
from __future__ import annotations

from services import account_deletion
from bot.chat.framework import Ctx, registry


@registry.command("отменить удаление", aliases=("отмена удаления",), usage="бот отменить удаление",
                  section="profile", summary="Отменить запрошенное удаление аккаунта.")
async def cmd_cancel_deletion(ctx: Ctx) -> None:
    _, text = await account_deletion.cancel_deletion(ctx.db, ctx.user_id)
    await ctx.reply(text)


@registry.command("восстановить аккаунт", aliases=("восстановление аккаунта",), usage="бот восстановить аккаунт",
                  section="profile", summary="Вернуть удалённый аккаунт, пока не истёк срок.")
async def cmd_restore_account(ctx: Ctx) -> None:
    ok, text = await account_deletion.restore_account(ctx.db, ctx.user_id)
    suffix = "\n<i>Профиль: <code>бот я</code> · Сайт: <code>бот сайт</code></i>" if ok else ""
    await ctx.reply(text + suffix)
