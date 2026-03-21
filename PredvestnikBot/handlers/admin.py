import html
import json
import time
from datetime import datetime as _dt, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.types import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import DEVELOPER_ID
from database.db import (
    get_activity_report, get_chat_banlist_users, get_chat_settings, get_chat_stats_for_chat,
    get_rest_info_map, get_rest_users, get_staff_in_chat, get_user_stats,
    get_voluntary_leaves,
    add_user_to_banlist, remove_user_from_banlist,
    set_chat_setting, set_rank_in_chat,
    add_rest_user, remove_rest_user,
    set_cleanup_reminder_sent, upsert_user,
    import_marriage_with_date, get_migration_stats,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import resolve_target, user_mention
from utils.ranks import RANKS, rank_level, rank_name

router = Router()

# ─── Ожидание JSON браков (двухшаговый ввод) ─────────────────────────────────
# chat_id -> (admin_user_id, expires_at)
_awaiting_marriages: dict[int, tuple[int, float]] = {}

# Полные разрешения чата (Bot API 6.3+, гранулярные медиа-поля)
_FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)

_ADMIN_JUNIOR_MAX = "moderator"
_ADMIN_SENIOR_MAX = "admin_junior"
_CO_OWNER_MAX = "admin_senior"


@router.message(BotCommand("ранг", "выдать ранг", "setrank"), RankFilter("admin_junior"))
async def cmd_setrank(message: Message, cmd_args: str):
    # Синтаксис: бот ранг <ранг> @user   или   бот ранг @user <ранг>   или ответом
    parts = cmd_args.split(maxsplit=1) if cmd_args else []

    # Определяем где ранг, а где цель (поддерживаются оба порядка)
    new_rank = None
    rest = ""
    if len(parts) >= 2:
        p0, p1 = parts[0].lower(), parts[1].strip()
        if p0 in RANKS:
            new_rank = p0
            rest = p1
        elif p1.split()[0].lower() in RANKS:
            new_rank = p1.split()[0].lower()
            rest = p0
        else:
            new_rank = p0 if p0 in RANKS else None
            rest = p1
    elif len(parts) == 1:
        if parts[0].lower() in RANKS:
            new_rank = parts[0].lower()
        else:
            rest = parts[0]

    if not new_rank or new_rank not in RANKS:
        await message.answer(
            f"❌ Укажи ранг. Пример: <code>бот ранг moderator @user</code>\n"
            f"Или: <code>бот ранг @user moderator</code>\n"
            f"Доступные: {', '.join(RANKS.keys())}",
            parse_mode="HTML",
        )
        return

    if new_rank == "developer":
        await message.answer(
            "❌ Ранг developer системный и закреплён за DEVELOPER_ID. Выдаётся только через config.py.",
            parse_mode="HTML",
        )
        return

    uid, name, _ = await resolve_target(message, rest)
    if uid is None:
        await message.answer(name)
        return

    # Ensure target user exists in `users` table — otherwise staff JOIN queries miss them
    if message.reply_to_message and getattr(message.reply_to_message, "from_user", None):
        tg_u = message.reply_to_message.from_user
        if tg_u and tg_u.id == uid:
            await upsert_user(uid, tg_u.username or "", tg_u.full_name or "")

    my_stats = await get_user_stats(message.from_user.id, message.chat.id)
    my_rank = "developer" if (DEVELOPER_ID and message.from_user.id == DEVELOPER_ID) else (my_stats["rank"] if my_stats else "user")

    # Определяем максимальный ранг, который может выдать выполняющий
    if rank_level(my_rank) >= rank_level("developer"):
        max_settable = "owner"
    elif rank_level(my_rank) >= rank_level("owner"):
        max_settable = "co_owner"
    elif rank_level(my_rank) >= rank_level("co_owner"):
        max_settable = _CO_OWNER_MAX  # admin_senior
    elif rank_level(my_rank) >= rank_level("admin_senior"):
        max_settable = _ADMIN_SENIOR_MAX  # admin_junior
    else:  # admin_junior
        max_settable = _ADMIN_JUNIOR_MAX  # moderator

    if rank_level(new_rank) > rank_level(max_settable):
        await message.answer(
            f"❌ Твой ранг позволяет выдавать максимум: {rank_name(max_settable)}"
        )
        return

    target_stats = await get_user_stats(uid, message.chat.id)
    target_rank = target_stats["rank"] if target_stats else "user"
    if rank_level(target_rank) >= rank_level(my_rank):
        await message.answer("❌ Нельзя изменить ранг пользователя с равным или большим рангом.")
        return

    try:
        await set_rank_in_chat(uid, message.chat.id, new_rank)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    await message.answer(
        f"✅ Ранг {user_mention(uid, name)} изменён на {rank_name(new_rank)}",
        parse_mode="HTML",
    )


@router.message(BotCommand("состав", "персонал", "стафф", "adminlist"), RankFilter("admin_junior"))
async def cmd_adminlist(message: Message, cmd_args: str):
    staff = await get_staff_in_chat(message.chat.id)
    if not staff:
        await message.answer("👥 Список администрации пуст.")
        return

    lines = ["👥 <b>Администрация чата:</b>\n"]
    for m in staff:
        uname = f"@{m['username']}" if m["username"] else "—"
        lines.append(f"{rank_name(m['rank'])} — <b>{m['full_name']}</b> ({uname})")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("статистика", "статс", "stats"), RankFilter("admin_junior"))
async def cmd_stats(message: Message, cmd_args: str):
    s = await get_chat_stats_for_chat(message.chat.id)
    await message.answer(
        f"📊 <b>Статистика чата</b>\n\n"
        f"👥 Участников в базе: {s['total']}\n"
        f"👮 Администраторов: {s['staff']}\n"
        f"⛔ Заблокировано: {s['banned']}\n"
        f"💬 Всего сообщений: {s['messages']}",
        parse_mode="HTML",
    )


@router.message(BotCommand("правила"), RankFilter("admin_junior"))
async def cmd_rules_set(message: Message, cmd_args: str):
    # Только "установить" / "set" — показ правил делает user.py (нет RankFilter)
    if cmd_args.lower().startswith("установить") or cmd_args.lower().startswith("set"):
        text = cmd_args.split(maxsplit=1)
        if len(text) < 2:
            await message.answer(
                "❌ Укажи текст правил: <code>бот правила установить Ваш текст...</code>",
                parse_mode="HTML",
            )
            return
        rules = text[1]
        await set_chat_setting(message.chat.id, "rules_text", rules)
        await message.answer("✅ Правила чата обновлены.")
    # Если просто "бот правила" от admin — показываем правила (дублируем логику)
    else:
        settings = await get_chat_settings(message.chat.id)
        if settings and settings["rules_text"]:
            await message.answer(
                f"📜 <b>Правила чата:</b>\n\n{settings['rules_text']}",
                parse_mode="HTML",
            )
        else:
            await message.answer("📜 Правила чата ещё не установлены.")


@router.message(BotCommand("приветствие", "welcome"), RankFilter("admin_junior"))
async def cmd_welcome(message: Message, cmd_args: str):
    if cmd_args.lower() in ("выкл", "off", "удалить"):
        await set_chat_setting(message.chat.id, "welcome_text", None)
        await message.answer("✅ Приветственное сообщение отключено.")
    elif cmd_args:
        await set_chat_setting(message.chat.id, "welcome_text", cmd_args)
        await message.answer(
            f"✅ Приветственное сообщение установлено:\n\n{cmd_args}\n\n"
            f"<i>Используй {{name}} для имени, {{username}} для юзернейма</i>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Укажи текст или <code>выкл</code>.\n"
            "Пример: <code>бот приветствие Добро пожаловать, {name}!</code>",
            parse_mode="HTML",
        )


@router.message(BotCommand("прощание", "farewell", "goodbye"), RankFilter("admin_junior"))
async def cmd_farewell(message: Message, cmd_args: str):
    if cmd_args.lower() in ("выкл", "off", "удалить"):
        await set_chat_setting(message.chat.id, "farewell_text", None)
        await message.answer("✅ Прощальное сообщение отключено.")
    elif cmd_args:
        await set_chat_setting(message.chat.id, "farewell_text", cmd_args)
        await message.answer(
            f"✅ Прощальное сообщение установлено:\n\n{cmd_args}",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Укажи текст или <code>выкл</code>.\n"
            "Пример: <code>бот прощание До свидания, {name}!</code>",
            parse_mode="HTML",
        )


@router.message(BotCommand("антифлуд", "antiflood"), RankFilter("admin_junior"))
async def cmd_antiflood(message: Message, cmd_args: str):
    from config import FLOOD_WINDOW, DEFAULT_FLOOD_MUTE
    arg = cmd_args.lower()
    if arg in ("выкл", "off", "0"):
        await set_chat_setting(message.chat.id, "antiflood_enabled", 0)
        await message.answer("✅ Антифлуд отключён.")
    elif arg.isdigit() and int(arg) > 0:
        limit = int(arg)
        mute_mins = DEFAULT_FLOOD_MUTE // 60
        await set_chat_setting(message.chat.id, "antiflood_enabled", 1)
        await set_chat_setting(message.chat.id, "antiflood_limit", limit)
        await message.answer(
            f"✅ Антифлуд включён: максимум {limit} сообщений за {int(FLOOD_WINDOW)} сек.\n"
            f"При нарушении — мут на {mute_mins} мин."
        )
    else:
        await message.answer(
            "❌ Укажи число или <code>выкл</code>.\n"
            "Пример: <code>бот антифлуд 5</code>",
            parse_mode="HTML",
        )


@router.message(BotCommand("тег входа", "коллприветствие", "welcomecall"), RankFilter("admin_junior"))
async def cmd_welcome_call(message: Message, cmd_args: str):
    """Включить/выключить массовое упоминание всех при входе нового участника."""
    arg = (cmd_args or "").strip().lower()
    if arg in ("вкл", "on", "включить", "1"):
        await set_chat_setting(message.chat.id, "welcome_call", 1)
        await message.answer(
            "📢 <b>Колл при вступлении включён.</b>\n"
            "<i>При входе нового участника все члены чата получат упоминание.</i>\n"
            "⚠️ Это может быть шумно в крупных чатах!",
            parse_mode="HTML",
        )
    elif arg in ("выкл", "off", "отключить", "0"):
        await set_chat_setting(message.chat.id, "welcome_call", 0)
        await message.answer("✅ Колл при вступлении отключён.")
    else:
        settings = await get_chat_settings(message.chat.id)
        enabled = settings["welcome_call"] if settings else 0
        status = "🟢 Включён" if enabled else "🔴 Отключён"
        await message.answer(
            f"📢 <b>Колл при вступлении:</b> {status}\n\n"
            f"Включить: <code>бот коллприветствие вкл</code>\n"
            f"Выключить: <code>бот коллприветствие выкл</code>",
            parse_mode="HTML",
        )


@router.message(BotCommand("чистка", "cleanup", "прочистка"), RankFilter("admin_junior"))
async def cmd_cleanup(message: Message, bot: Bot, cmd_args: str):
    """
    бот чистка [N]          — заблокировать чат + отчёт активности за неделю
    бот чистка открыть      — разблокировать чат после чистки
    бот чистка порог [N]    — установить порог по умолчанию
    """
    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    parts   = cmd_args.split() if cmd_args else []
    chat_id = message.chat.id

    # Разблокировать чат
    if parts and parts[0].lower() in ("открыть", "open", "unlock", "разблок", "разблокировать"):
        try:
            await bot.set_chat_permissions(chat_id, _FULL_PERMISSIONS)
            await set_chat_setting(chat_id, "cleanup_locked", 0)
            await message.answer("✅ Чат разблокирован — участники снова могут писать.")
        except Exception as e:
            await message.answer(f"❌ Не удалось разблокировать: {e}")
        return

    # Установить порог по умолчанию
    if parts and parts[0].lower() in ("порог", "threshold"):
        if len(parts) > 1 and parts[1].isdigit():
            await set_chat_setting(chat_id, "cleanup_threshold", int(parts[1]))
            await message.answer(f"✅ Порог чистки по умолчанию: <b>{parts[1]}</b> сообщ./неделю.", parse_mode="HTML")
        else:
            await message.answer("❌ Укажи число: <code>бот чистка порог 10</code>", parse_mode="HTML")
        return

    # Порог сообщений
    if parts and parts[0].isdigit():
        min_msgs = int(parts[0])
    else:
        settings = await get_chat_settings(chat_id)
        val = settings["cleanup_threshold"] if settings else None
        min_msgs = val if val is not None else 10

    # Заблокировать чат (Telegram-администраторы автоматически обходят блокировку)
    locked = False
    try:
        await bot.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=False))
        locked = True
        await set_chat_setting(chat_id, "cleanup_locked", 1)
        staff = await get_staff_in_chat(chat_id)
        for s in staff:
            # Восстанавливаем модераторов и выше — они могут писать во время чистки
            if rank_level(s["rank"]) >= rank_level("moderator"):
                try:
                    await bot.restrict_chat_member(
                        chat_id, s["user_id"],
                        permissions=_FULL_PERMISSIONS,
                    )
                except Exception:
                    pass
    except Exception:
        pass

    users = await get_activity_report(chat_id)
    if not users:
        if locked:
            await bot.set_chat_permissions(chat_id, _FULL_PERMISSIONS)
            await set_chat_setting(chat_id, "cleanup_locked", 0)
        await message.answer("ℹ️ Нет данных об активности за эту неделю.")
        return

    def _short_dt(iso_str):
        if not iso_str:
            return "—"
        try:
            return _dt.fromisoformat(iso_str).strftime("%d.%m")
        except Exception:
            return "—"

    staff_ranks = {"moderator", "admin_junior", "admin_senior", "co_owner", "owner", "developer",
                   "helper", "admin"}  # + backwards compat

    # Сортируем всех по сообщениям за неделю (убывание)
    all_sorted = sorted(users, key=lambda x: x["week_count"], reverse=True)

    # Bulk-проверка отдыха (вместо N+1 запросов)
    rest_info = await get_rest_info_map(chat_id)

    # Категоризация
    staff_list = [u for u in all_sorted if u["rank"] in staff_ranks]
    non_staff  = [u for u in all_sorted if u["rank"] not in staff_ranks]

    resting = []
    passed  = []
    failed  = []
    for u in non_staff:
        if u["user_id"] in rest_info:
            resting.append(u)
        elif u["week_count"] >= min_msgs:
            passed.append(u)
        else:
            failed.append(u)

    lock_line = "🔒 Чат заблокирован" if locked else "⚠️ Не удалось заблокировать чат"
    total = len(all_sorted)
    lines = [
        f"📋 <b>Чистка чата</b>",
        f"{lock_line}  ·  Порог: <b>{min_msgs}</b> сообщ./нед.",
        f"👥 Всего: <b>{total}</b>  |  ✅ {len(passed)}  ❌ {len(failed)}  😴 {len(resting)}  🛡 {len(staff_list)}",
        "",
    ]

    # Стафф (с подсветкой ✅/❌ по порогу)
    if staff_list:
        lines.append(f"🛡 <b>Стафф ({len(staff_list)}):</b>")
        for u in staff_list:
            mark = "✅" if u["week_count"] >= min_msgs else "❌"
            lines.append(
                f"  {mark} {user_mention(u['user_id'], u['full_name'])} "
                f"— {rank_name(u['rank'])} · {u['week_count']}/{min_msgs} за нед."
            )
        lines.append("")

    # На отдыхе (с информацией о днях)
    if resting:
        lines.append(f"😴 <b>На отдыхе ({len(resting)}):</b>")
        for u in resting:
            info = rest_info.get(u["user_id"])
            if info:
                rest_detail = f"ещё {info['days_left']} дн. (до {info['expires'].strftime('%d.%m.%Y')})"
            else:
                rest_detail = ""
            lines.append(
                f"  {user_mention(u['user_id'], u['full_name'])} "
                f"— {u['week_count']} за нед. · {rest_detail}"
            )
        lines.append("")

    # Прошли
    if passed:
        lines.append(f"✅ <b>Прошли ({len(passed)}):</b>")
        for u in passed:
            lines.append(
                f"  {user_mention(u['user_id'], u['full_name'])} "
                f"— <b>{u['week_count']}</b> за нед. ({u['total_count']} всего)"
            )
        lines.append("")

    # Не прошли
    if failed:
        lines.append(f"❌ <b>Не прошли ({len(failed)}):</b>")
        for u in failed:
            lines.append(
                f"  {user_mention(u['user_id'], u['full_name'])} "
                f"— <b>{u['week_count']}</b>/{min_msgs} за нед. | посл.: {_short_dt(u['last_active'])}"
            )
        lines.append("")
        lines.append("<i>Кикнуть: <code>бот кик @username</code></i>")

    lines.append(f"\n🔓 Разблокировать: <code>бот чистка открыть</code>")

    # Telegram has a 4096 char limit per message — split if needed
    text = "\n".join(lines)
    if len(text) <= 4096:
        await message.answer(text, parse_mode="HTML")
    else:
        # Send in chunks
        chunk: list[str] = []
        chunk_len = 0
        for line in lines:
            if chunk_len + len(line) + 1 > 4000:
                await message.answer("\n".join(chunk), parse_mode="HTML")
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += len(line) + 1
        if chunk:
            await message.answer("\n".join(chunk), parse_mode="HTML")

@router.message(BotCommand("чистка дата", "cleanup date", "cleanup_date"), RankFilter("admin_junior"))
async def cmd_cleanup_date(message: Message, cmd_args: str):
    """
    бот чистка дата                   — показать запланированную дату
    бот чистка дата ДД.ММ.ГГГГ ЧЧ:ММ  — установить дату чистки
    бот чистка дата сбросить             — убрать запланирование
    """
    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    chat_id = message.chat.id
    arg = (cmd_args or "").strip().lower()

    if not arg:
        settings = await get_chat_settings(chat_id)
        sched = settings["next_cleanup_at"] if settings else None
        if sched:
            try:
                dt = _dt.fromisoformat(sched).replace(tzinfo=timezone.utc)
                fmt = dt.astimezone(_ZURICH).strftime("%d.%m.%Y %H:%M (Цюрих)")
            except Exception:
                fmt = sched
            await message.answer(
                f"📅 Запланированная чистка: <b>{fmt}</b>\n"
                f"Изменить: <code>бот чистка дата ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
                f"Сбросить: <code>бот чистка дата сбросить</code>",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "📅 Дата чистки не установлена.\n"
                "Установить: <code>бот чистка дата ДД.ММ.ГГГГ ЧЧ:ММ</code>",
                parse_mode="HTML",
            )
        return

    if arg in ("сбросить", "reset", "clear", "убрать"):
        await set_chat_setting(chat_id, "next_cleanup_at", None)
        await set_cleanup_reminder_sent(chat_id, 0)
        await message.answer("✅ Запланированная дата чистки сброшена.")
        return

    # Парсим дату: ДД.ММ.ГГГГ ЧЧ:ММ  или  ДД.ММ.ГГГГ (ввод — по Цюриху)
    raw = cmd_args.strip()
    dt_local = None
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            dt_local = _dt.strptime(raw, fmt).replace(tzinfo=_ZURICH)
            break
        except ValueError:
            pass

    if dt_local is None:
        await message.answer(
            "❌ Не удалось распознать дату.\n"
            "Пример: <code>бот чистка дата 25.03.2026 20:00</code>",
            parse_mode="HTML",
        )
        return

    if dt_local < _dt.now(_ZURICH):
        await message.answer("❌ Дата уже в прошлом. Укажи будущую дату.")
        return

    dt_utc = dt_local.astimezone(timezone.utc)
    await set_chat_setting(chat_id, "next_cleanup_at", dt_utc.replace(tzinfo=None).isoformat())
    await set_cleanup_reminder_sent(chat_id, 0)  # сбросить флаг напоминания
    fmt_str = dt_local.strftime("%d.%m.%Y %H:%M (Цюрих)")
    delta = dt_utc - _dt.now(timezone.utc)
    days_left = delta.days
    await message.answer(
        f"✅ Чистка запланирована на <b>{fmt_str}</b>\n"
        f"⏳ Осталось: <b>{days_left} дн.</b>\n"
        f"🔔 Напоминание в чат придёт за 2 дня до начала.",
        parse_mode="HTML",
    )


@router.message(BotCommand("неактив", "inactivity", "неактивность"), RankFilter("admin_junior"))
async def cmd_inactivity(message: Message, cmd_args: str):
    """
    бот неактив         — показать текущие настройки
    бот неактив вкл     — включить авто-варн за неактив
    бот неактив выкл    — выключить
    бот неактив дни N  — установить порог в N дней
    """
    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    chat_id = message.chat.id
    parts = (cmd_args or "").strip().lower().split()
    settings = await get_chat_settings(chat_id)

    if not parts:
        enabled = bool(settings.get("inactivity_warn_enabled")) if settings else False
        days    = (settings.get("inactivity_warn_days") or 5) if settings else 5
        status  = "✅ Включён" if enabled else "❌ Выключён"
        await message.answer(
            f"⏰ <b>Авто-варн за неактивность</b>\n\n"
            f"Статус: {status}\n"
            f"Порог: <b>{days} дн.()ей</b>\n\n"
            f"<code>бот неактив вкл</code> / <code>выкл</code>\n"
            f"<code>бот неактив дни 5</code> — порог 5 дней",
            parse_mode="HTML",
        )
        return

    if parts[0] in ("вкл", "on", "enable"):
        await set_chat_setting(chat_id, "inactivity_warn_enabled", 1)
        days = (settings.get("inactivity_warn_days") or 5) if settings else 5
        await message.answer(
            f"✅ Авто-варн за неактивность <b>включён</b>.\n"
            f"Порог: {days} дн. без сообщений → варн.",
            parse_mode="HTML",
        )
    elif parts[0] in ("выкл", "off", "disable"):
        await set_chat_setting(chat_id, "inactivity_warn_enabled", 0)
        await message.answer("❌ Авто-варн выключён.")
    elif parts[0] in ("дни", "days", "день", "day") and len(parts) > 1 and parts[1].isdigit():
        new_days = max(1, int(parts[1]))
        await set_chat_setting(chat_id, "inactivity_warn_days", new_days)
        await message.answer(f"✅ Порог неактивности: <b>{new_days} дн.</b>", parse_mode="HTML")
    else:
        await message.answer(
            "❌ Неверные аргументы.\n"
            "Примеры:\n"
            "<code>бот неактив вкл</code>\n"
            "<code>бот неактив выкл</code>\n"
            "<code>бот неактив дни 5</code>",
            parse_mode="HTML",
        )


# ─── Скан / статистика данных в БД ───────────────────────────────────────────

@router.message(BotCommand("скан", "scan", "статистика бд"), RankFilter("developer"))
async def cmd_scan(message: Message):
    """
    бот скан — показать статистику данных в БД для этого чата.
    Напоминает об использовании scan_history.py для исторических данных.
    """
    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    stats = await get_migration_stats(message.chat.id)
    top_lines = []
    for i, u in enumerate(stats["top5"], 1):
        name = html.escape(u.get("full_name") or u.get("username") or str(u["user_id"]))
        top_lines.append(f"  {i}. {name} — {u['message_count']:,} сообщ.")

    top_block = "\n".join(top_lines) if top_lines else "  (нет данных)"

    await message.answer(
        f"📊 <b>Статистика данных в БД</b>\n\n"
        f"👥 Пользователей в БД: <b>{stats['users_total']}</b>\n"
        f"💬 С сообщениями:      <b>{stats['users_with_msgs']}</b>\n"
        f"📩 Всего сообщений:    <b>{stats['total_messages']:,}</b>\n"
        f"💑 Браков:             <b>{stats['marriages_pairs']}</b>\n\n"
        f"🔝 <b>Топ-5 по сообщениям:</b>\n{top_block}\n\n"
        f"⚠️ <b>Об исторических сообщениях:</b>\n"
        f"Telegram Bot API не позволяет боту читать историю чата.\n"
        f"Для импорта накопленных сообщений из прошлого использу скрипт:\n"
        f"<code>python scripts/scan_history.py --chat {message.chat.id} --db bot.db</code>\n"
        f"(нужны api_id + api_hash от my.telegram.org)",
        parse_mode="HTML",
    )


# ─── Импорт браков из JSON ────────────────────────────────────────────────────

_MARRIAGES_JSON_EXAMPLE = (
    "[\n"
    '  {"user1": 123456789, "user2": 987654321, "since": "21.03.2025"},\n'
    '  {"user1": "@alice",  "user2": "@bob",    "since": "01.06.2024"},\n'
    '  {"user1": 111111,    "user2": 222222}\n'
    "]"
)
_MARRIAGES_HELP = (
    "💑 <b>Импорт браков из JSON</b>\n\n"
    "Формат каждой пары:\n"
    "<code>{\"user1\": ID_или_@юзернейм, \"user2\": ID_или_@юзернейм, \"since\": \"ДД.ММ.ГГГГ\"}</code>\n\n"
    "Поле <code>since</code> — необязательно (по умолчанию: сегодня).\n\n"
    "Пример JSON:\n"
    f"<pre>{html.escape(_MARRIAGES_JSON_EXAMPLE)}</pre>\n\n"
    "👉 Отправь JSON списком в <b>следующем сообщении</b> (ожидание 3 минуты).\n"
    "Или укажи его прямо после команды в одной строке:\n"
    "<code>бот загрузить браки [{\"user1\":123,\"user2\":456,\"since\":\"01.01.2025\"}]</code>"
)

_ZURICH = ZoneInfo("Europe/Zurich")


async def _resolve_uid(bot: Bot, chat_id: int, ref) -> int | None:
    """Возвращает integer user_id из числа, строки-числа или @username."""
    if isinstance(ref, int):
        return ref
    ref = str(ref).strip()
    if ref.lstrip("-").isdigit():
        return int(ref)
    if ref.startswith("@"):
        try:
            member = await bot.get_chat_member(chat_id, ref)
            return member.user.id
        except Exception as exc:
            return None
    return None


async def _process_marriages_json(message: Message, bot: Bot, raw: str) -> None:
    chat_id = message.chat.id
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        await message.answer(
            f"❌ Ошибка разбора JSON: <code>{html.escape(str(exc))}</code>\n\n"
            f"Проверь формат и попробуй снова.",
            parse_mode="HTML",
        )
        return

    if not isinstance(data, list):
        await message.answer("❌ JSON должен быть <b>списком</b> (массивом) пар.", parse_mode="HTML")
        return

    ok_pairs: list[str] = []
    fail_pairs: list[str] = []

    today_utc = _dt.now(_ZURICH).astimezone(timezone.utc).replace(tzinfo=None).isoformat()

    for idx, entry in enumerate(data, 1):
        if not isinstance(entry, dict):
            fail_pairs.append(f"#{idx}: не объект")
            continue

        u1_raw = entry.get("user1")
        u2_raw = entry.get("user2")
        since_raw = entry.get("since", "")

        if u1_raw is None or u2_raw is None:
            fail_pairs.append(f"#{idx}: нет user1 или user2")
            continue

        uid1 = await _resolve_uid(bot, chat_id, u1_raw)
        uid2 = await _resolve_uid(bot, chat_id, u2_raw)

        if uid1 is None:
            fail_pairs.append(f"#{idx}: не удалось определить {u1_raw!r}")
            continue
        if uid2 is None:
            fail_pairs.append(f"#{idx}: не удалось определить {u2_raw!r}")
            continue

        # Парсим дату since
        married_at = today_utc
        if since_raw:
            for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
                try:
                    dt_local = _dt.strptime(str(since_raw), fmt).replace(tzinfo=_ZURICH)
                    married_at = dt_local.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
                    break
                except ValueError:
                    pass

        try:
            await import_marriage_with_date(uid1, uid2, chat_id, married_at)
            ok_pairs.append(f"[{uid1}] ↔ [{uid2}]")
        except Exception as exc:
            fail_pairs.append(f"#{idx}: ошибка БД — {exc}")

    lines = []
    if ok_pairs:
        lines.append(f"✅ Импортировано <b>{len(ok_pairs)}</b> пар:")
        lines.extend(f"  • {p}" for p in ok_pairs)
    if fail_pairs:
        lines.append(f"\n⚠️ Ошибки ({len(fail_pairs)}):")
        lines.extend(f"  • {html.escape(p)}" for p in fail_pairs)

    await message.answer("\n".join(lines) or "Нет пар для импорта.", parse_mode="HTML")


@router.message(BotCommand("загрузить браки", "load_marriages", "импорт браки"), RankFilter("admin_junior"))
async def cmd_load_marriages(message: Message, cmd_args: str, bot: Bot):
    """
    бот загрузить браки                — показать формат + ждать JSON
    бот загрузить браки [{"user1":…}]  — импортировать сразу
    """
    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    raw = (cmd_args or "").strip()
    if raw:
        await _process_marriages_json(message, bot, raw)
        return

    # Режим ожидания: следующее сообщение от этого же админа
    _awaiting_marriages[message.chat.id] = (message.from_user.id, time.time() + 180)
    await message.answer(_MARRIAGES_HELP, parse_mode="HTML")


async def _is_awaiting_json(message: Message) -> bool:
    if not message.chat or not message.from_user or not message.text:
        return False
    entry = _awaiting_marriages.get(message.chat.id)
    if entry is None:
        return False
    admin_id, expires = entry
    if time.time() > expires:
        del _awaiting_marriages[message.chat.id]
        return False
    return message.from_user.id == admin_id


@router.message(_is_awaiting_json)
async def _catch_marriages_json(message: Message, bot: Bot):
    """Перехватывает JSON-ответ в режиме ожидания бракоимпорта."""
    del _awaiting_marriages[message.chat.id]
    await _process_marriages_json(message, bot, message.text)


# ─── Соцсети ──────────────────────────────────────────────────────────────────

@router.message(BotCommand("соцсети", "соцсеть", "socials"), RankFilter("admin_junior"))
async def cmd_set_social(message: Message, cmd_args: str):
    _valid = {"tiktok", "youtube", "instagram"}
    args = (cmd_args or "").strip()
    if not args:
        await message.answer(
            "🔗 <b>Настройка соцсетей чата</b>\n\n"
            "Синтаксис:\n"
            "<code>бот соцсети tiktok https://tiktok.com/@channel</code>\n"
            "<code>бот соцсети youtube https://youtube.com/@channel</code>\n"
            "<code>бот соцсети instagram https://instagram.com/page</code>\n\n"
            "Удалить: <code>бот соцсети tiktok удалить</code>\n"
            "Показать в чат: <code>бот нашиссылки</code>",
            parse_mode="HTML",
        )
        return

    parts = args.split(maxsplit=1)
    key = parts[0].lower()
    url = parts[1].strip() if len(parts) > 1 else ""

    if key not in _valid:
        await message.answer(
            f"❌ Неизвестная соцсеть «{key}».\n"
            f"Доступные: {', '.join(_valid)}",
        )
        return

    field_name = f"social_{key}"
    if url.lower() in ("удалить", "удал", "delete", "remove", ""):
        await set_chat_setting(message.chat.id, field_name, None)
        await message.answer(f"✅ Ссылка на {key} удалена.")
    else:
        await set_chat_setting(message.chat.id, field_name, url)
        await message.answer(f"✅ {key}: {url}", disable_web_page_preview=True)


# ─── Подсказка по истории чата ────────────────────────────────────────────────

@router.message(BotCommand("история чата", "историячата", "chathistory"), RankFilter("admin_junior"))
async def cmd_chat_history_hint(message: Message, cmd_args: str):
    await message.answer(
        "📋 <b>Как включить видимую историю для новых участников</b>\n\n"
        "Telegram не позволяет ботам менять эту настройку.\n"
        "Включите вручную:\n\n"
        "1. Откройте <b>настройки группы</b>\n"
        "2. Найдите <b>«История чата»</b> (Chat History)\n"
        "3. Выберите <b>«Видна»</b> (Visible)\n\n"
        "После этого все новые участники будут видеть старые сообщения.",
        parse_mode="HTML",
    )


# ─── Отдых (защита от чистки) ────────────────────────────────────────────────

@router.message(BotCommand("отдых", "rest"), RankFilter("co_owner"))
async def cmd_rest(message: Message, cmd_args: str):
    """
    бот отдых @user [дней]   — поставить на отдых (по умолч. 7 дней)
    бот отдых снять @user    — снять отдых
    бот отдых список         — список отдыхающих
    """
    args = (cmd_args or "").strip()
    chat_id = message.chat.id

    if not args:
        await message.answer(
            "😴 <b>Управление отдыхом</b>\n\n"
            "Пользователи на отдыхе не затрагиваются чисткой.\n\n"
            "<code>бот отдых @user 14</code> — отдых на 14 дней\n"
            "<code>бот отдых @user</code> — отдых на 7 дней\n"
            "<code>бот отдых снять @user</code> — снять отдых\n"
            "<code>бот отдых список</code> — список отдыхающих",
            parse_mode="HTML",
        )
        return

    parts = args.split(maxsplit=1)

    # Список отдыхающих
    if parts[0].lower() in ("список", "list", "лист"):
        rest_list = await get_rest_users(chat_id)
        if not rest_list:
            await message.answer("😴 Список отдыхающих пуст.")
            return
        lines = ["😴 <b>На отдыхе:</b>\n"]
        for r in rest_list:
            added = _dt.fromisoformat(r["added_at"])
            expires = added + __import__("datetime").timedelta(days=r["days"])
            lines.append(
                f"  • {user_mention(r['user_id'], r['full_name'])} — "
                f"{r['days']} дн. (до {expires.strftime('%d.%m.%Y')})"
            )
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # Снять отдых
    if parts[0].lower() in ("снять", "убрать", "remove", "delete"):
        if len(parts) < 2:
            await message.answer("❌ Укажи пользователя: <code>бот отдых снять @user</code>", parse_mode="HTML")
            return
        uid, name, _ = await resolve_target(message, parts[1].strip())
        if uid is None:
            await message.answer(name)
            return
        await remove_rest_user(uid, chat_id)
        await message.answer(f"✅ {user_mention(uid, name)} снят(а) с отдыха.", parse_mode="HTML")
        return

    # Добавить на отдых: бот отдых @user [дней]
    uid, name, remaining = await resolve_target(message, parts[0])
    if uid is None:
        await message.answer(name)
        return
    days_str = remaining or (parts[1] if len(parts) > 1 else "")
    days = 7
    if days_str and days_str.strip().isdigit():
        days = max(1, min(365, int(days_str.strip())))

    await add_rest_user(uid, chat_id, days, message.from_user.id)
    await message.answer(
        f"😴 {user_mention(uid, name)} на отдыхе <b>{days}</b> дней.\n"
        f"Не будет затронут(а) чисткой.",
        parse_mode="HTML",
    )


@router.message(BotCommand("ушли", "leavelog", "покинули"), RankFilter("moderator"))
async def cmd_leave_log(message: Message, cmd_args: str):
    """Показать последних пользователей, которые добровольно покинули чат."""
    try:
        limit = max(1, min(50, int(cmd_args.strip()))) if cmd_args.strip().isdigit() else 15
    except (ValueError, AttributeError):
        limit = 15

    rows = await get_voluntary_leaves(message.chat.id, limit)
    if not rows:
        await message.answer(
            "📋 Никто добровольно не покидал чат (по крайней мере с момента запуска бота)."
        )
        return

    import html as _html
    lines = [f"🚪 <b>Последние {len(rows)} добровольных выходов:</b>\n"]
    for r in rows:
        uid_val = r["user_id"]
        safe_name = _html.escape(r["full_name"] or str(uid_val))
        uname = f" (@{_html.escape(r['username'])})" if r.get("username") else ""
        left_at = (r["left_at"] or "")[:16].replace("T", " ")
        lines.append(
            f"  • <a href='tg://user?id={uid_val}'>{safe_name}</a>{uname} — {left_at}"
        )
    lines.append(f"\n<i>Используй «бот ушли N» для другого числа записей.</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── ЧС по Telegram ID пользователя ──────────────────────────────────────────

@router.message(BotCommand("юзбан", "usrban", "банюзер"), RankFilter("moderator"))
async def cmd_user_ban(message: Message, cmd_args: str):
    """Добавить Telegram ID в чёрный список чата."""
    import html as _html
    raw = (cmd_args or "").strip()
    # Поддержка: числовой ID или @username (если есть в БД)
    if raw.lstrip("-").isdigit():
        user_id = int(raw)
        display = str(user_id)
    else:
        from utils.helpers import resolve_target
        uid, name, _ = await resolve_target(message, raw)
        if not uid:
            await message.answer(
                "❌ Укажи числовой ID или @username.\n"
                "Пример: <code>бот юзбан 123456789</code>",
                parse_mode="HTML",
            )
            return
        user_id = uid
        display = f"{name} (ID: {user_id})"

    added = await add_user_to_banlist(message.chat.id, user_id, added_by=message.from_user.id)
    if added:
        await message.answer(
            f"🚫 <b>ID {_html.escape(str(user_id))} добавлен в ЧС чата.</b>\n"
            f"При попытке вернуться бот заблокирует автоматически.",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"⚠️ ID {user_id} уже в чёрном списке.", parse_mode="HTML")


@router.message(BotCommand("юзразбан", "usrunban", "разбанюзер"), RankFilter("moderator"))
async def cmd_user_unban(message: Message, cmd_args: str):
    """Убрать Telegram ID из чёрного списка чата."""
    raw = (cmd_args or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(
            "❌ Укажи числовой ID.\n"
            "Пример: <code>бот юзразбан 123456789</code>",
            parse_mode="HTML",
        )
        return
    user_id = int(raw)
    removed = await remove_user_from_banlist(message.chat.id, user_id)
    if removed:
        await message.answer(f"✅ ID {user_id} убран из ЧС чата.", parse_mode="HTML")
    else:
        await message.answer(f"❌ ID {user_id} не найден в ЧС.", parse_mode="HTML")


@router.message(BotCommand("юзбаны", "usrbans", "чспользователей"), RankFilter("moderator"))
async def cmd_user_banlist(message: Message, cmd_args: str):
    """Показать чёрный список пользователей по ID для этого чата."""
    import html as _html
    rows = await get_chat_banlist_users(message.chat.id, limit=50)
    if not rows:
        await message.answer("📋 Чёрный список по ID пуст.")
        return

    lines = [f"🚫 <b>ЧС по ID ({len(rows)} чел.):</b>\n"]
    for r in rows:
        name = _html.escape(r.get("full_name") or "")
        uname = f" @{_html.escape(r['username'])}" if r.get("username") else ""
        added = (r.get("added_at") or "")[:10]
        display = f"{name}{uname}".strip() or "—"
        lines.append(f"  • <code>{r['user_id']}</code> {display} — {added}")

    await message.answer("\n".join(lines), parse_mode="HTML")
