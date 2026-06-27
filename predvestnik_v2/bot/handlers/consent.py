"""bot/handlers/consent.py — приём ToS/Privacy (БЛОК22).

Кнопку «✅ Принять и играть» (callback_data="tos:accept") tos_middleware
пропускает к этому хендлеру; он фиксирует согласие и открывает доступ.
"""
from aiogram import Router, F, types

from infrastructure.repositories.users import accept_tos

router = Router(name="consent_router")


@router.callback_query(F.data == "tos:accept")
async def cb_tos_accept(query: types.CallbackQuery, db):
    await accept_tos(db, query.from_user.id, query.from_user.username)
    await query.answer("Документы приняты ✅")
    try:
        await query.message.edit_text(
            "✅ <b>Документы приняты — доступ открыт!</b>\n\n"
            "Напишите /start или откройте мини-апп. Приятной игры в PREDVESTNIK!",
            parse_mode="HTML",
        )
    except Exception:
        # сообщение могло быть в группе/устареть — не критично
        try:
            await query.message.answer(
                "✅ Документы приняты — доступ открыт! Приятной игры в PREDVESTNIK!")
        except Exception:
            pass
