"""Insurance agent request views."""
import logging
import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def insurance_agent_request(request):
    from users.models import AdminNotificationProfile, InsuranceAgentRequest

    existing = InsuranceAgentRequest.objects.filter(user=request.user, status__in=['new', 'reviewing']).first()

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        if not full_name:
            messages.error(request, _('Пожалуйста, укажите ваше имя.'))
            return redirect('users:insurance_agent')

        req = InsuranceAgentRequest.objects.create(
            user=request.user,
            request_type=request.POST.get('request_type', 'new_agent'),
            full_name=full_name,
            phone=request.POST.get('phone', '').strip(),
            email=request.POST.get('email', '').strip() or request.user.email,
            telegram_username=request.POST.get('telegram_username', '').strip(),
            city=request.POST.get('city', '').strip(),
            insurance_types=request.POST.get('insurance_types', '').strip(),
            message=request.POST.get('message', '').strip(),
        )
        messages.success(request, _('Ваша заявка принята! Наш менеджер свяжется с вами в ближайшее время.'))
        _notify_admins_insurance(req)
        return redirect('users:insurance_agent')

    return render(request, 'users/insurance_agent.html', {'existing': existing, 'user': request.user})


def _notify_admins_insurance(req) -> None:
    from notifications.models import Notification as _Notif
    from users.models import AdminNotificationProfile

    for profile in AdminNotificationProfile.objects.filter(is_active=True).select_related('admin_user'):
        admin = profile.admin_user

        if profile.should_notify_site('insurance_request'):
            _Notif.objects.create(
                recipient=admin, notification_type='system',
                title=_('Новая заявка: страховой агент'),
                message=_('%(name)s подал(а) заявку на страхового агента.\nТип: %(req_type)s\nТелефон: %(phone)s\nEmail: %(email)s') % {
                    'name': req.full_name, 'req_type': req.get_request_type_display(),
                    'phone': req.phone or '—', 'email': req.email or '—',
                },
                link='/admin/users/insuranceagentrequest/',
            )

        if profile.should_notify_telegram('insurance_request') and getattr(admin, 'telegram_chat_id', None):
            _rid, _cid = req.pk, admin.telegram_chat_id

            def _send_tg(rid=_rid, cid=_cid):
                try:
                    from users.models import InsuranceAgentRequest as _IAR
                    from users.telegram.notify import send_message as _sm
                    r = _IAR.objects.get(pk=rid)
                    _sm(cid, (
                        f"🛡 <b>Новая заявка: страховой агент</b>\n\n👤 <b>{r.full_name}</b>\n"
                        f"📋 {r.get_request_type_display()}\n"
                        + (f"📞 {r.phone}\n" if r.phone else "")
                        + (f"✉️ {r.email}\n" if r.email else "")
                        + (f"📍 {r.city}\n" if r.city else "")
                        + (f"\n💬 {r.message}\n" if r.message else "")
                        + f"\n🔗 /admin/users/insuranceagentrequest/{r.pk}/change/"
                    ), parse_mode='HTML')
                except Exception as exc:
                    logger.error("insurance TG notify failed: %s", exc)

            threading.Thread(target=_send_tg, daemon=True).start()
