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


CABINET_URL = "https://iesasport.ch/auth/cabinet/"

# ── Handlers ───────────────────────────────────────────────────────────────

Reply = tuple[str, dict | None]


async def handle_start(chat_id: int, text: str, user_db) -> Reply:
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        status = await sync_to_async(lambda: user_db.membership_status)()
        emoji = "✅" if status == "active" else "⚠️"
        status_label = _('Active') if status == 'active' else _('Inactive')
        msg = (
            _('👋 <b>Welcome back, %(name)s!</b>') % {'name': name} + "\n\n"
            f"{emoji} " + _('Membership: <b>%(status)s</b>') % {'status': status_label} + "\n\n"
            + _('Choose an action:')
        )
        kb = _kb(
            [_btn(_("📊 My status"), "cb:status"), _btn(_("❓ Help"), "cb:help")],
            [_url_btn(_("🏠 Personal Cabinet"), CABINET_URL)],
            [_btn(_("🔓 Unlink Telegram"), "cb:unlink_ask")],
        )
    else:
        msg = (
            _('👋 <b>Hello! This is the IESA Sport bot.</b>') + "\n\n"
            + _('Here you can link your Telegram to your website account '
                'and receive instant notifications about partner visits.') + "\n\n"
            + _('Press the button below ↓')
        )
        kb = _kb(
            [_btn(_("🔗 Link account"), "cb:link")],
            [_btn(_("❓ Help"), "cb:help")],
        )
    return msg, kb


async def handle_help(chat_id: int, text: str, user_db) -> Reply:
    msg = (
        _('📖 <b>IESA Sport Bot — help</b>') + "\n\n"
        + _('🔗 <b>Link account</b> — get a 6-digit code and enter it in your cabinet on the site.') + "\n\n"
        + _('📊 <b>My status</b> — check your membership status.') + "\n\n"
        + _('🏠 <b>Personal Cabinet</b> — open the site, get your PIN for partners.') + "\n\n"
        + _('🔓 <b>Unlink Telegram</b> — disable notifications.') + "\n\n"
        + _('<b>You receive notifications about:</b>') + "\n"
        + _('✅ Visit confirmation') + "\n"
        + _('📝 Visit edit') + "\n"
        + _('❌ Visit cancellation') + "\n"
        + _('🎉 Membership activation')
    )
    kb = _kb(
        [_btn(_("🔗 Link account"), "cb:link"), _btn(_("📊 My status"), "cb:status")],
        [_url_btn(_("🏠 Personal Cabinet"), CABINET_URL)],
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
            [_btn("🔓 Отвязать", "cb:unlink_ask"), _url_btn("🏠 Кабинет", CABINET_URL)],
        )
        return msg, kb

    code = await sync_to_async(generate_link_code)(chat_id)
    msg = (
        f"🔗 <b>Твой код привязки:</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"1. Открой <b>Личный кабинет</b> на сайте\n"
        f"2. Раздел «Telegram» → введи этот код\n\n"
        f"⏳ Код действителен <b>10 минут</b>"
    )
    kb = _kb(
        [_url_btn("🏠 Открыть кабинет", CABINET_URL)],
        [_btn("🔄 Новый код", "cb:new_code")],
    )
    return msg, kb


async def handle_id(chat_id: int, text: str, user_db) -> Reply:
    account_line = ""
    if user_db:
        name = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
        account_line = "\n" + _('👤 Linked to: <b>%(name)s</b>') % {'name': name}
    msg = _('Your Telegram chat_id:') + f"\n<code>{chat_id}</code>" + account_line
    return msg, None


async def handle_status(chat_id: int, text: str, user_db) -> Reply:
    if not user_db:
        msg = _("❌ Telegram is not linked to an IESA Sport account.")
        kb = _kb([_btn(_("🔗 Link account"), "cb:link")])
        return msg, kb

    name   = await sync_to_async(lambda: user_db.get_full_name() or user_db.username)()
    status = await sync_to_async(lambda: user_db.membership_status)()
    emoji  = "✅" if status == "active" else "⚠️"
    label  = _('Active') if status == 'active' else _('Inactive')
    msg = (
        f"👤 <b>{name}</b>\n"
        f"{emoji} " + _('Membership status: <b>%(label)s</b>') % {'label': label}
    )
    kb = _kb(
        [_url_btn(_("🏠 Personal Cabinet"), CABINET_URL), _btn(_("🔄 Refresh"), "cb:status")],
        [_btn(_("🔓 Unlink Telegram"), "cb:unlink_ask")],
    )
    return msg, kb


async def handle_unlink_ask(chat_id: int, text: str, user_db) -> Reply:
    """Show confirmation before unlinking."""
    if not user_db:
        return _("ℹ️ This Telegram is not linked to any account."), None
    msg = _("⚠️ <b>Unlink Telegram from account?</b>") + "\n\n" + _('You will stop receiving notifications.')
    kb = _kb([_btn(_("✅ Yes, unlink"), "cb:unlink_yes"), _btn(_("❌ Cancel"), "cb:cancel")])
    return msg, kb


async def handle_unlink_yes(chat_id: int, text: str, user_db) -> Reply:
    if not user_db:
        return _("ℹ️ Already unlinked."), None

    def _do_unlink():
        from users.models import User
        return User.objects.filter(telegram_chat_id=chat_id).update(
            telegram_chat_id=None,
            telegram_linked_at=None,
        )

    count = await sync_to_async(_do_unlink)()
    msg = _("✅ Telegram unlinked from account.") if count else _("ℹ️ Already unlinked.")
    kb = _kb([_btn(_("🔗 Link again"), "cb:link")])
    return msg, kb


async def handle_cancel(chat_id: int, text: str, user_db) -> Reply:
    return _("↩️ Cancelled."), None


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
