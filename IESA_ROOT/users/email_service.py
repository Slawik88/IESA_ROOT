"""
Email Service for IESA Sport Visit Notifications
Sends visit confirmation, edit, and cancellation emails via Resend SMTP.
"""
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

ADMIN_EMAIL = 'makssamrt29@gmail.com'


def _get_from_email():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'IESA Sport <noreply@iesasport.ch>')


def send_visit_confirmed(visit):
    """Send confirmation email to member when a visit is logged."""
    member = visit.member
    partner = visit.partner
    if not member.email:
        return

    subject = f'✅ Visit confirmed at {partner.company_name}'
    cost_display = f'{visit.cost} CHF' if visit.cost else 'N/A'
    service_display = visit.get_service_type_display()
    ts = visit.timestamp.strftime('%d.%m.%Y %H:%M')

    html = f"""
<html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: linear-gradient(135deg,#667eea,#764ba2); padding:30px; border-radius:10px 10px 0 0; text-align:center;">
    <h1 style="color:#fff; margin:0;">✅ Visit Confirmed</h1>
  </div>
  <div style="background:#f8f9fa; padding:30px; border-radius:0 0 10px 10px;">
    <p>Hello, <strong>{member.get_full_name() or member.username}</strong>!</p>
    <p>Your visit has been logged successfully.</p>
    <table style="width:100%; border-collapse:collapse; margin:20px 0;">
      <tr style="background:#fff; border-bottom:1px solid #dee2e6;">
        <td style="padding:10px 15px; font-weight:bold;">Partner</td>
        <td style="padding:10px 15px;">{partner.company_name}</td>
      </tr>
      <tr style="background:#f8f9fa; border-bottom:1px solid #dee2e6;">
        <td style="padding:10px 15px; font-weight:bold;">Service</td>
        <td style="padding:10px 15px;">{service_display}</td>
      </tr>
      <tr style="background:#fff; border-bottom:1px solid #dee2e6;">
        <td style="padding:10px 15px; font-weight:bold;">Cost</td>
        <td style="padding:10px 15px;">{cost_display}</td>
      </tr>
      <tr style="background:#f8f9fa;">
        <td style="padding:10px 15px; font-weight:bold;">Date &amp; Time</td>
        <td style="padding:10px 15px;">{ts}</td>
      </tr>
    </table>
    {"<p><strong>Description:</strong> " + visit.service_description + "</p>" if visit.service_description else ""}
    <hr style="border:none; border-top:1px solid #dee2e6; margin:20px 0;">
    <p style="color:#6c757d; font-size:0.85rem;">IESA Sport — Your membership card</p>
  </div>
</body></html>
"""
    plain = (
        f"Visit confirmed at {partner.company_name}\n"
        f"Service: {service_display}\nCost: {cost_display}\nDate: {ts}\n"
    )
    _send(subject, plain, html, [member.email])


def send_visit_edited(visit, audit):
    """Send notification to member when their visit record is edited."""
    member = visit.member
    partner = visit.partner
    if not member.email:
        return

    subject = f'📝 Visit record updated — {partner.company_name}'
    ts = visit.timestamp.strftime('%d.%m.%Y %H:%M')
    html = f"""
<html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: linear-gradient(135deg,#f093fb,#f5576c); padding:30px; border-radius:10px 10px 0 0; text-align:center;">
    <h1 style="color:#fff; margin:0;">📝 Visit Updated</h1>
  </div>
  <div style="background:#f8f9fa; padding:30px; border-radius:0 0 10px 10px;">
    <p>Hello, <strong>{member.get_full_name() or member.username}</strong>!</p>
    <p>Your visit at <strong>{partner.company_name}</strong> (logged on {ts}) has been updated.</p>
    <h3>Previous values:</h3>
    <table style="width:100%; border-collapse:collapse; margin:0 0 15px;">
      <tr style="background:#fff3cd; border-bottom:1px solid #ffc107;">
        <td style="padding:8px 12px; font-weight:bold;">Service</td>
        <td style="padding:8px 12px;">{audit.previous_service_type}</td>
      </tr>
      <tr style="background:#fff3cd; border-bottom:1px solid #ffc107;">
        <td style="padding:8px 12px; font-weight:bold;">Cost</td>
        <td style="padding:8px 12px;">{f'{audit.previous_cost} CHF' if audit.previous_cost else 'N/A'}</td>
      </tr>
    </table>
    <h3>New values:</h3>
    <table style="width:100%; border-collapse:collapse; margin:0 0 15px;">
      <tr style="background:#d4edda; border-bottom:1px solid #28a745;">
        <td style="padding:8px 12px; font-weight:bold;">Service</td>
        <td style="padding:8px 12px;">{visit.get_service_type_display()}</td>
      </tr>
      <tr style="background:#d4edda; border-bottom:1px solid #28a745;">
        <td style="padding:8px 12px; font-weight:bold;">Cost</td>
        <td style="padding:8px 12px;">{f'{visit.cost} CHF' if visit.cost else 'N/A'}</td>
      </tr>
    </table>
    <p><strong>Reason for edit:</strong> {audit.reason}</p>
    <p style="color:#6c757d; font-size:0.85rem;">If you have questions, contact the partner directly.</p>
  </div>
</body></html>
"""
    plain = (
        f"Your visit at {partner.company_name} has been edited.\n"
        f"Reason: {audit.reason}\n"
        f"New service: {visit.get_service_type_display()}, Cost: {visit.cost or 'N/A'} CHF\n"
    )
    _send(subject, plain, html, [member.email])


def send_visit_cancelled(visit, audit):
    """Send notification to member when their visit is cancelled."""
    member = visit.member
    partner = visit.partner
    if not member.email:
        return

    subject = f'❌ Visit cancelled — {partner.company_name}'
    ts = visit.timestamp.strftime('%d.%m.%Y %H:%M')
    html = f"""
<html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: linear-gradient(135deg,#f5576c,#c0392b); padding:30px; border-radius:10px 10px 0 0; text-align:center;">
    <h1 style="color:#fff; margin:0;">❌ Visit Cancelled</h1>
  </div>
  <div style="background:#f8f9fa; padding:30px; border-radius:0 0 10px 10px;">
    <p>Hello, <strong>{member.get_full_name() or member.username}</strong>!</p>
    <p>Your visit at <strong>{partner.company_name}</strong> (originally logged on {ts}) has been <strong>cancelled</strong>.</p>
    <table style="width:100%; border-collapse:collapse; margin:20px 0;">
      <tr style="background:#f8d7da; border-bottom:1px solid #f5c6cb;">
        <td style="padding:10px 15px; font-weight:bold;">Service</td>
        <td style="padding:10px 15px;">{audit.previous_service_type}</td>
      </tr>
      <tr style="background:#f8d7da;">
        <td style="padding:10px 15px; font-weight:bold;">Cost</td>
        <td style="padding:10px 15px;">{f'{audit.previous_cost} CHF' if audit.previous_cost else 'N/A'}</td>
      </tr>
    </table>
    <p><strong>Reason for cancellation:</strong> {audit.reason}</p>
    <p style="color:#6c757d; font-size:0.85rem;">If you believe this is an error, please contact the partner.</p>
  </div>
</body></html>
"""
    plain = (
        f"Your visit at {partner.company_name} has been cancelled.\n"
        f"Reason: {audit.reason}\n"
    )
    _send(subject, plain, html, [member.email])


def send_test_email(recipient=ADMIN_EMAIL):
    """Send a simple test email to verify SMTP configuration."""
    subject = '✅ IESA Sport — Test Email'
    plain = 'This is a test email from IESA Sport visit notification system.'
    html = """
<html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: linear-gradient(135deg,#667eea,#764ba2); padding:30px; border-radius:10px; text-align:center;">
    <h1 style="color:#fff; margin:0;">✅ Test Email</h1>
    <p style="color:#ddd; margin:15px 0 0;">IESA Sport email notifications are working correctly.</p>
  </div>
</body></html>
"""
    return _send(subject, plain, html, [recipient])


def _send(subject, plain_text, html_content, recipients):
    """Internal helper — wraps send_mail with error logging."""
    try:
        result = send_mail(
            subject=subject,
            message=plain_text,
            from_email=_get_from_email(),
            recipient_list=recipients,
            html_message=html_content,
            fail_silently=False,
        )
        logger.info(f'Email sent: "{subject}" → {recipients}')
        return result
    except Exception as exc:
        logger.error(f'Email failed: "{subject}" → {recipients}: {exc}')
        return 0
