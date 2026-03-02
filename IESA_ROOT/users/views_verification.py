"""
Membership Verification System Views
"""
import logging
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django_ratelimit.decorators import ratelimit

from users.telegram import (
    consume_link_code,
    get_webhook_info,
    init_bot_commands,
    is_configured as _token_configured,
    notify_visit_cancelled,
    notify_visit_confirmed,
    notify_visit_edited,
    process_incoming_update,
    send_test_notification,
    set_webhook,
    token as _token,
    verify_telegram_auth,
    webhook_secret as _webhook_secret,
)
from .forms_verification import (
    CancelVisitForm,
    EditVisitForm,
    MemberSearchForm,
    VisitForm,
)
from .models import Partner, User, Visit, VisitAudit

logger = logging.getLogger(__name__)

# Lockout constants
PIN_MAX_ATTEMPTS = 10
PIN_LOCKOUT_MINUTES = 15
IDEMPOTENCY_WINDOW = 300   # 5 minutes
EDIT_WINDOW = 1200          # 20 minutes


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def is_partner(user):
    """Check if user has a Partner profile."""
    try:
        has_profile = hasattr(user, 'partner_profile')
        logger.debug("is_partner check — user: %s, has_profile: %s", user.username, has_profile)
        return has_profile
    except Exception as exc:
        logger.error("is_partner check error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public / member views
# ---------------------------------------------------------------------------

def public_profile(request, uuid):
    """Public profile view accessible via QR code."""
    member = get_object_or_404(User, permanent_id=uuid)
    return render(request, 'users/member_scan_card.html', {
        'member': member,
        'is_public_view': True,
    })


@login_required
def member_cabinet(request):
    """Personal cabinet showing current PIN and membership info."""
    import time

    user = request.user

    if not hasattr(user, 'membership_status'):
        messages.error(request, _('⚠️ System error: Database migration required. Contact administrator.'))
        return redirect('core:home')

    _tg_ctx = {
        'telegram_linked': bool(user.telegram_chat_id),
        'telegram_bot_configured': bool(_token()),
        'telegram_bot_name': os.environ.get('TELEGRAM_BOT_NAME', ''),
    }

    if user.membership_status != 'active':
        return render(request, 'users/member_cabinet.html', {
            'membership_status': user.membership_status,
            'current_pin': None,
            'seconds_remaining': 0,
            'error_message': _('Your membership is inactive. Contact administrator to activate your account.'),
            **_tg_ctx,
        })

    if not user.totp_secret:
        messages.error(request, _('⚠️ TOTP secret not configured. Contact administrator.'))
        return render(request, 'users/member_cabinet.html', {
            'membership_status': user.membership_status,
            'current_pin': None,
            'seconds_remaining': 0,
            'error_message': _('PIN system not initialized. Contact administrator.'),
            **_tg_ctx,
        })

    current_pin = user.get_current_pin()
    if not current_pin:
        messages.error(request, _('⚠️ Unable to generate PIN. Contact administrator.'))
        return render(request, 'users/member_cabinet.html', {
            'membership_status': user.membership_status,
            'current_pin': None,
            'seconds_remaining': 0,
            'error_message': _('PIN generation failed. Contact administrator.'),
            **_tg_ctx,
        })

    current_time = int(time.time())
    interval = 720
    time_step = current_time // interval
    next_refresh = (time_step + 1) * interval
    seconds_remaining = next_refresh - current_time

    return render(request, 'users/member_cabinet.html', {
        'current_pin': current_pin,
        'seconds_remaining': seconds_remaining,
        'membership_status': user.membership_status,
        'user_name': user.get_full_name() or user.username,
        'telegram_linked': bool(user.telegram_chat_id),
        'telegram_bot_configured': bool(_token()),
        'telegram_bot_name': os.environ.get('TELEGRAM_BOT_NAME', ''),
    })


# ---------------------------------------------------------------------------
# Partner dashboard
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_partner, login_url='/auth/login/', redirect_field_name=None)
def partner_dashboard(request):
    """Partner dashboard: member search, visit log, statistics."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, _('⚠️ Partner profile not configured. Contact administrator.'))
        return redirect('core:home')
    except AttributeError:
        messages.error(request, _('⚠️ System error: Database migration required. Contact administrator.'))
        return redirect('core:home')

    visits = Visit.objects.filter(partner=partner).select_related('member').order_by('-timestamp')
    total_visits = visits.count()
    verified_visits = visits.filter(pin_verified=True).count()
    total_cost = visits.aggregate(Sum('cost'))['cost__sum'] or 0
    unique_members = visits.values('member').distinct().count()

    search_results = None
    search_form = MemberSearchForm(request.GET or None)

    if search_form.is_valid():
        query = search_form.cleaned_data.get('query', '').strip()
        if query:
            search_filter = (
                Q(pseudonym__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(username__icontains=query)
            )
            if len(query.replace('-', '')) >= 32:
                try:
                    import uuid
                    search_filter |= Q(permanent_id=uuid.UUID(query))
                except ValueError:
                    try:
                        c = query.replace('-', '')
                        if len(c) == 32:
                            fmt = f"{c[0:8]}-{c[8:12]}-{c[12:16]}-{c[16:20]}-{c[20:32]}"
                            search_filter |= Q(permanent_id=uuid.UUID(fmt))
                    except (ValueError, IndexError):
                        pass
            search_results = User.objects.filter(search_filter).distinct()[:20]

    paginator = Paginator(visits, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    now = timezone.now()

    context = {
        'partner': partner,
        'search_form': search_form,
        'search_results': search_results,
        'visits': page_obj,
        'total_visits': total_visits,
        'verified_visits': verified_visits,
        'total_cost': total_cost,
        'unique_members': unique_members,
        'now': now,
        'edit_window': EDIT_WINDOW,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'users/partials/partner_search_results.html', context)

    return render(request, 'users/partner_dashboard.html', context)


# ---------------------------------------------------------------------------
# Log visit
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_partner, login_url='/auth/login/', redirect_field_name=None)
@require_http_methods(["GET", "POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def log_visit(request, member_id):
    """Log a visit for a member. Includes brute-force protection + idempotency."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, _('Partner profile not found.'))
        return redirect('users:partner_dashboard')

    member = get_object_or_404(User, id=member_id)

    if member.membership_status != 'active':
        messages.warning(request, _('⚠️ Warning: %(name)s membership is currently inactive.') % {'name': member.get_full_name()})

    if request.method == 'POST':
        form = VisitForm(request.POST)
        if form.is_valid():
            now = timezone.now()

            # Brute-force check
            if member.pin_lockout_until and member.pin_lockout_until > now:
                remaining = int((member.pin_lockout_until - now).total_seconds() // 60) + 1
                messages.error(
                    request,
                    _('🔒 PIN entry locked for this member. Please wait %(remaining)d minute(s).') % {'remaining': remaining}
                )
                return render(request, 'users/log_visit.html', {
                    'form': form, 'member': member, 'partner': partner
                })

            provided_pin = form.cleaned_data['pin']

            if not member.totp_secret:
                messages.error(request, _('⚠️ Member PIN system not configured. Contact administrator.'))
                return redirect('users:partner_dashboard')

            if member.verify_pin(provided_pin):
                # Idempotency check
                cutoff = now - timezone.timedelta(seconds=IDEMPOTENCY_WINDOW)
                existing = Visit.objects.filter(
                    partner=partner,
                    member=member,
                    service_type=form.cleaned_data['service_type'],
                    cost=form.cleaned_data.get('cost'),
                    timestamp__gte=cutoff,
                ).first()

                if existing:
                    member_name = member.get_full_name() or member.username
                    messages.warning(
                        request,
                        _('ℹ️ Duplicate detected: identical visit already logged within the last 5 minutes '
                          'for %(name)s. No new record created.') % {'name': member_name}
                    )
                    return redirect('users:partner_dashboard')

                # Save visit
                visit = form.save(commit=False)
                visit.member = member
                visit.partner = partner
                visit.pin_verified = True
                visit.status = 'ACTIVE'
                visit.save()

                # Reset brute-force counter
                if member.failed_pin_attempts:
                    member.failed_pin_attempts = 0
                    member.pin_lockout_until = None
                    member.save(update_fields=['failed_pin_attempts', 'pin_lockout_until'])

                try:
                    notify_visit_confirmed(visit)
                except Exception as exc:
                    logger.error("notify_visit_confirmed failed: %s", exc)

                member_name = member.get_full_name() or member.username
                cost_display = f'{visit.cost} CHF' if visit.cost else 'N/A'
                messages.success(
                    request,
                    _('✅ Visit logged! Member: %(name)s | '
                      'Service: %(service)s | Cost: %(cost)s') % {
                        'name': member_name,
                        'service': visit.get_service_type_display(),
                        'cost': cost_display,
                    }
                )
                return redirect('users:partner_dashboard')

            else:
                # Wrong PIN
                member.failed_pin_attempts = (member.failed_pin_attempts or 0) + 1
                if member.failed_pin_attempts >= PIN_MAX_ATTEMPTS:
                    member.pin_lockout_until = now + timezone.timedelta(minutes=PIN_LOCKOUT_MINUTES)
                    member.failed_pin_attempts = 0
                    member.save(update_fields=['failed_pin_attempts', 'pin_lockout_until'])
                    form.add_error('pin', _('🔒 Too many wrong PINs. PIN locked for %(minutes)d minutes.') % {'minutes': PIN_LOCKOUT_MINUTES})
                else:
                    attempts_left = PIN_MAX_ATTEMPTS - member.failed_pin_attempts
                    member.save(update_fields=['failed_pin_attempts'])
                    form.add_error('pin', _('❌ Invalid PIN. %(left)d attempt(s) remaining before lockout.') % {'left': attempts_left})
    else:
        form = VisitForm()

    return render(request, 'users/log_visit.html', {
        'form': form,
        'member': member,
        'partner': partner,
    })


# ---------------------------------------------------------------------------
# Edit visit
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_partner, login_url='/auth/login/', redirect_field_name=None)
@require_http_methods(["GET", "POST"])
def edit_visit(request, visit_id):
    """Edit a visit within the 20-minute window."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, _('Partner profile not found.'))
        return redirect('users:partner_dashboard')

    visit = get_object_or_404(Visit, id=visit_id, partner=partner)

    age = (timezone.now() - visit.timestamp).total_seconds()
    if age > EDIT_WINDOW:
        messages.error(request, _('⏰ Edit window expired. Visits can only be edited within 20 minutes of logging.'))
        return redirect('users:partner_dashboard')

    if visit.status == 'CANCELLED':
        messages.error(request, _('❌ Cancelled visits cannot be edited.'))
        return redirect('users:partner_dashboard')

    if request.method == 'POST':
        form = EditVisitForm(request.POST, instance=visit)
        if form.is_valid():
            reason = form.cleaned_data.get('reason', '')

            audit = VisitAudit(
                visit=visit,
                action=VisitAudit.ACTION_EDIT,
                previous_service_type=visit.get_service_type_display(),
                previous_service_description=visit.service_description,
                previous_cost=visit.cost,
                previous_comments=visit.comments,
                reason=reason,
                changed_by=request.user,
            )

            updated_visit = form.save(commit=False)
            updated_visit.status = 'EDITED'
            updated_visit.save()
            audit.save()

            try:
                notify_visit_edited(updated_visit, audit)
            except Exception as exc:
                logger.error("notify_visit_edited failed: %s", exc)

            messages.success(request, _('✅ Visit updated. Member notified via Telegram.'))
            return redirect('users:partner_dashboard')
    else:
        form = EditVisitForm(instance=visit)

    return render(request, 'users/edit_visit.html', {
        'form': form,
        'visit': visit,
        'partner': partner,
        'seconds_left': max(0, int(EDIT_WINDOW - age)),
    })


# ---------------------------------------------------------------------------
# Cancel visit
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_partner, login_url='/auth/login/', redirect_field_name=None)
@require_http_methods(["GET", "POST"])
def cancel_visit(request, visit_id):
    """Cancel a visit within the 20-minute window."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, _('Partner profile not found.'))
        return redirect('users:partner_dashboard')

    visit = get_object_or_404(Visit, id=visit_id, partner=partner)

    age = (timezone.now() - visit.timestamp).total_seconds()
    if age > EDIT_WINDOW:
        messages.error(request, _('⏰ Edit window expired. Visits can only be cancelled within 20 minutes of logging.'))
        return redirect('users:partner_dashboard')

    if visit.status == 'CANCELLED':
        messages.warning(request, _('This visit is already cancelled.'))
        return redirect('users:partner_dashboard')

    if request.method == 'POST':
        form = CancelVisitForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']

            audit = VisitAudit(
                visit=visit,
                action=VisitAudit.ACTION_CANCEL,
                previous_service_type=visit.get_service_type_display(),
                previous_service_description=visit.service_description,
                previous_cost=visit.cost,
                previous_comments=visit.comments,
                reason=reason,
                changed_by=request.user,
            )

            visit.status = 'CANCELLED'
            visit.save(update_fields=['status'])
            audit.save()

            try:
                notify_visit_cancelled(visit, audit)
            except Exception as exc:
                logger.error("notify_visit_cancelled failed: %s", exc)

            messages.success(request, _('✅ Visit cancelled. Member notified via Telegram.'))
            return redirect('users:partner_dashboard')
    else:
        form = CancelVisitForm()

    return render(request, 'users/cancel_visit.html', {
        'form': form,
        'visit': visit,
        'partner': partner,
        'seconds_left': max(0, int(EDIT_WINDOW - age)),
    })


# ---------------------------------------------------------------------------
# Telegram bot test page
# ---------------------------------------------------------------------------

@login_required
def test_telegram_view(request):
    """Staff-only page: configure webhook and verify bot setup."""
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden(_("Access restricted to administrators only."))

    import html as _html
    from django.middleware.csrf import get_token
    from django.http import HttpResponse
    from users.telegram import token as _token

    result_html = ""
    webhook_secret = _webhook_secret()
    webhook_url = request.build_absolute_uri(f"/auth/telegram/webhook/{webhook_secret}/") if webhook_secret else ""

    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "set_webhook":
                if not webhook_secret:
                    result_html = '<div class="alert err">❌ TELEGRAM_WEBHOOK_SECRET не задан в DigitalOcean.</div>'
                else:
                    ok, message = set_webhook(webhook_url)
                    css = "ok" if ok else "err"
                    icon = "✅" if ok else "❌"
                    result_html = f'<div class="alert {css}">{icon} {_html.escape(message)}</div>'
                    if ok:
                        import asyncio
                        try:
                            asyncio.run(init_bot_commands())
                            result_html += '<div class="alert ok">✅ Команды бота зарегистрированы в Telegram</div>'
                        except Exception as exc_cmd:
                            result_html += f'<div class="alert err">⚠️ Команды не установлены: {_html.escape(str(exc_cmd))}</div>'
            else:
                result_html = '<div class="alert err">❌ Неизвестное действие.</div>'
        except Exception as exc:
            logger.error("test_telegram_view failed: %s", exc)
            result_html = f'<div class="alert err">❌ Ошибка: {_html.escape(str(exc))}</div>'

    token_set  = bool(_token())
    secret_set = bool(webhook_secret)
    webhook_info = get_webhook_info() if token_set else {}
    current_url = (webhook_info.get("result") or {}).get("url", "") if isinstance(webhook_info, dict) else ""

    token_badge = (
        '<span class="badge ok">✅ TELEGRAM_BOT_TOKEN задан</span>' if token_set
        else '<span class="badge err">❌ TELEGRAM_BOT_TOKEN не задан</span>'
    )
    secret_badge = (
        '<span class="badge ok">✅ TELEGRAM_WEBHOOK_SECRET задан</span>' if secret_set
        else '<span class="badge err">❌ TELEGRAM_WEBHOOK_SECRET не задан</span>'
    )

    webhook_block = (
        f'<div class="alert ok">Текущий webhook: <code>{_html.escape(current_url)}</code></div>'
        if current_url
        else '<div class="alert err">Webhook пока не установлен.</div>'
    )

    csrf = get_token(request)

    html_page = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Тест Telegram бота — IESA Sport</title>
  <style>
    body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:40px 20px;color:#333}}
    .card{{background:#fff;max-width:580px;margin:0 auto;padding:36px;border-radius:12px;
           box-shadow:0 4px 24px rgba(0,0,0,.1)}}
    h2{{margin:0 0 4px}}
    .sub{{color:#777;font-size:13px;margin-bottom:20px}}
    .badges{{margin-bottom:20px}}
    .badge{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;
             margin-right:6px;margin-bottom:6px}}
    .badge.ok{{background:#d4edda;color:#155724}}
    .badge.err{{background:#f8d7da;color:#721c24}}
    .badge.warn{{background:#fff3cd;color:#856404}}
    .info-box{{background:#e8f4fd;border-left:4px solid #3498db;
               padding:14px 16px;border-radius:0 8px 8px 0;margin-bottom:22px;font-size:13px;line-height:1.6}}
    .info-box code{{background:#d0e8f8;padding:1px 5px;border-radius:4px;font-size:12px}}
    label{{display:block;font-size:13px;font-weight:bold;margin-bottom:6px;margin-top:14px}}
    input[type=text],textarea{{width:100%;box-sizing:border-box;padding:10px 14px;
                       border:1px solid #ccc;border-radius:8px;font-size:14px;font-family:inherit}}
    textarea{{height:100px;resize:vertical}}
    input:focus,textarea:focus{{outline:none;border-color:#29b6f6;
                                box-shadow:0 0 0 3px rgba(41,182,246,.2)}}
    button{{margin-top:16px;width:100%;padding:12px;
            background:linear-gradient(135deg,#29b6f6,#0288d1);
            color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer;font-weight:bold}}
    button:hover{{opacity:.88}}
    .alert{{margin-top:18px;padding:14px 18px;border-radius:8px;font-size:14px}}
    .alert.ok{{background:#d4edda;color:#155724}}
    .alert.err{{background:#f8d7da;color:#721c24}}
    .back{{display:block;text-align:center;margin-top:18px;font-size:13px;color:#999;text-decoration:none}}
    .back:hover{{color:#333}}
  </style>
</head>
<body>
  <div class="card">
        <h2>🤖 Telegram Bot Setup</h2>
        <p class="sub">Только для администраторов. Настройка webhook, чтобы бот отвечал пользователю без TELEGRAM_CHAT_ID.</p>

        <div class="badges">{token_badge}{secret_badge}</div>

        {webhook_block}

    <div class="info-box">
      <b>Где задать переменные:</b><br>
      DigitalOcean App Platform → твоё приложение → <b>Settings</b> → <b>App-Level Env Vars</b><br><br>
      <code>TELEGRAM_BOT_TOKEN</code> — токен от @BotFather<br>
            <code>TELEGRAM_WEBHOOK_SECRET</code> — случайная строка (например 32+ символа)<br><br>
            Webhook URL для Telegram:<br>
            <code>{_html.escape(webhook_url or 'Сначала задай TELEGRAM_WEBHOOK_SECRET')}</code><br><br>
            После установки webhook: открой бота в Telegram, нажми <b>Start</b> и отправь любое сообщение.
            Бот ответит прямо в этот чат.
    </div>

    <form method="post">
      <input type="hidden" name="csrfmiddlewaretoken" value="{csrf}">
            <input type="hidden" name="action" value="set_webhook">
            <button type="submit">🔗 Установить webhook в Telegram</button>
    </form>
    {result_html}
    <a href="/" class="back">← На главную</a>
  </div>
</body>
</html>"""

    return HttpResponse(html_page)



# ---------------------------------------------------------------------------
# Method A: Link code (user writes /link in bot → enters code on website)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def connect_telegram_code_view(request):
    """Accept 6-digit code from Telegram bot and link the account."""
    import html as _html
    from django.utils import timezone as tz
    from users.telegram import consume_link_code, send_message

    error = ""

    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        if not code.isdigit() or len(code) != 6:
            error = _("Code must be exactly 6 digits.")
        else:
            chat_id = consume_link_code(code)
            if not chat_id:
                error = _("Code is invalid or expired. Get a new one with /link in the bot.")
            else:
                from .models import User
                if User.objects.filter(telegram_chat_id=int(chat_id)).exclude(pk=request.user.pk).exists():
                    error = _("This Telegram account is already linked to another user.")
                else:
                    request.user.telegram_chat_id = int(chat_id)
                    request.user.telegram_linked_at = tz.now()
                    request.user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
                    send_message(
                        f"✅ Telegram привязан к аккаунту <b>{_html.escape(request.user.username)}</b> на IESA Sport!",
                        chat_id=chat_id,
                    )
                    messages.success(request, _("✅ Telegram linked successfully!"))
                    return redirect("users:profile")

    return render(request, "users/connect_telegram_code.html", {
        "error": error,
        "telegram_bot_name": os.environ.get("TELEGRAM_BOT_NAME", ""),
    })


@login_required
@require_http_methods(["POST"])
def disconnect_telegram_view(request):
    """Unlink Telegram from the current user account."""
    request.user.telegram_chat_id = None
    request.user.telegram_linked_at = None
    request.user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
    messages.success(request, _("Telegram disconnected from your account."))
    return redirect("users:profile")


# ---------------------------------------------------------------------------
# Method B: Telegram Login Widget callback
# ---------------------------------------------------------------------------

@login_required
def telegram_login_callback_view(request):
    """
    Telegram Login Widget sends user here after tapping 'Login with Telegram'.
    Verifies HMAC signature and links telegram_chat_id to the logged-in user.
    """
    import time
    from django.utils import timezone as tz
    from users.telegram import verify_telegram_auth

    flat = {k: (v[0] if isinstance(v, list) else v) for k, v in dict(request.GET).items()}

    if not flat.get("hash") or not verify_telegram_auth(flat):
        messages.error(request, _("Telegram signature verification failed."))
        return redirect("users:profile")

    if time.time() - int(flat.get("auth_date", 0)) > 300:
        messages.error(request, _("Telegram request expired. Please try again."))
        return redirect("users:profile")

    tg_id = int(flat.get("id", 0))
    if not tg_id:
        messages.error(request, _("Unable to retrieve Telegram ID."))
        return redirect("users:profile")

    from .models import User
    if User.objects.filter(telegram_chat_id=tg_id).exclude(pk=request.user.pk).exists():
        messages.error(request, _("This Telegram account is already linked to another user."))
        return redirect("users:profile")

    request.user.telegram_chat_id = tg_id
    request.user.telegram_linked_at = tz.now()
    request.user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
    tg_name = flat.get("username") or flat.get("first_name", "")
    messages.success(request, _("✅ Telegram (%(name)s) linked successfully!") % {'name': tg_name})
    return redirect("users:profile")


@csrf_exempt
@require_http_methods(["POST"])
async def telegram_webhook_view(request, secret):
    import json as _json
    import logging as _logging
    _wlog = _logging.getLogger("users.telegram.webhook")

    try:
        payload = _json.loads(request.body.decode("utf-8") or "{}")
    except Exception as exc:
        _wlog.error("Webhook JSON parse error: %s", exc)
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    # Log every incoming update type so we can see what Telegram is sending
    update_type = (
        "callback_query" if "callback_query" in payload else
        "message"        if "message"        in payload else
        "chat_member"    if "chat_member"    in payload else
        "edited_message" if "edited_message" in payload else
        list(payload.keys())[:2]
    )
    _wlog.info("Webhook received: type=%s update_id=%s", update_type, payload.get("update_id"))
    if "callback_query" in payload:
        cb = payload["callback_query"]
        _wlog.info("  callback_query id=%s data=%r chat=%s",
                   cb.get("id"), cb.get("data"),
                   (cb.get("message") or {}).get("chat", {}).get("id"))

    from users.telegram.config import is_active
    if is_active():
        try:
            await process_incoming_update(payload)
        except Exception as exc:
            _wlog.exception("process_incoming_update raised: %s", exc)
    else:
        _wlog.warning("Bot is_active()=False — update ignored (token set: %s)",
                      bool(payload))
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Server time API
# ---------------------------------------------------------------------------

def server_time(request):
    """Return current UTC timestamp as JSON for client-side sync."""
    return JsonResponse({'timestamp': timezone.now().isoformat()})
