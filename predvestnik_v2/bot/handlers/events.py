import asyncio
import random
import time
from datetime import datetime, timedelta

from aiogram import Router, types, F, Bot
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
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories.blacklist import is_in_chat_blacklist
from infrastructure.repositories.chest_events import (
    get_active_chest, close_chest, update_last_chest_at,
)
from services.utils import safe_html

router = Router(name="events_router")

_LEAVE_MSG_TTL = 600  # кнопки активны 10 минут


class LeaveCB(CallbackData, prefix="leave"):
    action: str        # "blacklist" | "close"
    user_id: int
    sent_at: int = 0   # unix timestamp отправки — для TTL проверки


# ── Welcome messages diversity ────────────────────────────────────────────────

_BOT_WELCOME_MESSAGES = [
    (
        "👋 <b>Привет! Я — Предвестник V2</b>\n\n"
        "Я ваш игровой бот: экономика, питомцы, модерация и многое другое.\n\n"
        "📌 <b>С чего начать:</b>\n"
        "· бот помощь — все команды\n"
        "· бот профиль — ваш профиль\n"
        "· бот зоопарк — питомцы\n"
        "· бот настройки чата — для администраторов\n\n"
        "<i>Владелец чата уже получил ранг Владельца 👑</i>"
    ),
    (
        "🔮 <b>Предвестник V2 здесь!</b>\n\n"
        "Готов к работе: экономика, питомцы, гача, аукцион и многое другое.\n\n"
        "📌 <b>Быстрый старт:</b>\n"
        "· бот помощь — список всех команд\n"
        "· бот крутка — гача-крутки\n"
        "· бот акция — ежедневная акция\n"
        "· бот задания — ежедневные квесты\n\n"
        "<i>Пишите «бот» перед каждой командой.</i>"
    ),
    (
        "⚡ <b>Бот активирован!</b>\n\n"
        "Добро пожаловать в мир Предвестника.\n"
        "Собирай питомцев, зарабатывай Мору, участвуй в аукционах.\n\n"
        "📌 <b>Полезные команды:</b>\n"
        "· бот помощь — навигация\n"
        "· бот стрик — ежедневный вход\n"
        "· бот топ — лидерборд\n"
        "· бот я — ваша карточка\n\n"
        "<i>Синтаксис: бот [команда], [аргументы]</i>"
    ),
    (
        "🌌 <b>Привет, новый чат!</b>\n\n"
        "Я — Предвестник V2, ваш игровой помощник.\n\n"
        "🐾 Питомцы · 💰 Экономика · 🛡 Модерация\n"
        "🎰 Гача · 🏛 Аукцион · 📋 Квесты\n\n"
        "Напиши <b>бот помощь</b> чтобы узнать всё.\n\n"
        "<i>Администраторы: бот настройки чата — для настройки прав.</i>"
    ),
    (
        "✨ <b>Предвестник V2 к вашим услугам!</b>\n\n"
        "Полноценная игровая экосистема прямо в Telegram.\n\n"
        "📌 <b>Три первых шага:</b>\n"
        "1️⃣ бот профиль — посмотреть себя\n"
        "2️⃣ бот стрик — начать серию входов\n"
        "3️⃣ бот крутка — получить первого питомца\n\n"
        "<i>Удачи! 🍀</i>"
    ),
]

_USER_WELCOME_MESSAGES = [
    "👋 Добро пожаловать, <b>{name}</b>! Напиши <b>бот помощь</b> чтобы узнать команды.",
    "🌟 <b>{name}</b>, рады тебя видеть! Начни с <b>бот стрик</b> — ежедневный бонус ждёт.",
    "⚡ <b>{name}</b> только что вошёл(а) в чат! Напиши <b>бот профиль</b> чтобы создать свой профиль.",
    "🎉 Привет, <b>{name}</b>! Мир Предвестника ждёт тебя — попробуй <b>бот крутка</b>.",
    "✨ <b>{name}</b> присоединился(ась)! Пиши <b>бот помощь</b> — там всё что нужно знать.",
]


async def _delayed_bot_welcome(bot: Bot, chat_id: int) -> None:
    """Send the bot's welcome message after a short delay. No DB needed."""
    await asyncio.sleep(2)
    text = random.choice(_BOT_WELCOME_MESSAGES)
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Bot welcome failed in {chat_id}: {e}")


# ── Main member status handler ────────────────────────────────────────────────

@router.chat_member()
async def on_user_status_changed(event: ChatMemberUpdated, db, bot: Bot):
    """Fires when any user's membership status changes in a chat."""
    chat_id = event.chat.id
    user_id = event.new_chat_member.user.id
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status

    # ── Case: BOT itself joined the chat ─────────────────────────────────────
    if user_id == bot.id and new_status in ("member", "administrator") and old_status in ("left", "kicked"):
        logger.info(f"Бот вошёл в чат {chat_id} ({event.chat.title})")

        # Auto-assign rank 6 (Владелец) to the chat owner
        try:
            admins = await bot.get_chat_administrators(chat_id)
            for admin in admins:
                if admin.status == "creator":
                    owner_id = admin.user.id
                    owner_username = getattr(admin.user, "username", None)
                    await users_repo.update_user(db, owner_id, owner_username)
                    # Ensure user_chat_stats row exists before setting rank
                    await db.execute(
                        "INSERT OR IGNORE INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, ?)",
                        (owner_id, chat_id),
                    )
                    await db.execute(
                        "UPDATE user_chat_stats SET local_rank = 6 "
                        "WHERE user_tg_id = ? AND chat_tg_id = ?",
                        (owner_id, chat_id),
                    )
                    await db.commit()
                    logger.info(f"Авто-ранг 6 выдан владельцу {owner_id} в чате {chat_id}")
                    break
        except Exception as e:
            logger.warning(f"Не удалось выдать авто-ранг в чате {chat_id}: {e}")

        # Ensure chat settings row exists
        chat_title = event.chat.title or ""
        await db.execute(
            "INSERT OR IGNORE INTO chat_settings (chat_id, chat_title) VALUES (?, ?)",
            (chat_id, chat_title),
        )
        await db.commit()

        # Send welcome message after 2-second delay (no DB needed in the task)
        asyncio.create_task(_delayed_bot_welcome(bot, chat_id))
        return

    # ── Case: user left or was kicked ────────────────────────────────────────
    if new_status in ("left", "kicked"):
        await mod_db.set_user_left_status(db, chat_id, user_id, True)
        logger.info(f"Юзер {user_id} покинул чат {chat_id}. Скрыт из топов.")

        # C1-B: отправить сообщение с кнопками "Добавить в ЧС" / "Закрыть"
        user_name = safe_html(
            event.old_chat_member.user.first_name or f"ID{user_id}"
        )
        now_ts = int(time.time())
        b = InlineKeyboardBuilder()
        b.button(
            text="🚫 Добавить в ЧС",
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
                f"👋 <b>{user_name}</b> покинул(а) чат.",
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
                user_name = safe_html(event.new_chat_member.user.first_name or f"ID{user_id}")
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
            until_dt = datetime.utcnow() + timedelta(days=shield_days)
            until_str = until_dt.strftime("%Y-%m-%d %H:%M:%S")
            await db.execute("INSERT OR IGNORE INTO users (user_tg_id) VALUES (?)", (user_id,))
            await db.execute(
                "INSERT OR IGNORE INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, ?)",
                (user_id, chat_id),
            )
            await mod_db.set_immunity(db, chat_id, user_id, 0, until_str)
            logger.info(f"Юзер {user_id} получил Щит Новичка на {shield_days} дн.")

        # Welcome message for new user (skip if it's the bot itself)
        if user_id != bot.id:
            user_name = safe_html(
                event.new_chat_member.user.first_name or f"ID{user_id}"
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
    from infrastructure.repositories.blacklist import add_to_chat_blacklist
    from infrastructure.repositories import moderation as _mod_db
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

        await add_to_chat_blacklist(db, chat_id, callback_data.user_id, None, actor_id)
        await db.commit()

        admin_name = safe_html(query.from_user.first_name)
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
