"""Разовая подсказка про ИИ-помощника после N-го сообщения новичка.

Legacy ``users.onboarded`` остаётся только флагом совместимости. Игровое
обучение хранится отдельно в событиях Reconstruction.
"""


async def mark_ai_hint_shown(db, user_id: int) -> bool:
    """True — это первый вызов для юзера, подсказку нужно отправить.
    False — уже отправляли (или гонка: параллельный чат уже забрал право
    первой отправки между чтением msg_count и этим вызовом)."""
    async with db.execute(
        "UPDATE users SET ai_hint_shown = TRUE "
        "WHERE user_tg_id = ? AND ai_hint_shown = FALSE RETURNING user_tg_id",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    if not row:
        return False
    await db.commit()
    return True
