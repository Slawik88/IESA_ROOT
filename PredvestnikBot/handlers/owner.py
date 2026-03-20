import html
import re
import pathlib

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    add_allowed_group, get_allowed_groups, get_chat_members, get_user,
    get_user_stats, remove_allowed_group, set_rank_in_chat, set_user_stat_in_chat,
    add_admin_group, remove_admin_group, get_admin_groups,
    add_xp_in_chat,
    # Channel types
    set_channel_type, remove_channel_type, get_channel_type, get_all_channel_types,
    # Community roles
    add_community_role, remove_community_role, get_community_roles,
    assign_community_role, revoke_community_role, get_user_community_roles,
    get_role_holders,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import resolve_target, user_mention
from utils.ranks import rank_level, rank_name

_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.py"


def _write_whitelist_to_config(groups: list[int]) -> bool:
    """Overwrite the ALLOWED_GROUPS line in config.py. Returns True on success."""
    try:
        content = _CONFIG_PATH.read_text(encoding="utf-8")
        if groups:
            ids_str = ", ".join(str(g) for g in sorted(groups))
            new_val = f"ALLOWED_GROUPS: set[int] = {{{ids_str}}}"
        else:
            new_val = "ALLOWED_GROUPS: set[int] = set()"
        new_content, n = re.subn(
            r"ALLOWED_GROUPS\s*:\s*set\[int\]\s*=\s*[^\n]*",
            new_val,
            content,
        )
        if n == 0:
            return False
        _CONFIG_PATH.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False

router = Router()

# ─── Фильтрация по ролям для колл-команды ─────────────────────────────────────
# Ключ — токен после «бот колл» (со знаком # или без)
# Значение — список рангов для фильтрации, None = все
_ROLE_TOKENS: dict[str, list[str] | None] = {
    "#все":     None,
    "#all":     None,
    "#юзеры":   ["user"],
    "#users":   ["user"],
    "#модеры":  ["moderator"],
    "#moder":   ["moderator"],
    "#хелперы": ["moderator"],  # алиас для обратной совместимости
    "#админыжр":  ["admin_junior"],
    "#junioradmin": ["admin_junior"],
    "#админстар":  ["admin_senior"],
    "#senioradmin": ["admin_senior"],
    "#стафф":   ["moderator", "admin_junior", "admin_senior", "co_owner", "owner", "developer",
                  "helper", "admin"],  # + обратная совместимость
    "#staff":   ["moderator", "admin_junior", "admin_senior", "co_owner", "owner", "developer",
                  "helper", "admin"],
    "#админы":  ["admin_junior", "admin_senior", "co_owner", "owner", "developer", "admin"],
    "#admins":  ["admin_junior", "admin_senior", "co_owner", "owner", "developer", "admin"],
    "#admin":   ["admin_junior", "admin_senior", "co_owner", "owner", "developer", "admin"],
}


def _role_label(ranks: list[str] | None) -> str:
    if ranks is None:
        return "все участники"
    first = ranks[0]
    if "user" in ranks and len([r for r in ranks if r in ("user",)]) == len(ranks):
        return "👤 Участники"
    if first in ("moderator", "helper") and "developer" in ranks:
        return "👮 Стафф (модер+)"
    if first in ("admin_junior", "admin"):
        return "⚡ Админы+"
    if first == "admin_senior":
        return "💎 Админ Старший+"
    if first == "moderator":
        return "🛡 Модераторы"
    return ", ".join(ranks)


@router.message(BotCommand("совладелец", "coowner", "setowner"), RankFilter("owner"))
async def cmd_set_coowner(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    target_stats = await get_user_stats(uid, message.chat.id)
    if target_stats and rank_level(target_stats["rank"]) >= rank_level("owner"):
        await message.answer("❌ Нельзя изменить ранг владельца или выше.")
        return

    await set_rank_in_chat(uid, message.chat.id, "co_owner")
    await message.answer(
        f"👑 {user_mention(uid, name)} назначен {rank_name('co_owner')}!",
        parse_mode="HTML",
    )


@router.message(BotCommand("рассылка", "broadcast", "колл", "call"), RankFilter("owner"))
async def cmd_broadcast(message: Message, bot: Bot, cmd_args: str):
    args = cmd_args.strip()

    # Парсим необязательный фильтр ролей (первый токен начинается с #)
    ranks_filter: list[str] | None = None   # None = не задан → все
    filter_set = False
    text = args

    if args:
        first, *rest = args.split(maxsplit=1)
        if first.lower() in _ROLE_TOKENS:
            ranks_filter = _ROLE_TOKENS[first.lower()]
            filter_set = True
            text = rest[0] if rest else ""

    # Получить участников этого чата (из cleanup_counts)
    members = await get_chat_members(message.chat.id, ranks=ranks_filter)

    if not members:
        label = _role_label(ranks_filter) if filter_set else "все участники"
        await message.answer(
            f"❌ Нет участников для тега ({label}).\n"
            f"<i>Бот видит только тех, кто написал хотя бы одно сообщение.</i>",
            parse_mode="HTML",
        )
        return

    label = _role_label(ranks_filter) if filter_set else "все участники"
    header_parts = [f"📢 <b>Внимание — {label}!</b>"]
    if text:
        header_parts.append(f"\n{text}")
    header = "\n".join(header_parts)

    # Отправляем упоминания батчами
    from config import BROADCAST_BATCH
    for i in range(0, len(members), BROADCAST_BATCH):
        batch = members[i : i + BROADCAST_BATCH]
        mentions = " ".join(user_mention(u["user_id"], u["full_name"]) for u in batch)
        chunk = f"{header}\n\n{mentions}" if i == 0 else mentions
        await message.answer(chunk, parse_mode="HTML")

    # Удаляем исходную команду чтобы не засорять чат (не критично, игнорируем ошибку)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(BotCommand("разработчик", "developer", "devinfo"), RankFilter("developer"))
async def cmd_developer(message: Message, cmd_args: str):
    from database.db import get_chat_stats_for_chat
    stats = await get_chat_stats_for_chat(message.chat.id)
    await message.answer(
        f"🛠 <b>Панель разработчика</b>\n\n"
        f"👥 Участников в базе: {stats['total']}\n"
        f"💬 Всего сообщений: {stats['messages']}\n"
        f"⛔ Заблокировано: {stats['banned']}\n"
        f"👮 Администраторов: {stats['staff']}",
        parse_mode="HTML",
    )


# ─── Белый список групп (developer only) ──────────────────────────────────────

@router.message(BotCommand("разрешить", "allow", "whitelist"), RankFilter("developer"))
async def cmd_allow_group(message: Message, cmd_args: str):
    """Добавить группу в белый список. Без аргумента — текущую группу."""
    arg = cmd_args.strip()
    if arg:
        try:
            chat_id = int(arg)
        except ValueError:
            await message.answer("❌ Укажи числовой chat_id или вызови без аргумента в нужной группе.")
            return
    elif message.chat.type in ("group", "supergroup"):
        chat_id = message.chat.id
    else:
        await message.answer("❌ Укажи chat_id группы: <code>бот разрешить -100123456</code>", parse_mode="HTML")
        return

    await add_allowed_group(chat_id)
    all_groups = await get_allowed_groups()
    saved = _write_whitelist_to_config(all_groups)
    saved_note = " (сохранено в config.py)" if saved else ""
    await message.answer(
        f"✅ Группа <code>{chat_id}</code> добавлена в белый список{saved_note}.",
        parse_mode="HTML",
    )


@router.message(BotCommand("запретить", "disallow", "unwhitelist"), RankFilter("developer"))
async def cmd_disallow_group(message: Message, cmd_args: str):
    """Убрать группу из белого списка. Без аргумента — текущую группу."""
    arg = cmd_args.strip()
    if arg:
        try:
            chat_id = int(arg)
        except ValueError:
            await message.answer("❌ Укажи числовой chat_id.")
            return
    elif message.chat.type in ("group", "supergroup"):
        chat_id = message.chat.id
    else:
        await message.answer("❌ Укажи chat_id группы: <code>бот запретить -100123456</code>", parse_mode="HTML")
        return

    await remove_allowed_group(chat_id)
    all_groups = await get_allowed_groups()
    saved = _write_whitelist_to_config(all_groups)
    saved_note = " (сохранено в config.py)" if saved else ""
    await message.answer(
        f"🚫 Группа <code>{chat_id}</code> убрана из белого списка{saved_note}.",
        parse_mode="HTML",
    )


@router.message(BotCommand("группы", "groups", "whitelist_list"), RankFilter("developer"))
async def cmd_list_groups(message: Message, cmd_args: str):
    """Показать все разрешённые группы."""
    groups = await get_allowed_groups()
    if not groups:
        await message.answer(
            "📋 Белый список пуст — бот работает во <b>всех</b> группах.\n\n"
            "<i>Добавить текущую: <code>бот разрешить</code>\n"
            "Добавить по ID: <code>бот разрешить -100123456</code></i>",
            parse_mode="HTML",
        )
        return

    from database.db import get_active_chats
    chats = await get_active_chats()
    chat_map = {c["chat_id"]: c["title"] for c in chats}

    lines = [f"📋 <b>Разрешённые группы ({len(groups)}):</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for cid in sorted(groups):
        title = chat_map.get(cid, "—")
        lines.append(f"  • <code>{cid}</code>  {title}")
        buttons.append([InlineKeyboardButton(
            text=f"❌ {title[:25] if title != '—' else str(cid)}",
            callback_data=f"rmg:{cid}",
        )])

    lines.append("\n<i>бот запретить — убрать текущую группу из списка</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("rmg:"))
async def cb_remove_group(callback: CallbackQuery):
    caller_stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
    caller_rank = caller_stats["rank"] if caller_stats else "user"
    if rank_level(caller_rank) < rank_level("developer"):
        await callback.answer("❌ Недостаточно прав.", show_alert=True)
        return

    chat_id = int(callback.data.split(":")[1])
    await remove_allowed_group(chat_id)
    all_groups = await get_allowed_groups()
    _write_whitelist_to_config(all_groups)

    await callback.answer(f"✅ Группа {chat_id} убрана")

    # Обновить список
    if not all_groups:
        try:
            await callback.message.edit_text(
                "📋 Белый список пуст — бот работает во <b>всех</b> группах.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    from database.db import get_active_chats
    chats = await get_active_chats()
    chat_map = {c["chat_id"]: c["title"] for c in chats}

    lines = [f"📋 <b>Разрешённые группы ({len(all_groups)}):</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for cid in sorted(all_groups):
        title = chat_map.get(cid, "—")
        lines.append(f"  • <code>{cid}</code>  {title}")
        buttons.append([InlineKeyboardButton(
            text=f"❌ {title[:25] if title != '—' else str(cid)}",
            callback_data=f"rmg:{cid}",
        )])

    lines.append("\n<i>бот запретить — убрать текущую группу из списка</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    try:
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass


# ─── Developer: редактор данных пользователей ──────────────────────────────

_STAT_MAP = {
    "сообщения":   ("message_count", int),
    "msgs":        ("message_count", int),
    "xp":          ("xp", int),
    "опыт":        ("xp", int),
    "уровень":     ("level", int),
    "level":       ("level", int),
    "репутация":   ("reputation", int),
    "rep":         ("reputation", int),
    "варны":       ("warns", int),
    "warns":       ("warns", int),
    "бан":         ("is_banned", int),
    "ban":         ("is_banned", int),
    "bio":         ("bio", str),
    "биография":   ("bio", str),
    "титул":       ("custom_title", str),
    "title":       ("custom_title", str),
}


@router.message(BotCommand("сетюзер", "setuser", "редактор", "edituser"), RankFilter("developer"))
async def cmd_set_user(message: Message, cmd_args: str):
    """Developer-only: set any user stat.
    Синтаксис: бот сетюзер @user поле значение
    Пример:    бот сетюзер @makss xp 5000
    """
    if not cmd_args:
        # Показываем инлайн-кнопки с полями
        buttons = []
        row = []
        _labels = {
            "xp": "💠 XP",
            "уровень": "🌟 Уровень",
            "сообщения": "💬 Сообщения",
            "репутация": "⭐ Репутация",
            "варны": "⚠️ Варны",
            "бан": "🔴 Бан",
            "bio": "📝 Био",
            "титул": "🎖 Титул",
        }
        for i, (key, label) in enumerate(_labels.items()):
            row.append(InlineKeyboardButton(
                text=label, callback_data=f"su:f:{key}",
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        await message.answer(
            "🛠 <b>Редактор данных пользователя</b>\n\n"
            "Синтаксис:\n"
            "<code>бот сетюзер @user поле значение</code>\n\n"
            "Нажми кнопку для подсказки поля, или введи команду целиком.\n\n"
            "Примеры:\n"
            "<code>бот сетюзер @makss xp 5000</code>\n"
            "<code>бот сетюзер @makss титул 🌟 Stardish Admin</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        return

    parts = cmd_args.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "❌ Недостаточно аргументов.\n"
            "Пример: <code>бот сетюзер @user xp 5000</code>",
            parse_mode="HTML",
        )
        return

    target_str, field_key, raw_value = parts
    uid, name, _ = await resolve_target(message, target_str)
    if uid is None:
        await message.answer(name)
        return

    field_info = _STAT_MAP.get(field_key.lower())
    if not field_info:
        fields = " | ".join(sorted(_STAT_MAP.keys()))
        await message.answer(
            f"❌ Неизвестное поле «{field_key}».\n"
            f"Доступные: <code>{fields}</code>",
            parse_mode="HTML",
        )
        return

    db_field, cast = field_info
    try:
        value = cast(raw_value)
    except (ValueError, TypeError):
        await message.answer(
            f"❌ Неверное значение «{raw_value}» для поля «{field_key}»."
        )
        return

    ok = await set_user_stat_in_chat(uid, message.chat.id, db_field, value)
    if ok:
        await message.answer(
            f"✅ <b>{name}</b>: {field_key} → <code>{value}</code>",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Не удалось обновить — поле не разрешено.")


@router.callback_query(F.data.startswith("su:f:"))
async def cb_setuser_field_hint(callback: CallbackQuery):
    field = callback.data.split(":", 2)[2]
    _hints = {
        "xp": "<code>бот сетюзер @user xp 5000</code>",
        "уровень": "<code>бот сетюзер @user уровень 10</code>",
        "сообщения": "<code>бот сетюзер @user сообщения 300</code>",
        "репутация": "<code>бот сетюзер @user репутация 50</code>",
        "варны": "<code>бот сетюзер @user варны 0</code>",
        "бан": "<code>бот сетюзер @user бан 1</code>  (0 = разбан)",
        "bio": "<code>бот сетюзер @user bio Текст биографии</code>",
        "титул": "<code>бот сетюзер @user титул 🌟 Мой титул</code>",
    }
    hint = _hints.get(field, "неизвестное поле")
    await callback.answer(f"Пример: {field}", show_alert=False)
    await callback.message.answer(
        f"📝 Введи команду:\n{hint}",
        parse_mode="HTML",
    )


@router.message(BotCommand("прибавитьxp", "addxp"), RankFilter("developer"))
async def cmd_add_xp_dev(message: Message, cmd_args: str):
    """Developer-only: add XP to user (positive or negative).
    Пример: бот прибавитьxp @user 500
    """
    parts = cmd_args.split(maxsplit=1) if cmd_args else []
    if len(parts) < 2:
        await message.answer(
            "❌ Укажи пользователя и количество XP.\n"
            "Пример: <code>бот прибавитьxp @user 500</code>",
            parse_mode="HTML",
        )
        return
    uid, name, _ = await resolve_target(message, parts[0])
    if uid is None:
        await message.answer(name)
        return
    try:
        delta = int(parts[1])
    except ValueError:
        await message.answer("❌ Укажи целое число.")
        return

    user_stats = await get_user_stats(uid, message.chat.id)
    old_xp = (user_stats["xp"] or 0) if user_stats else 0
    new_xp = max(0, old_xp + delta)
    await set_user_stat_in_chat(uid, message.chat.id, "xp", new_xp)
    sign = "+" if delta >= 0 else ""
    await message.answer(
        f"✅ <b>{name}</b>: XP {sign}{delta} → <b>{new_xp}</b>",
        parse_mode="HTML",
    )


@router.message(BotCommand("settitle", "сеттитул", "кастомтитул"), RankFilter("developer"))
async def cmd_set_title(message: Message, cmd_args: str):
    """Установить кастомный отображаемый титул пользователю (визуально заменяет ранг в профиле).
    Пример: бот сеттитул @user 🌟 Stardish Admin
    """
    parts = cmd_args.split(maxsplit=1) if cmd_args else []
    if not parts:
        await message.answer(
            "❌ Укажи пользователя и титул.\n"
            "Пример: <code>бот сеттитул @user 🌟 Stardish Admin</code>\n"
            "Сброс: <code>бот сеттитул @user -</code>",
            parse_mode="HTML",
        )
        return
    uid, name, _ = await resolve_target(message, parts[0])
    if uid is None:
        await message.answer(name)
        return
    title_text = parts[1].strip() if len(parts) > 1 else ""
    if title_text == "-":
        title_text = None
    await set_user_stat_in_chat(uid, message.chat.id, "custom_title", title_text)
    if title_text:
        await message.answer(
            f"✅ <b>{name}</b>: кастомный титул → <b>{title_text}</b>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"✅ <b>{name}</b>: кастомный титул сброшен.",
            parse_mode="HTML",
        )


# ─── Админ-группы (системные уведомления) ────────────────────────────────────

@router.message(BotCommand("админгруппа", "adminchat", "admingroup"), RankFilter("developer"))
async def cmd_add_admin_group(message: Message, cmd_args: str):
    """Добавить группу администрации. Без аргумента — текущую группу."""
    arg = cmd_args.strip()
    if arg:
        try:
            chat_id = int(arg)
        except ValueError:
            await message.answer(
                "❌ Укажи числовой chat_id.\n"
                "Пример: <code>бот админгруппа -100123456</code>",
                parse_mode="HTML",
            )
            return
    elif message.chat.type in ("group", "supergroup"):
        chat_id = message.chat.id
    else:
        await message.answer(
            "❌ Укажи chat_id или вызови в нужной группе.\n"
            "Пример: <code>бот админгруппа -100123456</code>",
            parse_mode="HTML",
        )
        return

    await add_admin_group(chat_id)
    await message.answer(
        f"✅ Группа <code>{chat_id}</code> добавлена как админ-группа.\n"
        f"Сюда будут приходить системные уведомления.",
        parse_mode="HTML",
    )


@router.message(BotCommand("удадмингруппу", "removeadminchat", "удалитьадмингруппу"), RankFilter("developer"))
async def cmd_remove_admin_group(message: Message, cmd_args: str):
    """Убрать группу администрации."""
    arg = cmd_args.strip()
    if arg:
        try:
            chat_id = int(arg)
        except ValueError:
            await message.answer("❌ Укажи числовой chat_id.", parse_mode="HTML")
            return
    elif message.chat.type in ("group", "supergroup"):
        chat_id = message.chat.id
    else:
        await message.answer("❌ Укажи chat_id группы.", parse_mode="HTML")
        return

    await remove_admin_group(chat_id)
    await message.answer(
        f"🚫 Группа <code>{chat_id}</code> удалена из админ-групп.",
        parse_mode="HTML",
    )


@router.message(BotCommand("админгруппы", "adminchats", "admingroups"), RankFilter("developer"))
async def cmd_list_admin_groups(message: Message, cmd_args: str):
    """Показать все группы администрации."""
    groups = await get_admin_groups()
    if not groups:
        await message.answer(
            "📋 Админ-группы не настроены.\n"
            "Системные уведомления будут приходить в личку администраторам.\n\n"
            "<i>Добавить: <code>бот админгруппа</code> (в нужной группе)\n"
            "Или: <code>бот админгруппа -100123456</code></i>",
            parse_mode="HTML",
        )
        return

    from database.db import get_active_chats
    chats = await get_active_chats()
    chat_map = {c["chat_id"]: c["title"] for c in chats}

    lines = [f"📋 <b>Админ-группы ({len(groups)}):</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for cid in sorted(groups):
        title = chat_map.get(cid, "—")
        lines.append(f"  • <code>{cid}</code>  {title}")
        buttons.append([InlineKeyboardButton(
            text=f"❌ {title[:25] if title != '—' else str(cid)}",
            callback_data=f"rag:{cid}",
        )])

    lines.append("\n<i>Сюда бот отправляет репорты, нарушения и системную информацию.</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("rag:"))
async def cb_remove_admin_group(callback: CallbackQuery):
    # Developer-only check
    uid = callback.from_user.id
    cid = callback.message.chat.id
    stats = await get_user_stats(uid, cid)
    if not stats or rank_level(stats["rank"]) < rank_level("developer"):
        await callback.answer("⛔ Только для разработчика.", show_alert=True)
        return

    raw = callback.data.split(":", 1)[1]
    try:
        chat_id = int(raw)
    except ValueError:
        await callback.answer("❌ Ошибка")
        return

    await remove_admin_group(chat_id)

    # Refresh the list
    groups = await get_admin_groups()
    if not groups:
        try:
            await callback.message.edit_text(
                "📋 Все админ-группы удалены.\n"
                "Системные уведомления будут приходить в личку администраторам.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await callback.answer("✅ Удалена")
        return

    from database.db import get_active_chats
    chats = await get_active_chats()
    chat_map = {c["chat_id"]: c["title"] for c in chats}

    lines = [f"📋 <b>Админ-группы ({len(groups)}):</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for cid in sorted(groups):
        title = chat_map.get(cid, "—")
        lines.append(f"  • <code>{cid}</code>  {title}")
        buttons.append([InlineKeyboardButton(
            text=f"❌ {title[:25] if title != '—' else str(cid)}",
            callback_data=f"rag:{cid}",
        )])

    lines.append("\n<i>Сюда бот отправляет репорты, нарушения и системную информацию.</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    try:
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"✅ Группа {chat_id} удалена")


# ─────────────────────── CHANNEL TYPES ────────────────────────────────────────
# бот канал правила|роли|основной [chat_id]
# бот канал удалить правила|роли|основной
# бот каналы

_CHANNEL_TYPE_LABELS = {
    "rules": "📜 Правила+Роли",
    "main":  "💬 Основной чат",
}


@router.message(BotCommand("канал"), RankFilter("developer"))
async def cmd_set_channel(message: Message) -> None:
    """бот канал <тип> [chat_id]  — назначить канал по типу.
    Типы: правила, основной.
    Если chat_id не указан — используется текущий чат.
    """
    args = (message.text or "").split()[2:]  # skip "бот" "канал"
    if not args:
        await message.reply(
            "❓ Использование:\n"
            "  <code>бот канал правила [chat_id]</code>\n"
            "  <code>бот канал основной [chat_id]</code>\n"
            "  <code>бот канал удалить правила|основной</code>",
            parse_mode="HTML",
        )
        return

    type_arg = args[0].lower()

    # Handle remove sub-command
    if type_arg == "удалить":
        if len(args) < 2:
            await message.reply("❓ Укажи тип: <code>бот канал удалить правила|основной</code>", parse_mode="HTML")
            return
        type_key = _resolve_channel_type(args[1].lower())
        if not type_key:
            await message.reply("❌ Неизвестный тип. Используй: <b>правила</b> или <b>основной</b>.", parse_mode="HTML")
            return
        await remove_channel_type(type_key)
        label = _CHANNEL_TYPE_LABELS.get(type_key, type_key)
        await message.reply(f"✅ Канал «{label}» удалён из настроек.", parse_mode="HTML")
        return

    type_key = _resolve_channel_type(type_arg)
    if not type_key:
        await message.reply("❌ Неизвестный тип. Используй: <b>правила</b> или <b>основной</b>.", parse_mode="HTML")
        return

    # Determine chat_id
    if len(args) >= 2:
        try:
            chat_id = int(args[1])
        except ValueError:
            await message.reply("❌ chat_id должен быть числом.", parse_mode="HTML")
            return
    else:
        chat_id = message.chat.id

    await set_channel_type(type_key, chat_id)
    label = _CHANNEL_TYPE_LABELS.get(type_key, type_key)
    await message.reply(f"✅ <b>{label}</b> → <code>{chat_id}</code>", parse_mode="HTML")


def _resolve_channel_type(arg: str) -> str | None:
    mapping = {
        "правила": "rules",
        "роли": "rules",
        "основной": "main",
    }
    return mapping.get(arg)


@router.message(BotCommand("каналы"), RankFilter("developer"))
async def cmd_list_channels(message: Message) -> None:
    """бот каналы — показать все настроенные типы каналов."""
    channels = await get_all_channel_types()
    if not channels:
        await message.reply("ℹ️ Каналы не настроены. Используй <code>бот канал правила|основной [id]</code>.", parse_mode="HTML")
        return

    lines = ["📡 <b>Настроенные каналы:</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        label = _CHANNEL_TYPE_LABELS.get(ch["type"], ch["type"])
        lines.append(f"  {label}: <code>{ch['chat_id']}</code>")
        buttons.append([InlineKeyboardButton(text=f"❌ Удалить {label}", callback_data=f"ct:del:{ch['type']}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("ct:del:"))
async def cb_remove_channel_type(callback: CallbackQuery) -> None:
    # Developer-only check
    uid = callback.from_user.id
    cid = callback.message.chat.id
    stats = await get_user_stats(uid, cid)
    if not stats or rank_level(stats["rank"]) < rank_level("developer"):
        await callback.answer("⛔ Только для разработчика.", show_alert=True)
        return

    type_key = callback.data.split(":", 2)[2]
    label = _CHANNEL_TYPE_LABELS.get(type_key, type_key)
    await remove_channel_type(type_key)

    channels = await get_all_channel_types()
    if not channels:
        try:
            await callback.message.edit_text("ℹ️ Все каналы удалены.", parse_mode="HTML")
        except Exception:
            pass
        await callback.answer(f"✅ {label} удалён")
        return

    lines = ["📡 <b>Настроенные каналы:</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        lbl = _CHANNEL_TYPE_LABELS.get(ch["type"], ch["type"])
        lines.append(f"  {lbl}: <code>{ch['chat_id']}</code>")
        buttons.append([InlineKeyboardButton(text=f"❌ Удалить {lbl}", callback_data=f"ct:del:{ch['type']}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"✅ {label} удалён")


# ─────────────────────── COMMUNITY ROLES ─────────────────────────────────────
# бот рольдобавить [emoji] <название> [описание]
# бот рольудалить <название>
# бот роли
# бот выдатьроль <@user|reply> <название>
# бот снятьроль <@user|reply> <название>
# бот мойроли
# бот ролипользователя <@user|reply>


@router.message(BotCommand("рольдобавить"), RankFilter("owner"))
async def cmd_add_role(message: Message) -> None:
    """бот рольдобавить [emoji] <название> [описание]"""
    args = (message.text or "").split(maxsplit=2)[1:]  # drop "бот"
    # args[0] == "рольдобавить"
    rest = " ".join(args[1:]).strip() if len(args) >= 2 else ""
    if not rest:
        await message.reply("❓ Использование: <code>бот рольдобавить [эмодзи] название [описание]</code>", parse_mode="HTML")
        return

    parts = rest.split(None, 2)
    # Detect if first token is an emoji (single grapheme cluster, not alnum)
    if parts and not parts[0][0].isalnum():
        emoji = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        description = parts[2] if len(parts) > 2 else ""
    else:
        emoji = ""
        name = parts[0]
        description = " ".join(parts[1:]) if len(parts) > 1 else ""

    if not name:
        await message.reply("❌ Название роли не может быть пустым.", parse_mode="HTML")
        return

    ok = await add_community_role(name, emoji, description)
    if not ok:
        await message.reply(f"❌ Роль <b>{name}</b> уже существует.", parse_mode="HTML")
        return

    display = f"{emoji} {name}".strip()
    await message.reply(f"✅ Роль <b>{html.escape(display)}</b> добавлена!", parse_mode="HTML")


@router.message(BotCommand("рольудалить"), RankFilter("owner"))
async def cmd_remove_role(message: Message) -> None:
    """бот рольудалить <название>"""
    args = (message.text or "").split(maxsplit=2)
    name = args[2].strip() if len(args) >= 3 else ""
    if not name:
        await message.reply("❓ Использование: <code>бот рольудалить название</code>", parse_mode="HTML")
        return

    ok = await remove_community_role(name)
    if not ok:
        await message.reply(f"❌ Роль <b>{html.escape(name)}</b> не найдена.", parse_mode="HTML")
        return
    await message.reply(f"✅ Роль <b>{html.escape(name)}</b> удалена.", parse_mode="HTML")


@router.message(BotCommand("роли"))
async def cmd_list_roles(message: Message) -> None:
    """бот роли — список всех ролей с числом участников."""
    roles = await get_community_roles()
    if not roles:
        await message.reply("ℹ️ Роли ещё не созданы. Используй <code>бот рольдобавить</code>.", parse_mode="HTML")
        return

    lines = ["🎭 <b>Роли сообщества:</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for r in roles:
        display = f"{r['emoji']} {r['name']}".strip() if r.get("emoji") else r["name"]
        count = r.get("holder_count", 0)
        status = f"({count} чел.)" if count else "<i>свободна</i>"
        lines.append(f"  <b>{html.escape(display)}</b> — {status}")
        if count:
            buttons.append([InlineKeyboardButton(
                text=f"👥 {display[:30]}",
                callback_data=f"rl:holders:{r['name']}",
            )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.reply("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("rl:holders:"))
async def cb_role_holders(callback: CallbackQuery) -> None:
    role_name = callback.data.split(":", 2)[2]
    holders = await get_role_holders(role_name)
    if not holders:
        await callback.answer("Роль никем не занята.", show_alert=True)
        return

    lines = [f"👥 <b>Участники с ролью «{role_name}»:</b>\n"]
    for h in holders:
        mention = f"<a href='tg://user?id={h['user_id']}'>{h.get('full_name') or str(h['user_id'])}</a>"
        lines.append(f"  • {mention}")

    try:
        await callback.message.reply("\n".join(lines), parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()


@router.message(BotCommand("выдатьроль"), RankFilter("admin_junior"))
async def cmd_assign_role(message: Message) -> None:
    """бот выдатьроль <@user|reply> <название роли>"""
    args = (message.text or "").split(maxsplit=2)
    rest = args[2].strip() if len(args) >= 3 else ""

    uid, fname, role_name = await _parse_target_and_role(message, rest)
    if uid is None:
        return

    result = await assign_community_role(uid, role_name)
    mention = user_mention(uid, fname)
    safe_role = html.escape(role_name)
    if result == "not_found":
        await message.reply(f"❌ Роль <b>{safe_role}</b> не найдена.", parse_mode="HTML")
    elif result == "already":
        await message.reply(f"ℹ️ У {mention} уже есть роль <b>{safe_role}</b>.", parse_mode="HTML")
    elif result == "taken":
        # Find who currently holds the role
        holders = await get_role_holders(role_name)
        if holders:
            holder = holders[0]
            current = user_mention(holder["user_id"], holder["full_name"] or str(holder["user_id"]))
            await message.reply(
                f"❌ Роль <b>{safe_role}</b> уже занята — {current}.\n"
                f"Сначала сними её командой: <code>бот снятьроль @user {html.escape(role_name)}</code>",
                parse_mode="HTML",
            )
        else:
            await message.reply(f"❌ Роль <b>{safe_role}</b> уже занята другим участником.", parse_mode="HTML")
    else:
        await message.reply(f"✅ {mention} получил роль <b>{safe_role}</b>!", parse_mode="HTML")


@router.message(BotCommand("снятьроль"), RankFilter("admin_junior"))
async def cmd_revoke_role(message: Message) -> None:
    """бот снятьроль <@user|reply> <название роли>"""
    args = (message.text or "").split(maxsplit=2)
    rest = args[2].strip() if len(args) >= 3 else ""

    uid, fname, role_name = await _parse_target_and_role(message, rest)
    if uid is None:
        return

    ok = await revoke_community_role(uid, role_name)
    mention = user_mention(uid, fname)
    safe_role = html.escape(role_name)
    if not ok:
        await message.reply(f"❌ Роль <b>{safe_role}</b> не найдена или не была у {mention}.", parse_mode="HTML")
    else:
        await message.reply(f"✅ Роль <b>{safe_role}</b> снята с {mention}.", parse_mode="HTML")


@router.message(BotCommand("мойроли"))
async def cmd_my_roles(message: Message) -> None:
    """бот мойроли — свои роли."""
    await _show_user_roles(message, message.from_user.id,
                           message.from_user.first_name or str(message.from_user.id))


@router.message(BotCommand("ролипользователя"))
async def cmd_user_roles(message: Message) -> None:
    """бот ролипользователя <@user|reply>"""
    args = (message.text or "").split(maxsplit=2)
    rest = args[2].strip() if len(args) >= 3 else ""
    uid, fname, _rem = await resolve_target(message, rest)
    if uid is None:
        await message.reply("❓ Укажи пользователя: <code>бот ролипользователя @user</code> или ответь на его сообщение.", parse_mode="HTML")
        return
    await _show_user_roles(message, uid, fname)


async def _show_user_roles(message: Message, user_id: int, name: str) -> None:
    roles = await get_user_community_roles(user_id)
    safe_name = html.escape(name)
    if not roles:
        await message.reply(f"ℹ️ У <b>{safe_name}</b> нет ролей.", parse_mode="HTML")
        return
    lines = [f"🎭 <b>Роли участника {safe_name}:</b>\n"]
    for r in roles:
        display = f"{r['emoji']} {r['name']}".strip() if r.get("emoji") else r["name"]
        lines.append(f"  • <b>{html.escape(display)}</b>")
    await message.reply("\n".join(lines), parse_mode="HTML")


async def _parse_target_and_role(
    message: Message, rest: str
) -> tuple:
    """Parse '<target> <role_name>' from rest string (reply counts as target too).
    Returns (user_id, full_name, role_name) or (None, None, None) on error.
    """
    if not rest and not message.reply_to_message:
        await message.reply(
            "❓ Укажи пользователя и название роли.\n"
            "Пример: <code>бот выдатьроль @user Геймер</code>",
            parse_mode="HTML",
        )
        return None, None, None

    # If replying, rest is the role name
    if message.reply_to_message:
        role_name = rest.strip()
        uid, fname, _rem = await resolve_target(message, "")
    else:
        # First token may be @username or user_id, rest is role
        parts = rest.split(None, 1)
        if len(parts) < 2:
            await message.reply("❓ Укажи <b>пользователя</b> и <b>название роли</b>.", parse_mode="HTML")
            return None, None, None
        uid, fname, _rem = await resolve_target(message, parts[0])
        role_name = parts[1].strip()

    if uid is None:
        await message.reply("❌ Пользователь не найден.", parse_mode="HTML")
        return None, None, None
    if not role_name:
        await message.reply("❌ Укажи название роли.", parse_mode="HTML")
        return None, None, None

    return uid, fname, role_name
