"""Command handlers.

Each handler returns a tuple: (text: str, reply_markup: dict | None).
reply_markup follows the Telegram InlineKeyboardMarkup schema.
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import re
from typing import Any

from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _

from .link import generate_link_code

logger = logging.getLogger(__name__)

# BLOCK 9 (audit v3): Telegram parse_mode=HTML ломается на сырых угловых скобках
# (<task>, <script>, любые `<...>` в тексте юзера). Также Telegram limit = 4096 chars.
_MAX_USER_ECHO_LEN = 300  # запас на префикс и suffix < 4096

def _safe_user_text(text: str, max_len: int = _MAX_USER_ECHO_LEN) -> str:
    """Безопасная вставка user-input в HTML-сообщение бота: escape + обрезка."""
    if not text:
        return ""
    safe = _html.escape(text, quote=False)
    if len(safe) > max_len:
        safe = safe[:max_len] + "…"
    return safe

# ── Keyboard builders ──────────────────────────────────────────────────────

def _kb(*rows: list[dict]) -> dict:
    """Build InlineKeyboardMarkup from rows of button dicts."""
    return {"inline_keyboard": list(rows)}


def _btn(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def _url_btn(text: str, url: str) -> dict:
    return {"text": text, "url": url}


# URL constants
CABINET_URL       = "https://iesasport.ch/auth/profile/"           # личный кабинет / профиль
CARD_URL          = "https://iesasport.ch/auth/profile/#pin-section"  # PIN + карта (Block 1)
CONNECT_TG_URL    = "https://iesasport.ch/auth/connect-telegram/"  # TG linking page
INSURANCE_URL     = "https://iesasport.ch/auth/insurance-agent/"   # страховой агент

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

    If the joining user already has an IESA account linked to this Telegram ID,
    the button leads to their profile; otherwise — to registration (which
    auto-redirects logged-in users anyway).
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

    # Check if this Telegram user already has a site account
    has_account = False
    if user_id:
        try:
            # B3-12: timeout защищает от зависания при медленной БД
            has_account = await asyncio.wait_for(
                sync_to_async(
                    lambda: __import__('users.models', fromlist=['User']).User.objects
                            .filter(telegram_chat_id=user_id).exists()
                )(),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("handle_new_channel_member: DB timeout for user_id=%s", user_id)
            # B3-08: логируем вместо pass
        except Exception as exc:
            logger.warning("handle_new_channel_member: DB error for user_id=%s: %s", user_id, exc)

    if has_account:
        text = (
            f"🏔 <b>{mention}</b> — добро пожаловать в <b>IESA Sport</b>!\n\n"
            f"Рады видеть тебя в нашем сообществе! "
            f"Твой аккаунт уже привязан — заходи в личный кабинет, чтобы увидеть "
            f"свою карту участника, скидки и ближайшие события."
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "🏠 Мой профиль →", "url": CABINET_URL}],
            ]
        }
    else:
        text = (
            f"🏔 <b>{mention}</b> — добро пожаловать в <b>IESA Sport</b>!\n\n"
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



async def handle_insurance(chat_id: int, text: str, user_db) -> Reply:
    """Команда /insurance — подача заявки на страхового агента."""
    if not user_db:
        msg = (
            "🛡️ <b>Страховой агент IESA</b>\n\n"
            "Чтобы подать заявку на страхового агента, сначала привяжите "
            "Telegram к своему аккаунту на сайте.\n\n"
            "Нажмите <b>Привязать аккаунт</b> — это займёт 1 минуту."
        )
        kb = _kb(
            [_btn("🔗 Привязать аккаунт", "cb:link")],
            [_url_btn("🌐 Сайт IESA", "https://iesasport.ch")],
        )
        return msg, kb

    # Проверяем существующую заявку
    def _check_existing():
        from users.models import InsuranceAgentRequest
        return InsuranceAgentRequest.objects.filter(
            user=user_db,
            status__in=['new', 'reviewing'],
        ).first()

    existing = await sync_to_async(_check_existing)()

    if existing:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        msg = (
            f"🛡️ <b>Ваша заявка уже подана, {name}!</b>\n\n"
            f"📋 Тип: {existing.get_request_type_display()}\n"
            f"🔄 Статус: <b>{existing.get_status_display()}</b>\n\n"
            "Наш менеджер обрабатывает её и скоро свяжется с вами."
        )
        kb = _kb(
            [_url_btn("📋 Перейти на сайт", INSURANCE_URL)],
        )
        return msg, kb

    name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
    msg = (
        f"🛡️ <b>Страховой агент IESA</b>\n\n"
        f"Здравствуйте, <b>{name}</b>!\n\n"
        "Мы подберём для вас личного страхового агента — специалиста, "
        "который поможет с:\n"
        "• Страхованием здоровья и жизни\n"
        "• Спортивным страхованием\n"
        "• Страхованием автомобиля и имущества\n"
        "• Пенсионными и накопительными программами\n\n"
        "📝 Нажмите кнопку ниже, чтобы заполнить заявку на сайте.\n"
        "Ответим в течение <b>24 часов</b>!"
    )
    kb = _kb(
        [_url_btn("🛡️ Подать заявку", INSURANCE_URL)],
        [_url_btn("🏠 Личный кабинет", CABINET_URL)],
    )
    return msg, kb


async def handle_echo(chat_id: int, text: str, user_db) -> Reply:
    # BLOCK 9b (audit v3): если юзер ввёл что похоже на 6-значный код привязки
    # прямо в чат бота — даём специальный ответ что код вводится на сайте.
    cleaned = re.sub(r"[\s\-]", "", text or "")
    if cleaned.isdigit() and len(cleaned) == 6:
        msg = (
            "⚠️ <b>Этот код вводится не в боте, а на сайте.</b>\n\n"
            f"Ваш код: <code>{_html.escape(cleaned)}</code>\n\n"
            "1. Откройте страницу привязки на сайте\n"
            "2. Войдите в свой аккаунт\n"
            "3. Введите этот код в поле\n"
            "4. Нажмите «Подтвердить»\n\n"
            "⏳ Код действителен <b>10 минут</b>"
        )
        kb = _kb(
            [_url_btn("🔗 Открыть страницу привязки", CONNECT_TG_URL)],
            [_btn("🔄 Получить новый код", "cb:new_code"), _btn("❓ Помощь", "cb:help")],
        )
        return msg, kb

    # BLOCK 9a (audit v3): обычный echo — экранируем HTML и обрезаем длину.
    # Без этого <task>, <script> и любые угловые скобки ломают Telegram parse_mode=HTML.
    safe = _safe_user_text(text)
    msg = (
        f"🔁 {safe}\n\n"
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
