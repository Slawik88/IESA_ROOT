import re
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, Bot
from aiogram.types import ChatPermissions
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from bot.filters.text_commands import TextCmd
from services import moderation as mod_service
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import routing
from services.utils import safe_html
from bot.handlers.moderation import WarnAction

router = Router(name="purge_router")

def parse_purge_args(args: str | None) -> tuple[str, str, int]:
    """Разбирает аргументы чистки. Возвращает: (start_date, end_date, norm)."""
    # По умолчанию: за последние 7 дней, норма 50.
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=7)
    norm = 50

    if not args:
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"), norm

    # Ищем даты (DD.MM или DD.MM.YYYY)
    date_pattern = r"(\d{2}\.\d{2}(?:\.\d{4})?)-(\d{2}\.\d{2}(?:\.\d{4})?)"
    date_match = re.search(date_pattern, args)
    
    if date_match:
        try:
            d1_str, d2_str = date_match.group(1), date_match.group(2)
            fmt1 = "%d.%m.%Y" if len(d1_str) > 5 else "%d.%m"
            fmt2 = "%d.%m.%Y" if len(d2_str) > 5 else "%d.%m"
            
            start_dt = datetime.strptime(d1_str, fmt1)
            end_dt = datetime.strptime(d2_str, fmt2)
            
            # Если год не указан, берем текущий
            if len(d1_str) <= 5: start_dt = start_dt.replace(year=datetime.now().year)
            if len(d2_str) <= 5: end_dt = end_dt.replace(year=datetime.now().year)
            
            # Убираем даты из строки, чтобы найти норму
            args = args.replace(date_match.group(0), "").strip()
        except ValueError:
            pass

    # Ищем норму (просто число)
    norm_match = re.search(r"\b\d+\b", args)
    if norm_match:
        norm = int(norm_match.group(0))

    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"), norm

_WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


@router.message(TextCmd(["чистка", "начать чистку"]))
async def cmd_purge_start(message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return

    can_mod, err = await mod_service.check_admin_rights(db, message.chat.id, message.from_user.id, 4, developer_id=developer_id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    start_date, end_date, norm = parse_purge_args(text_args)

    start_dt_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt_obj = datetime.strptime(end_date, "%Y-%m-%d")
    total_days = (end_dt_obj - start_dt_obj).days + 1
    period_display = (
        f"{start_date} — {end_date} "
        f"({total_days} дн., {_WEEKDAYS_RU[start_dt_obj.weekday()]}–{_WEEKDAYS_RU[end_dt_obj.weekday()]})"
    )

    # 1. ЗАБЛОКИРОВАТЬ ЧАТ (Глобальный мут для юзеров)
    settings = await mod_db.get_chat_settings(db, message.chat.id)
    purge_min_rank = settings.get("purge_min_rank", 4)
    await mod_db.update_chat_settings(db, message.chat.id, is_purging=1)
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=False))
    except Exception:
        pass # Бот может не быть админом

    await message.answer(
        f"🧹 <b>СИСТЕМА ЧИСТКИ АКТИВИРОВАНА</b>\n\n"
        f"⏳ Чат временно закрыт для сбора статистики...\n"
        f"📅 Период: <code>{period_display}</code>\n"
        f"🎯 Норма: <code>{norm} сообщений</code>\n\n"
        f"<i>Генерирую отчет, ожидайте...</i>\n"
        f"<i>⚠️ Завершить чистку: <code>бот конец чистки</code></i>",
        parse_mode="HTML"
    )

    # 2. SQL-ДВИЖОК: Сбор статистики
    query = """
        SELECT 
            u.user_tg_id as id, u.user_tg_username as username,
            s.local_rank, s.joined_at, s.is_immune, s.immune_until, s.warnings,
            IFNULL(SUM(d.message_count), 0) as msg_sum
        FROM user_chat_stats s
        LEFT JOIN users u ON s.user_tg_id = u.user_tg_id
        LEFT JOIN daily_user_stats d ON s.user_tg_id = d.user_id 
                                     AND d.chat_id = s.chat_tg_id 
                                     AND d.date BETWEEN ? AND ?
        WHERE s.chat_tg_id = ? AND s.is_left = 0
        GROUP BY u.user_tg_id
    """
    
    passed_users = []
    failed_users = []
    protected_users = []
    admin_users = []
    exempt_user_ids = []  # ID пользователей с рангом >= purge_min_rank для снятия мута

    async with db.execute(query, (start_date, end_date, message.chat.id)) as cursor:
        async for row in cursor:
            user_data = dict(row)
            uid = user_data['id']
            uname = safe_html(user_data['username'] or f"ID {uid}")
            msg_sum = user_data['msg_sum']
            link = f'<a href="tg://user?id={uid}">{uname}</a>'

            is_exempt = user_data['local_rank'] >= purge_min_rank
            has_absolute_immunity = user_data['is_immune'] == 1
            has_temp_shield = False

            if user_data['immune_until']:
                try:
                    dt = datetime.strptime(user_data['immune_until'], "%Y-%m-%d %H:%M:%S")
                    if dt > datetime.now(): has_temp_shield = True
                except: pass

            if is_exempt:
                admin_users.append(f"├ 👑 {link} ({msg_sum} msg)")
                exempt_user_ids.append(uid)
            elif has_absolute_immunity or has_temp_shield:
                protected_users.append(f"├ 🛡 {link} ({msg_sum} msg)")
            elif msg_sum >= norm:
                passed_users.append(f"├ ✅ {link} ({msg_sum} msg)")
            else:
                failed_users.append(user_data)  # Сохраняем весь словарь для досье

    # 2б. ВЕРНУТЬ ПРАВА МОДЕРАТОРАМ (purge_min_rank и выше)
    write_perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
        can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True
    )
    for uid in exempt_user_ids:
        try:
            await bot.restrict_chat_member(message.chat.id, uid, permissions=write_perms)
            await asyncio.sleep(0.05)
        except Exception:
            pass

    # 3. ГЕНЕРАЦИЯ ДАШБОРДА В ОСНОВНОЙ ЧАТ
    report = (
        f"📊 <b>ИТОГИ ЧИСТКИ АКТИВНОСТИ</b>\n"
        f"📅 Период: <code>{period_display}</code>\n"
        f"🎯 Норма: <code>{norm} сообщений</code>\n\n"
    )

    if admin_users:
        admin_users[-1] = admin_users[-1].replace("├", "└")
        report += f"<b>👑 Администрация (ранг ≥ {purge_min_rank}):</b>\n" + "\n".join(admin_users) + "\n\n"
    if passed_users:
        passed_users[-1] = passed_users[-1].replace("├", "└")
        report += f"<b>Прошли норму ({len(passed_users)}):</b>\n" + "\n".join(passed_users) + "\n\n"
    if protected_users:
        protected_users[-1] = protected_users[-1].replace("├", "└")
        report += f"<b>Под защитой ({len(protected_users)}):</b>\n" + "\n".join(protected_users) + "\n\n"
    if failed_users:
        failed_lines = [f"""├ <a href="tg://user?id={u['id']}">{safe_html(u['username'] or str(u['id']))}</a> ({u['msg_sum']} msg)""" for u in failed_users]
        failed_lines[-1] = failed_lines[-1].replace("├", "└")
        report += f"<b>❌ НЕ ПРОШЛИ ({len(failed_users)}):</b>\n" + "\n".join(failed_lines)
    else:
        report += "<b>❌ НЕ ПРОШЛИ:</b>\n└ <i>Таких нет, все молодцы!</i>"

    # Экранируем слишком длинные списки для ТГ (макс 4096 симв.)
    if len(report) > 4000: report = report[:4000] + "\n... [Список обрезан из-за лимитов Telegram]"
    await message.answer(report, parse_mode="HTML")

    # 4. РАССЫЛКА "ДОСЬЕ" В АДМИН-ЧАТ (С АНТИ-СПАМ ЗАДЕРЖКОЙ)
    admin_chat_id = await routing.get_admin_chat(db, message.chat.id)
    target_chat_to_send_dossier = admin_chat_id if admin_chat_id else message.chat.id

    if failed_users:
        await bot.send_message(target_chat_to_send_dossier, "📁 <b>Начинаю выгрузку личных дел нарушителей...</b>", parse_mode="HTML")
        
        for u in failed_users:
            # Считаем время в чате
            joined_dt = datetime.strptime(u['joined_at'], "%Y-%m-%d %H:%M:%S") if u['joined_at'] else datetime.now()
            days_in_chat = max(1, (datetime.now() - joined_dt).days)
            
            uname = safe_html(u['username'] or f"ID {u['id']}")
            dossier = (
                f"""🗂 <b>ДОСЬЕ НАРУШИТЕЛЯ:</b> <a href="tg://user?id={u['id']}">{uname}</a>\n"""
                f"├ Сообщений за период: <b>{u['msg_sum']}</b> из {norm}\n"
                f"├ Дней в чате: <b>{days_in_chat}</b> (с {joined_dt.strftime('%d.%m.%Y')})\n"
                f"└ Текущие варны: <b>{u['warnings']}</b>\n\n"
                f"<i>Выберите меру наказания:</i>"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="⚠️ Варн", callback_data=WarnAction(action="warn_only", target_id=u['id'], chat_id=message.chat.id))
            builder.button(text="👢 Кик", callback_data=WarnAction(action="kick", target_id=u['id'], chat_id=message.chat.id))
            builder.button(text="🔨 Бан", callback_data=WarnAction(action="ban", target_id=u['id'], chat_id=message.chat.id))
            builder.button(text="🕊 Пропустить", callback_data="delete_dossier")
            builder.adjust(2, 2)
            
            try:
                await bot.send_message(target_chat_to_send_dossier, dossier, reply_markup=builder.as_markup(), parse_mode="HTML")
                await asyncio.sleep(0.3) # АНТИ-СПАМ ЗАДЕРЖКА!
            except Exception as e:
                logger.error(f"Не удалось отправить досье: {e}")

@router.callback_query(lambda c: c.data == "delete_dossier")
async def delete_dossier_callback(callback: types.CallbackQuery):
    await callback.message.delete()

@router.message(TextCmd(["конец чистки", "закончить чистку"]))
async def cmd_purge_stop(message: types.Message, db, bot: Bot, developer_id: int = 0):
    if message.chat.type == "private": return
    can_mod, err = await mod_service.check_admin_rights(db, message.chat.id, message.from_user.id, 4, developer_id=developer_id)
    if not can_mod: return await message.answer(err, parse_mode="HTML")

    await mod_db.update_chat_settings(db, message.chat.id, is_purging=0)
    try:
        permissions = ChatPermissions(
            can_send_messages=True, can_send_audios=True, can_send_documents=True,
            can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
            can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True
        )
        await bot.set_chat_permissions(message.chat.id, permissions)
    except Exception:
        pass
        
    await message.answer("✅ <b>Чистка завершена!</b> Чат снова открыт для общения.", parse_mode="HTML")