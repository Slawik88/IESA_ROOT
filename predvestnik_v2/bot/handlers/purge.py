"""bot/handlers/purge.py — Чистка 2.0 (admin_audit B4/B5).

Тонкий чат-адаптер над services/purge.py: сессии в БД, батчевая выдача досье
(«Выслать ещё N»), вердикты кнопками (только инициатор), «конец чистки» больше
НЕ трогает права чата. Тот же движок использует сайт (Админ → Чистка) —
начатую в чате чистку можно продолжить на сайте и наоборот.
"""
from aiogram import Router, types, Bot

from bot.filters.text_commands import TextCmd
from services import moderation as mod_service
from services import purge as purge_svc
from services.utils import feature_guard

router = Router(name="purge_router")


@router.message(TextCmd(["чистка", "начать чистку"]))
async def cmd_purge_start(message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return
    if not await feature_guard(message, db, "tab_purge", "Чистки"):
        return

    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, 4, developer_id=developer_id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    start_date, end_date, norm = purge_svc.parse_purge_args(text_args)

    await message.answer(
        f"🧹 <b>ЧИСТКА: СБОР СВОДКИ</b>\n\n"
        f"📅 Период: <code>{start_date} — {end_date}</code>\n"
        f"🎯 Норма: <code>{norm} сообщений</code>\n\n"
        f"<i>Считаю активность, ожидайте… Досье придут порциями по "
        f"{purge_svc.BATCH_SIZE} — под каждым кнопки вердикта (жмёт инициатор).</i>",
        parse_mode="HTML",
    )

    ok, msg, info = await purge_svc.start_purge(
        db, message.chat.id, message.from_user.id, start_date, end_date, norm)
    if not ok:
        return await message.answer(msg, parse_mode="HTML")
    if info.get("failed", 0) == 0:
        await message.answer(
            "🎉 Нарушителей нет — чистка закрыта автоматически.\n"
            "<i>Следующие шаги: <code>бот кто рест</code> · своя норма/период — "
            "<code>бот чистка, 01.06-30.06 100</code></i>",
            parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith("pm:"))
async def cb_purge_more(callback: types.CallbackQuery, db):
    """«📨 Выслать ещё N» — следующая порция досье. Только инициатор."""
    try:
        session_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return await callback.answer("Ошибка данных.", show_alert=True)
    sent, remaining = await purge_svc.send_next_batch(db, session_id, callback.from_user.id)
    if sent == -1:
        return await callback.answer("Досье высылает только инициатор чистки.", show_alert=True)
    if sent == 0 and remaining == 0:
        return await callback.answer("Все досье уже выданы (или сессия закрыта).", show_alert=True)
    await callback.answer(f"📨 Выслано ещё {sent}.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("pv:"))
async def cb_purge_verdict(callback: types.CallbackQuery, db, developer_id: int = 0):
    """Кнопки вердикта под досье: pv:{session}:{target}:{action}."""
    try:
        _, sid, uid, action = callback.data.split(":")
        session_id, target_id = int(sid), int(uid)
    except (IndexError, ValueError):
        return await callback.answer("Ошибка данных.", show_alert=True)

    ok, text = await purge_svc.apply_verdict(
        db, session_id, target_id, action, callback.from_user.id, developer_id=developer_id)
    if not ok:
        return await callback.answer(text, show_alert=True)
    await callback.answer("Вердикт записан.")
    try:
        # Помечаем досье вынесенным вердиктом, кнопки убираем
        label = purge_svc._VERDICT_LABEL.get(action, action)
        await callback.message.edit_text(
            (callback.message.html_text or "") + f"\n\n<b>Вердикт: {label}</b>",
            parse_mode="HTML")
    except Exception:
        pass


@router.message(TextCmd(["чистка статус", "статус чистки"]))
async def cmd_purge_status(message: types.Message, db):
    if message.chat.type == "private":
        return
    st = await purge_svc.get_status(db, message.chat.id)
    if not st:
        return await message.answer(
            "ℹ️ Активной чистки нет.\n"
            "<i>Начать: <code>бот чистка</code> или <code>бот чистка, 01.06-30.06 100</code></i>",
            parse_mode="HTML")
    c, s = st["counts"], st["session"]
    await message.answer(
        f"🧹 <b>ЧИСТКА #{s['id']}</b> (активна)\n"
        f"├ Досье выдано: <b>{c['sent']}/{c['total']}</b>\n"
        f"├ Вердиктов: <b>{c['decided']}/{c['total']}</b> "
        f"(⚠️ {c['warned']} · 👢 {c['kicked']} · 🔨 {c['banned']} · 🕊 {c['skipped']})\n"
        f"└ Инициатор: <a href=\"tg://user?id={s['initiator_id']}\">ссылка</a>\n\n"
        f"<i>Завершить: <code>бот конец чистки</code> · Продолжить можно и на "
        f"сайте: Админ → Чистка</i>",
        parse_mode="HTML")


@router.message(TextCmd(["конец чистки", "закончить чистку"]))
async def cmd_purge_stop(message: types.Message, db, bot: Bot, developer_id: int = 0):
    if message.chat.type == "private":
        return
    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, 4, developer_id=developer_id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    st = await purge_svc.get_status(db, message.chat.id)
    if not st:
        # Легаси-подстраховка: снять зависший флаг режима чистки без сессии.
        # Права чата НЕ трогаем (admin_audit B5 — старая версия молча сносила
        # ручные ограничения владельца через set_chat_permissions).
        from infrastructure.repositories import moderation as mod_db
        await mod_db.update_chat_settings(db, message.chat.id, is_purging=False)
        return await message.answer(
            "ℹ️ Активной чистки не было — режим чистки снят на всякий случай.\n"
            "<i>Начать новую: <code>бот чистка</code></i>",
            parse_mode="HTML")

    summary = await purge_svc.finish_purge(db, st["session"]["id"], message.from_user.id)
    await message.answer(
        summary + "\n<i>Новая чистка: <code>бот чистка</code> · Защитить от "
                  "чистки: <code>бот рест, @юзер 7д</code></i>",
        parse_mode="HTML")
