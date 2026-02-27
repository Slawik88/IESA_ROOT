"""Visit and membership notification functions.

All functions are sync (called from Django views/signals).
"""
import logging

from django.utils.translation import gettext as _

from .client import send_message

logger = logging.getLogger(__name__)


def notify_visit_confirmed(visit) -> bool:
    """Notify member that their visit has been confirmed."""
    chat_id = getattr(visit.member, "telegram_chat_id", None)
    if not chat_id:
        return False
    member  = visit.member
    partner = visit.partner
    ts      = visit.timestamp.strftime("%d.%m.%Y %H:%M")
    cost    = f"{visit.cost} CHF" if visit.cost else "—"
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
    chat_id = getattr(visit.member, "telegram_chat_id", None)
    if not chat_id:
        return False
    member   = visit.member
    partner  = visit.partner
    ts       = visit.timestamp.strftime("%d.%m.%Y %H:%M")
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
    chat_id = getattr(visit.member, "telegram_chat_id", None)
    if not chat_id:
        return False
    member   = visit.member
    partner  = visit.partner
    ts       = visit.timestamp.strftime("%d.%m.%Y %H:%M")
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
        "<a href='https://iesasport.ch/auth/cabinet/'>" + _('Open cabinet →') + "</a>"
    )
    return send_message(text, chat_id=chat_id)
