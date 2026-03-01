"""Command handlers.

Each handler returns a tuple: (text: str, reply_markup: dict | None).
reply_markup follows the Telegram InlineKeyboardMarkup schema.
"""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _

from .link import generate_link_code

logger = logging.getLogger(__name__)

# ── Keyboard builders ──────────────────────────────────────────────────────

def _kb(*rows: list[dict]) -> dict:
    """Build InlineKeyboardMarkup from rows of button dicts."""
    return {"inline_keyboard": list(rows)}


def _btn(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def _url_btn(text: str, url: str) -> dict:
    return {"text": text, "url": url}


# URL constants
CABINET_URL    = "https://iesasport.ch/auth/profile/"       # regular user profile
CARD_URL       = "https://iesasport.ch/auth/cabinet/"        # member PIN card
CONNECT_TG_URL = "https://iesasport.ch/auth/connect-telegram/"  # TG linking page

# ── Handlers ───────────────────────────────────────────────────────────────

Reply = tuple[str, dict | None]


async def handle_start(chat_id: int, text: str, user_db) -> Reply:
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        status = await sync_to_async(lambda: user_db.membership_status)()
        emoji = "✅" if status == "active" else "⚠️"
        status_label = "Активно" if status == "active" else "Неактивно"
        msg = (
            f"👋 <b>С возвращением, {name}!</b>\n\n"
            f"{emoji} Членство: <b>{status_label}</b>\n\n"
            "Выберите действие:"
        )
        kb = _kb(
            [_btn("📊 Мой статус", "cb:status"), _btn("❓ Помощь", "cb:help")],
            [_url_btn("🏠 Личный кабинет", CABINET_URL)],
            [_btn("🔓 Отвязать Telegram", "cb:unlink_ask")],
        )
    else:
        msg = (
            "👋 <b>Добро пожаловать в бот IESA Sport!</b>\n\n"
            "IESA Sport — это спортивная ассоциация Швейцарии.\n\n"
            "С помощью этого бота вы можете:\n"
            "• 🔔 Получать уведомления о визитах к партнёрам\n"
            "• 📊 Проверять статус членства\n"
            "• 🃏 Управлять своим аккаунтом на сайте\n\n"
            "Нажмите кнопку ниже, чтобы привязать Telegram к вашему аккаунту ↓"
        )
        kb = _kb(
            [_btn("🔗 Привязать аккаунт", "cb:link")],
            [_btn("❓ Помощь", "cb:help"), _url_btn("🌐 Сайт", "https://iesasport.ch")],
        )
    return msg, kb


async def handle_help(chat_id: int, text: str, user_db) -> Reply:
    msg = (
        "📖 <b>IESA Sport Bot — справка</b>\n\n"
        "<b>Команды:</b>\n"
        "🔗 /link — привязать Telegram к аккаунту на сайте\n"
        "📊 /status — проверить статус членства\n"
        "🔓 /unlink — отвязать Telegram\n"
        "🆔 /id — узнать свой Telegram chat ID\n\n"
        "<b>Уведомления:</b>\n"
        "✅ Подтверждение визита к партнёру\n"
        "📝 Изменение визита\n"
        "❌ Отмена визита\n"
        "🎉 Активация членства\n\n"
        "<b>Как привязать аккаунт:</b>\n"
        "1. Нажмите /link — получите 6-значный код\n"
        "2. Откройте страницу привязки по кнопке ниже\n"
        "3. Раздел «Telegram» → введите код\n\n"
        "🌐 <a href=\"https://iesasport.ch\">iesasport.ch</a>"
    )
    kb = _kb(
        [_btn("🔗 Привязать аккаунт", "cb:link"), _btn("📊 Статус", "cb:status")],
        [_url_btn("👤 Мой профиль", CABINET_URL)],
    )
    return msg, kb


async def handle_link(chat_id: int, text: str, user_db) -> Reply:
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        msg = (
            f"✅ Твой Telegram уже привязан к аккаунту <b>{name}</b>.\n\n"
            "Если хочешь отвязать — нажми кнопку ниже."
        )
        kb = _kb(
            [_btn("🔓 Отвязать", "cb:unlink_ask"), _url_btn("👤 Мой профиль", CABINET_URL)],
        )
        return msg, kb

    code = await sync_to_async(generate_link_code)(chat_id)
    msg = (
        f"🔗 <b>Твой код привязки:</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"1. Нажми кнопку <b>Привязать</b> ниже\n"
        f"2. Войди в свой аккаунт на сайте\n"
        f"3. Раздел «Телеграм» → введи этот код\n\n"
        f"⏳ Код действителен <b>10 минут</b>"
    )
    kb = _kb(
        [_url_btn("🔗 Привязать", CONNECT_TG_URL)],
        [_btn("🔄 Новый код", "cb:new_code")],
    )
    return msg, kb


async def handle_id(chat_id: int, text: str, user_db) -> Reply:
    account_line = ""
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        account_line = f"\n👤 Привязан к: <b>{name}</b>"
    msg = f"🆔 Ваш Telegram chat ID:\n<code>{chat_id}</code>" + account_line
    return msg, None


async def handle_admin(chat_id: int, text: str, user_db) -> Reply:
    """Full bot capabilities overview — accessible to site staff."""
    is_staff = False
    if user_db:
        is_staff = await sync_to_async(lambda: user_db.is_staff or user_db.is_superuser)()

    if not is_staff:
        return (
            "🔒 Эта команда доступна только администраторам IESA Sport.\n\n"
            "Если вы администратор — убедитесь, что Telegram привязан к вашему аккаунту "
            "с правами staff на сайте.",
            _kb([_btn("🔗 Привязать аккаунт", "cb:link")])
        )

    msg = (
        "⚙️ <b>IESA Sport Bot — полное описание</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"

        "<b>🤖 Команды для пользователей:</b>\n"
        "/start — главное меню (статус, кабинет)\n"
        "/help — справка и описание функций\n"
        "/link — получить код привязки Telegram к аккаунту\n"
        "/status — проверить статус членства\n"
        "/unlink — отвязать Telegram (отключить уведомления)\n"
        "/id — узнать свой Telegram chat ID\n\n"

        "<b>📬 Автоматические уведомления:</b>\n"
        "• ✅ Визит подтверждён партнёром\n"
        "• 📝 Время/дата визита изменены\n"
        "• ❌ Визит отменён\n"
        "• 🎉 Членство активировано\n\n"

        "<b>👥 Групповые функции:</b>\n"
        "• Приветствие новых участников в группе\n"
        "• Кнопки: сайт + привязка аккаунта\n\n"

        "<b>🔧 Настройка (env переменные):</b>\n"
        "<code>TELEGRAM_BOT_TOKEN</code> — токен бота от @BotFather\n"
        "<code>TELEGRAM_BOT_NAME</code> — username бота (без @)\n"
        "<code>TELEGRAM_CHANNEL_ID</code> — ID группы для приветствий\n"
        "<code>TELEGRAM_WEBHOOK_SECRET</code> — секрет для webhook (опц.)\n\n"

        "<b>🧪 Тестирование:</b>\n"
        "• Личные уведомления: отправьте <code>/start</code> боту напрямую\n"
        "• Код привязки: <code>/link</code> → введите код на сайте\n"
        "• Тест уведомлений: в Django Admin → <b>Send test notification</b>\n"
        "• Приветствие: добавьте тест-аккаунт в группу, где стоит бот\n"
        "• Webhook статус: <code>GET /tg-webhook/info/</code>\n"
        "• Регистрация команд: <code>POST /tg-webhook/set-commands/</code>\n\n"

        "<b>🔐 Безопасность:</b>\n"
        "• Webhook защищён секретным токеном (X-Telegram-Bot-Api-Secret-Token)\n"
        "• Коды привязки — одноразовые, TTL 10 минут, Redis кэш\n"
        "• Rate limit: 10 команд / 60 сек на пользователя\n\n"

        f"<b>ℹ️ Ваш chat ID:</b> <code>{chat_id}</code>\n"
        "<a href=\"https://iesasport.ch/admin/\">Django Admin</a> | "
        "<a href=\"https://iesasport.ch\">Сайт</a>"
    )
    return msg, None


async def handle_status(chat_id: int, text: str, user_db) -> Reply:
    if not user_db:
        msg = "❌ Telegram не привязан к аккаунту IESA Sport."
        kb = _kb([_btn("🔗 Привязать аккаунт", "cb:link")])
        return msg, kb

    name   = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
    status = await sync_to_async(lambda: user_db.membership_status)()
    emoji  = "✅" if status == "active" else "⚠️"
    label  = "Активно" if status == "active" else "Неактивно"
    msg = (
        f"👤 <b>{name}</b>\n"
        f"{emoji} Статус членства: <b>{label}</b>"
    )
    kb = _kb(
        [_url_btn("👤 Мой профиль", CABINET_URL), _btn("🔄 Обновить", "cb:status")],
        [_btn("🔓 Отвязать Telegram", "cb:unlink_ask")],
    )
    return msg, kb


async def handle_unlink_ask(chat_id: int, text: str, user_db) -> Reply:
    """Show confirmation before unlinking."""
    if not user_db:
        return "ℹ️ Этот Telegram не привязан ни к одному аккаунту.", None
    msg = (
        "⚠️ <b>Отвязать Telegram от аккаунта?</b>\n\n"
        "Вы перестанете получать уведомления о визитах и членстве."
    )
    kb = _kb([_btn("✅ Да, отвязать", "cb:unlink_yes"), _btn("❌ Отмена", "cb:cancel")])
    return msg, kb


async def handle_unlink_yes(chat_id: int, text: str, user_db) -> Reply:
    if not user_db:
        return "ℹ️ Уже отвязан.", None

    def _do_unlink():
        from users.models import User
        return User.objects.filter(telegram_chat_id=chat_id).update(
            telegram_chat_id=None,
            telegram_linked_at=None,
        )

    count = await sync_to_async(_do_unlink)()
    msg = "✅ Telegram отвязан от аккаунта." if count else "ℹ️ Уже отвязан."
    kb = _kb([_btn("🔗 Привязать снова", "cb:link")])
    return msg, kb


async def handle_cancel(chat_id: int, text: str, user_db) -> Reply:
    return "↩️ Отменено.", None


async def handle_new_channel_member(chat_id: str, new_member: dict, channel_title: str) -> None:
    """Send a creative, non-intrusive welcome to the group when someone joins.

    Sent silently (no notification sound) so it doesn't disturb existing members.
    Works both from chat_member admin-level updates AND from the service message
    new_chat_members field (no admin rights needed).
    """
    user    = new_member.get("user") or {}
    user_id = user.get("id")
    fname   = user.get("first_name") or ""
    lname   = user.get("last_name") or ""
    uname   = user.get("username")
    is_bot  = user.get("is_bot", False)

    if is_bot:
        return

    full_name = f"{fname} {lname}".strip() or uname or f"id{user_id}"
    mention   = f'<a href="tg://user?id={user_id}">{full_name}</a>' if user_id else full_name

    # Short, punchy, personal — feels like a real club, not a bot blast
    text = (
        f"🏔 <b>{mention}</b> —  добро пожаловать в <b>IESA Sport</b>!\n\n"
        f"Ты только что стал частью спортивного сообщества Швейцарии. "
        f"Создай аккаунт на сайте, чтобы получить персональную карту участника — "
        f"с ней открываются скидки у партнёров, участие в событиях и многое другое."
    )

    keyboard = {
        "inline_keyboard": [
            [{"text": "📝 Зарегистрироваться →", "url": "https://iesasport.ch/auth/register/"}],
        ]
    }

    from .client import send_message_async  # noqa: avoid circular at top level
    await send_message_async(
        text,
        chat_id=chat_id,
        reply_markup=keyboard,
        disable_notification=True,   # silent — doesn't ping the whole group
    )



async def handle_echo(chat_id: int, text: str, user_db) -> Reply:
    msg = (
        f"🔁 {text}\n\n"
        "<i>" + _('I repeat your messages in test mode. '
                  'Use buttons or commands below.') + "</i>"
    )
    if user_db:
        kb = _kb(
            [_btn(_("📊 My status"), "cb:status"), _url_btn(_("🏠 Cabinet"), CABINET_URL)],
        )
    else:
        kb = _kb([_btn(_("🔗 Link account"), "cb:link"), _btn(_("❓ Help"), "cb:help")])
    return msg, kb
