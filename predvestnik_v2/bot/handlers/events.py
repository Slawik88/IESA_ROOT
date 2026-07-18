import asyncio
import random
import time

from aiogram import Router, types, Bot
from aiogram.filters.callback_data import CallbackData
from aiogram.types import ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from core.constants import (
    CHEST_REWARDS_BY_POSITION, CHEST_TOP3_BONUS_ITEM, CHEST_MAX_CLAIMANTS,
)
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import users as users_repo
from infrastructure.repositories.blacklist import is_in_chat_blacklist
from infrastructure.repositories.chest_events import (
    get_active_chest, close_chest, update_last_chest_at,
)
from services.utils import resolve_display_name
from bot.keyboards.cta import MINIAPP_URL

router = Router(name="events_router")

_LEAVE_MSG_TTL = 600  # кнопки активны 10 минут


class LeaveCB(CallbackData, prefix="leave"):
    action: str        # "blacklist" | "close"
    user_id: int
    sent_at: int = 0   # unix timestamp отправки — для TTL проверки


# ── Welcome messages diversity ────────────────────────────────────────────────

# UX_AUDIT Б5/Б20: тон — «тихая мистика» бренда, но предельно ясные первые шаги
# (короткий текст, нумерованные действия, кнопка мини-аппа). Никаких «⚡ Бот активирован!».
_BOT_WELCOME_MESSAGES = [
    (
        "🌘 <b>Предвестник вошёл в этот чат.</b>\n\n"
        "Теперь здесь идёт игра: питомцы, золото, кланы, бои.\n\n"
        "📌 <b>Три шага:</b>\n"
        "1️⃣ <b>бот я</b> — увидишь свой профиль\n"
        "2️⃣ <b>бот стрик</b> — ежедневная награда\n"
        "3️⃣ <b>бот помощь</b> — все команды\n\n"
        "<i>Владелец чата уже получил ранг 👑. Магазин, Казарма и бои — в мини-аппе (кнопка ниже).</i>"
    ),
    (
        "🕯 <b>Кто-то позвал — и Предвестник пришёл.</b>\n\n"
        "Я игровой бот: экономика, питомцы, гача, кланы.\n\n"
        "📌 <b>С чего начать:</b>\n"
        "· <b>бот я</b> — твоя карточка\n"
        "· <b>бот крутка</b> — первый питомец\n"
        "· <b>бот помощь</b> — всё остальное\n\n"
        "<i>Команды пишутся словом «бот» прямо в чат. Остальное — в мини-аппе (кнопка ниже).</i>"
    ),
    (
        "🌑 <b>В этом чате стало на одну тень больше.</b>\n\n"
        "Я — Предвестник: считаю Мору, выращиваю питомцев, слежу за порядком.\n\n"
        "📌 <b>Попробуй сразу:</b>\n"
        "· <b>бот стрик</b> — начни серию входов\n"
        "· <b>бот акция</b> — сделка дня\n"
        "· <b>бот помощь</b> — навигация\n\n"
        "<i>Администраторам: <b>бот настройки чата</b> — права и модули.</i>"
    ),
    (
        "🔮 <b>Шар показал этот чат — значит, мне сюда.</b>\n\n"
        "🐾 Питомцы · 💰 Экономика · 🛡 Модерация · 🎰 Гача\n\n"
        "Начни с <b>бот помощь</b> — там всё.\n"
        "Магазин, Казарма и бои — в мини-аппе (кнопка ниже).\n\n"
        "<i>Администраторам: <b>бот настройки чата</b>.</i>"
    ),
    (
        "✨ <b>Предвестник теперь среди вас.</b>\n\n"
        "📌 <b>Три первых шага:</b>\n"
        "1️⃣ <b>бот я</b> — твоя карточка\n"
        "2️⃣ <b>бот стрик</b> — серия входов и награды\n"
        "3️⃣ <b>бот крутка</b> — первый питомец\n\n"
        "<i>Всё остальное — <b>бот помощь</b> и мини-апп (кнопка ниже).</i>"
    ),
]

_USER_WELCOME_MESSAGES = [
    "🌘 <b>{name}</b>, тебя ждали. Напиши <b>бот я</b> — увидишь свой профиль.",
    "🕯 Свеча зажглась — <b>{name}</b> с нами. Начни с <b>бот стрик</b>: ежедневная награда.",
    "✨ <b>{name}</b>, добро пожаловать. <b>бот помощь</b> покажет, как тут всё устроено.",
    "🔮 Шар предсказал твоё появление, <b>{name}</b>. Попробуй <b>бот крутка</b> — первый питомец.",
    "🌑 Тень стала гуще: <b>{name}</b> здесь. Твоя карточка — <b>бот я</b>.",
]


def _welcome_kb() -> types.InlineKeyboardMarkup:
    """Кнопка мини-аппа в приветствии (UX_AUDIT Б5). В группах — только url-кнопка
    (web_app в группах даёт BUTTON_TYPE_INVALID)."""
    b = InlineKeyboardBuilder()
    b.button(text="🌐 Мини-апп: магазин, Казарма, бои", url=MINIAPP_URL)
    return b.as_markup()


async def _delayed_bot_welcome(bot: Bot, chat_id: int) -> None:
    """Send the bot's welcome message after a short delay. No DB needed."""
    await asyncio.sleep(2)
    text = random.choice(_BOT_WELCOME_MESSAGES)
    try:
        await bot.send_message(chat_id, text, reply_markup=_welcome_kb(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Bot welcome failed in {chat_id}: {e}")


# ── Main member status handler ────────────────────────────────────────────────

async def _bot_joined_chat(event: ChatMemberUpdated, db, bot: Bot) -> None:
    """Бот добавлен в чат: авто-ранг владельцу, настройки, приветствие."""
    chat_id = event.chat.id
    logger.info(f"Бот вошёл в чат {chat_id} ({event.chat.title})")

    # Авто-ранги (UX_AUDIT Б17): владельцу чата — 6, а также добавившему бота
    # Telegram-админу — 4 (Ст.Адм). Раньше ранг получал ТОЛЬКО «creator»: если
    # фаундер неактивен, бот оставался ненастраиваемым для реальных админов.
    # Самовосстановление в любой момент: «бот обновить права» (admin.py).
    async def _grant_rank(uid: int, uname, rank: int) -> None:
        await users_repo.update_user(db, uid, uname)
        await db.execute(
            "INSERT OR IGNORE INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, ?)",
            (uid, chat_id),
        )
        # Только повышение — вдруг у добавившего уже есть ранг выше
        await db.execute(
            "UPDATE user_chat_stats SET local_rank = ? "
            "WHERE user_tg_id = ? AND chat_tg_id = ? AND local_rank < ?",
            (rank, uid, chat_id, rank),
        )
        await db.commit()
        logger.info(f"Авто-ранг {rank} выдан {uid} в чате {chat_id}")

    try:
        admins = await bot.get_chat_administrators(chat_id)
        adder = event.from_user  # кто добавил бота
        for admin in admins:
            if admin.status == "creator":
                await _grant_rank(
                    admin.user.id, getattr(admin.user, "username", None), 6)
                break
        if adder:
            adder_status = next(
                (a.status for a in admins if a.user.id == adder.id), None)
            if adder_status == "administrator":
                await _grant_rank(
                    adder.id, getattr(adder, "username", None), 4)
    except Exception as e:
        logger.warning(f"Не удалось выдать авто-ранг в чате {chat_id}: {e}")

    # Ensure chat settings row exists + вернуть ивенты (могли выключиться при кике)
    chat_title = event.chat.title or ""
    await db.execute(
        "INSERT OR IGNORE INTO chat_settings (chat_id, chat_title) VALUES (?, ?)",
        (chat_id, chat_title),
    )
    await db.execute(
        "UPDATE chat_settings SET events_enabled = 1 WHERE chat_id = ?", (chat_id,)
    )
    await db.commit()

    # Send welcome message after 2-second delay (no DB needed in the task)
    asyncio.create_task(_delayed_bot_welcome(bot, chat_id))


@router.my_chat_member()
async def on_bot_status_changed(event: ChatMemberUpdated, db, bot: Bot):
    """Статус САМОГО бота приходит ТОЛЬКО через my_chat_member (chat_member —
    про других участников). Кик бота глушит ивенты чата, иначе шедулер
    сундуков ловит Forbidden каждый цикл (логи прода 2026-07-08)."""
    if event.chat.type == "private":
        return
    chat_id = event.chat.id
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status
    if new_status in ("left", "kicked"):
        await db.execute(
            "UPDATE chat_settings SET events_enabled = 0 WHERE chat_id = ?", (chat_id,)
        )
        await db.commit()
        logger.info(f"Бот удалён из чата {chat_id} — фоновые ивенты чата отключены")
        return
    if new_status in ("member", "administrator") and old_status in ("left", "kicked"):
        await _bot_joined_chat(event, db, bot)


@router.chat_member()
async def on_user_status_changed(event: ChatMemberUpdated, db, bot: Bot):
    """Fires when any user's membership status changes in a chat."""
    chat_id = event.chat.id
    user_id = event.new_chat_member.user.id
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status

    # Собственный статус бота сюда не приходит (см. on_bot_status_changed),
    # но на случай нестандартных клиентов — не обрабатываем себя как юзера.
    if user_id == bot.id:
        return

    # ── Case: user left or was kicked ────────────────────────────────────────
    if new_status in ("left", "kicked"):
        await mod_db.set_user_left_status(db, chat_id, user_id, True)
        logger.info(f"Юзер {user_id} покинул чат {chat_id}. Скрыт из топов.")

        # Сохраняем актуальный username в БД прямо в момент ухода
        leave_user = event.old_chat_member.user
        username = getattr(leave_user, "username", None)
        if username:
            await users_repo.update_user(db, user_id, username)

        # C1-B: отправить сообщение с кнопками "Добавить в ЧС" / "Закрыть"
        display_name = await resolve_display_name(db, user_id, chat_id, leave_user.first_name or f"ID{user_id}")
        username_part = f" (@{username})" if username else f" [ID: {user_id}]"
        kicked_note = " <i>(кикнут)</i>" if new_status == "kicked" else ""

        now_ts = int(time.time())
        b = InlineKeyboardBuilder()
        b.button(
            text="🚫 В чёрный список",
            callback_data=LeaveCB(action="blacklist", user_id=user_id, sent_at=now_ts),
        )
        b.button(
            text="✖️ Закрыть",
            callback_data=LeaveCB(action="close", user_id=user_id, sent_at=now_ts),
        )
        b.adjust(2)
        try:
            await bot.send_message(
                chat_id,
                f"👋 <b>{display_name}</b>{username_part} покинул(а) чат{kicked_note}.",
                reply_markup=b.as_markup(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить leave-уведомление в {chat_id}: {e}")
        return

    # ── Case: user joined (or returned) ─────────────────────────────────────
    if new_status in ("member", "administrator", "creator", "restricted"):
        await mod_db.set_user_left_status(db, chat_id, user_id, False)

        # Only react to actual new joins (not status changes within the chat)
        if old_status not in ("left", "kicked"):
            return

        # C1-A: kick if user is in chat blacklist
        if await is_in_chat_blacklist(db, chat_id, user_id):
            try:
                await bot.ban_chat_member(chat_id, user_id)
                await asyncio.sleep(1)
                await bot.unban_chat_member(chat_id, user_id)
                user_name = await resolve_display_name(db, user_id, chat_id, event.new_chat_member.user.first_name or f"ID{user_id}")
                await bot.send_message(
                    chat_id,
                    f"🚫 <b>{user_name}</b> находится в чёрном списке и был(а) исключён(а).",
                    parse_mode="HTML",
                )
                logger.info(f"Юзер {user_id} в ЧС — кикнут из {chat_id}")
            except Exception as e:
                logger.warning(f"Не удалось кикнуть юзера из ЧС {chat_id}: {e}")
            return

        # Shield for newcomers
        settings = await mod_db.get_chat_settings(db, chat_id)
        shield_days = settings.get("shield_duration_days", 0)

        if shield_days > 0:
            # bot_audit П7: через единый shield_user — он сохраняет is_immune
            # (возврат иммунного игрока больше не стирает постоянный иммунитет)
            # и пишет журнал модерации; строки users/user_chat_stats создаёт сам.
            from services import moderation as mod_service
            await mod_service.shield_user(
                db, chat_id, user_id, bot.id, shield_days * 1440,
                reason="Щит новичка")
            logger.info(f"Юзер {user_id} получил Щит Новичка на {shield_days} дн.")

        # Welcome message for new user (skip if it's the bot itself)
        if user_id != bot.id:
            user_name = await resolve_display_name(
                db, user_id, chat_id, event.new_chat_member.user.first_name or f"ID{user_id}"
            )
            welcome_text = random.choice(_USER_WELCOME_MESSAGES).format(name=user_name)
            try:
                await bot.send_message(chat_id, welcome_text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Приветствие не отправлено в {chat_id}: {e}")

        logger.info(f"Юзер {user_id} вошёл в чат {chat_id}.")


# ── C1-B Leave notification callbacks ────────────────────────────────────────

@router.callback_query(LeaveCB.filter())
async def cb_leave_action(
    query: types.CallbackQuery,
    callback_data: LeaveCB,
    db,
    developer_id: int = 0,
):
    import time as _time
    from services import moderation as _mod_service
    from infrastructure.repositories import chat as _chat_repo

    chat_id = query.message.chat.id
    actor_id = query.from_user.id

    if callback_data.action == "close":
        await query.message.delete()
        return await query.answer()

    # TTL check: кнопки работают только 10 минут
    if int(_time.time()) - callback_data.sent_at > _LEAVE_MSG_TTL:
        await query.message.edit_reply_markup(reply_markup=None)
        return await query.answer("⏰ Время действия кнопок истекло.", show_alert=True)

    if callback_data.action == "blacklist":
        # Check rank
        from infrastructure.repositories.moderation import get_chat_settings as _get_cs
        settings = await _get_cs(db, chat_id)
        required = settings.get("rank_ban", 5)
        stats = await _chat_repo.get_chat_stats(db, actor_id, chat_id)
        rank = stats.get("local_rank", 0) if stats else 0
        if not (developer_id and actor_id == developer_id) and rank < required:
            return await query.answer("❌ Недостаточно прав.", show_alert=True)

        await _mod_service.blacklist_user(db, chat_id, callback_data.user_id, actor_id)

        admin_name = await resolve_display_name(db, actor_id, chat_id, query.from_user.first_name)
        try:
            await query.message.edit_text(
                query.message.text + f"\n\n🚫 Добавлен(а) в ЧС ({admin_name}).",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass
        await query.answer("✅ Добавлен(а) в ЧС!")


# ── Chest events (B14) ────────────────────────────────────────────────────────

class ChestCB(CallbackData, prefix="chest"):
    chest_id: int


def _chest_keyboard(chest_id: int, claimed: int) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if claimed < CHEST_MAX_CLAIMANTS:
        b.button(
            text=f"👋 Забрать! ({claimed}/{CHEST_MAX_CLAIMANTS})",
            callback_data=ChestCB(chest_id=chest_id),
        )
    else:
        b.button(text="✅ Сундук разобран", callback_data=ChestCB(chest_id=chest_id))
    return b.as_markup()


@router.callback_query(ChestCB.filter())
async def cb_chest_claim(query: types.CallbackQuery, callback_data: ChestCB, db):
    chest_id = callback_data.chest_id
    user_id = query.from_user.id

    chest = await get_active_chest(db, query.message.chat.id)
    if not chest or chest["id"] != chest_id:
        await query.answer("⏰ Сундук уже закрыт!", show_alert=False)
        return

    position = 0
    claims_count = 0
    try:
        # Atomic claim: lock the chest row first so only one user at a time
        # can read MAX(position) and insert — eliminates the race condition.
        async with db.connection.transaction():
            # Lock chest row exclusively for the duration of this transaction
            async with db.execute(
                "SELECT id FROM chest_events WHERE id = ? AND status = 'active' FOR UPDATE",
                (chest_id,),
            ) as c:
                locked = await c.fetchone()
            if not locked:
                await query.answer("⏰ Сундук уже закрыт!", show_alert=False)
                return

            # Check if user already claimed
            async with db.execute(
                "SELECT position FROM chest_claims WHERE chest_id = ? AND user_id = ?",
                (chest_id, user_id),
            ) as c:
                existing = await c.fetchone()
            if existing:
                await query.answer("❌ Вы уже нажали!", show_alert=True)
                return

            # Get current position count (safe because we hold FOR UPDATE lock)
            async with db.execute(
                "SELECT COALESCE(MAX(position), 0) FROM chest_claims WHERE chest_id = ?",
                (chest_id,),
            ) as c:
                max_pos = (await c.fetchone())[0]

            position = max_pos + 1
            if position > CHEST_MAX_CLAIMANTS:
                await query.answer("❌ Все места уже заняты!", show_alert=True)
                return

            await db.execute(
                "INSERT INTO chest_claims (chest_id, user_id, position) VALUES (?, ?, ?)",
                (chest_id, user_id, position),
            )

            mora_reward = float(CHEST_REWARDS_BY_POSITION.get(position, 0))
            await eco_repo.add_balance(
                db, user_id,
                mora=mora_reward,
                source="event_chest",
                chat_id=query.message.chat.id,
                note=f"pos={position}",
            )

            if position <= 3:
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, 1) "
                    "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + 1",
                    (user_id, CHEST_TOP3_BONUS_ITEM),
                )

            claims_count = position  # position == number of claims so far
            if claims_count >= CHEST_MAX_CLAIMANTS:
                await close_chest(db, chest_id)
                await update_last_chest_at(db, query.message.chat.id)

        bonus_text = " + 🎟 Жетон!" if position <= 3 else ""
        await query.answer(
            f"🎉 #{position} место: +{mora_reward:.0f} 🪙{bonus_text}",
            show_alert=False,
        )

        try:
            if claims_count >= CHEST_MAX_CLAIMANTS:
                await query.message.edit_text(
                    query.message.text + "\n\n✅ <b>Сундук разобран!</b>",
                    reply_markup=_chest_keyboard(chest_id, claims_count),
                    parse_mode="HTML",
                )
            else:
                await query.message.edit_reply_markup(
                    reply_markup=_chest_keyboard(chest_id, claims_count)
                )
        except Exception:
            pass

    except Exception as e:
        try:
            pass  # transaction already rolled back by context manager
        except Exception:
            pass
        await query.answer("❌ Ошибка, попробуйте ещё раз.", show_alert=True)
        logger.error(f"Chest claim error: {e}")
