"""Visit and membership notification functions.

Sync variants — вызываются из Django views/signals в фоновом потоке (thread-safe).
Async варианты — для вызова из async-контекстов (B3-06).
"""
import logging

from django.utils.translation import gettext as _

from .client import send_message, send_message_async

logger = logging.getLogger(__name__)


def _visit_context(visit):
    """Return (chat_id, member, partner, ts, cost) or None if no telegram_chat_id."""
    chat_id = getattr(visit.member, "telegram_chat_id", None)
    if not chat_id:
        return None
    ts   = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    cost = f"{visit.cost} CHF" if visit.cost else "—"
    return chat_id, visit.member, visit.partner, ts, cost


def notify_visit_confirmed(visit) -> bool:
    """Notify member that their visit has been confirmed."""
    ctx = _visit_context(visit)
    if ctx is None:
        return False
    chat_id, member, partner, ts, cost = ctx
    service = visit.get_service_type_display()
    name    = member.get_full_name() or member.username
    text = (
        _("✅ <b>Visit confirmed</b>") + "\n\n"
        f"👤 {name}\n"
        f"🏢 {partner.company_name}\n"
        f"🏃 {service}  💰 {cost}\n"
        f"🕐 {ts}"
    )
    if visit.service_description:
        text += f"\n📝 {visit.service_description}"
    return send_message(text, chat_id=chat_id)


def notify_visit_edited(visit, audit) -> bool:
    """Notify member that their visit has been edited."""
    ctx = _visit_context(visit)
    if ctx is None:
        return False
    chat_id, member, partner, ts, _ = ctx
    old_cost = f"{audit.previous_cost} CHF" if audit.previous_cost else "—"
    new_cost = f"{visit.cost} CHF" if visit.cost else "—"
    text = (
        _("📝 <b>Visit edited</b>") + "\n\n"
        f"👤 {member.get_full_name() or member.username}\n"
        f"🏢 {partner.company_name}  🕐 {ts}\n"
        f"<s>{audit.previous_service_type} / {old_cost}</s>\n"
        f"✏️ {visit.get_service_type_display()} / {new_cost}\n"
        f"📋 {audit.reason}"
    )
    return send_message(text, chat_id=chat_id)


def notify_visit_cancelled(visit, audit) -> bool:
    """Notify member that their visit has been cancelled."""
    ctx = _visit_context(visit)
    if ctx is None:
        return False
    chat_id, member, partner, ts, _ = ctx
    old_cost = f"{audit.previous_cost} CHF" if audit.previous_cost else "—"
    text = (
        _("❌ <b>Visit cancelled</b>") + "\n\n"
        f"👤 {member.get_full_name() or member.username}\n"
        f"🏢 {partner.company_name}  🕐 {ts}\n"
        f"🏃 {audit.previous_service_type} / {old_cost}\n"
        f"📋 {audit.reason}"
    )
    return send_message(text, chat_id=chat_id)


def send_test_notification(custom_text: str = "") -> bool:
    """Stub — always False (used only in admin test pages)."""
    return bool(custom_text)


# ── Async variants (B3-06) ─────────────────────────────────────────────────
# Используются при вызове из async-контекста (aiogram handlers, async views и т.п.).
# Все ORM-поля читаются внутри sync_to_async блока перед отправкой.

async def notify_visit_confirmed_async(visit) -> bool:
    """Async variant of notify_visit_confirmed."""
    from asgiref.sync import sync_to_async

    async def _get_data():
        chat_id = getattr(visit.member, "telegram_chat_id", None)
        if not chat_id:
            return None
        member  = visit.member
        partner = visit.partner
        ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
        cost    = f"{visit.cost} CHF" if visit.cost else "—"
        service = visit.get_service_type_display()
        name    = member.get_full_name() or member.username
        desc    = visit.service_description or ""
        return chat_id, name, partner.company_name, service, cost, ts, desc

    data = await sync_to_async(_get_data)()
    if data is None:
        return False
    chat_id, name, company, service, cost, ts, desc = data
    text = (
        _("✅ <b>Visit confirmed</b>") + "\n\n"
        f"👤 {name}\n🏢 {company}\n🏃 {service}  💰 {cost}\n🕐 {ts}"
    )
    if desc:
        text += f"\n📝 {desc}"
    return await send_message_async(text, chat_id=chat_id)


def notify_membership_activated(user) -> bool:
    """Notify user that their membership has been activated."""
    chat_id = getattr(user, "telegram_chat_id", None)
    if not chat_id:
        return False
    name = user.get_full_name() or user.username
    text = (
        _("🎉 <b>Membership activated!</b>") + "\n\n"
        + _('Hello, %(name)s!') % {'name': name} + "\n"
        + _('Your IESA Sport membership is now active.') + "\n\n"
        + _('🏃 Use <b>Personal Cabinet</b> to get your PIN:') + "\n"
        "<a href='https://iesasport.ch/auth/profile/#pin-section'>" + _('Open profile →') + "</a>"
    )
    return send_message(text, chat_id=chat_id)
