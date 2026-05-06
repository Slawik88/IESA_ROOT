"""
Membership Verification System Views
"""
import asyncio
import logging
import os

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Max
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
    PartnerProfileForm,
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
# Утилиты
# ---------------------------------------------------------------------------

import uuid as _uuid_mod


def _try_parse_uuid(s: str):
    """Надёжно парсит UUID из строки с дефисами или без. Возвращает UUID или None (B1-14)."""
    s = s.strip()
    try:
        return _uuid_mod.UUID(s)
    except ValueError:
        pass
    clean = s.replace('-', '')
    if len(clean) == 32:
        try:
            return _uuid_mod.UUID(f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}")
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def is_partner(user):
    """Check if user has partner access — via is_partner flag OR existing partner_profile.

    is_partner boolean is the authoritative flag (synced via signals_partner.py).
    Falls back to partner_profile FK check for legacy/inconsistent data.

    Result кэшируется на экземпляре пользователя, чтобы избежать повторных DB-запросов
    при каждом вызове @partner_required декоратора в одном request/response цикле (B1-08).
    """
    # Быстрый путь: уже проверяли в этом request
    if hasattr(user, '_is_partner_cached'):
        return user._is_partner_cached

    try:
        if bool(user.is_partner):
            user._is_partner_cached = True
            return True
        # Fallback: check FK directly (handles inconsistent data where flag wasn't synced)
        has_profile = Partner.objects.filter(user=user).exists()
        if has_profile:
            # Auto-heal: sync the flag so templates see correct value
            User.objects.filter(pk=user.pk).update(is_partner=True)
            user.is_partner = True
            logger.info("is_partner auto-healed for user: %s", user.username)
        user._is_partner_cached = has_profile
        return has_profile
    except Exception as exc:
        logger.error("is_partner check error: %s", exc)
        return False


def partner_required(view_func):
    """Decorator: unauthenticated → login page; authenticated non-partner → access denied page."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_partner(request.user):
            return render(request, 'users/partner_access_denied.html', {
                'requested_url': request.path,
            }, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


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
        'telegram_bot_name': os.environ.get('TELEGRAM_BOT_NAME', 'IESA_Administrator_bot'),
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

    # Member's own visit history (what they see of their own visits at partners)
    total_member_visits = Visit.objects.filter(member=user).count()
    recent_visits = (
        Visit.objects
        .filter(member=user)
        .select_related('partner', 'partner__user')
        .order_by('-timestamp')[:20]
    )

    return render(request, 'users/member_cabinet.html', {
        'current_pin': current_pin,
        'seconds_remaining': seconds_remaining,
        'membership_status': user.membership_status,
        'user_name': user.get_full_name() or user.username,
        'user': user,
        'telegram_linked': bool(user.telegram_chat_id),
        'telegram_bot_configured': bool(_token()),
        'telegram_bot_name': os.environ.get('TELEGRAM_BOT_NAME', 'IESA_Administrator_bot'),
        'card_active': user.card_active,
        'card_issued_at': user.card_issued_at,
        'recent_visits': recent_visits,
        'total_visits': total_member_visits,
    })


# ---------------------------------------------------------------------------
# Partner dashboard
# ---------------------------------------------------------------------------

@partner_required
def partner_dashboard(request):
    """Partner dashboard: member search, visit log, statistics."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        if request.user.is_partner:
            # Auto-create a minimal Partner record for is_partner flag users
            partner = Partner.objects.create(
                user=request.user,
                company_name=request.user.get_full_name() or request.user.username,
            )
        else:
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

    # Today's activity
    today = timezone.localdate()
    today_visits_qs = visits.filter(timestamp__date=today)
    today_count = today_visits_qs.count()
    today_revenue = today_visits_qs.aggregate(r=Sum('cost'))['r'] or 0
    today_visit_list = today_visits_qs.order_by('-timestamp')[:20]

    # Recent (returning) clients sorted by last visit
    recent_members = (
        visits.filter(status='ACTIVE')
        .values('member__id', 'member__username', 'member__first_name',
                'member__last_name', 'member__pseudonym',
                'member__membership_status', 'member__avatar')
        .annotate(last_visit=Max('timestamp'), visit_count=Count('id'))
        .order_by('-last_visit')[:12]
    )

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
                _parsed_uuid = _try_parse_uuid(query)
                if _parsed_uuid:
                    search_filter |= Q(permanent_id=_parsed_uuid)
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
        'today_count': today_count,
        'today_revenue': today_revenue,
        'today_visit_list': today_visit_list,
        'recent_members': recent_members,
        'now': now,
        'edit_window': EDIT_WINDOW,
        'edit_window_cutoff': now - timezone.timedelta(seconds=EDIT_WINDOW),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'users/partials/partner_search_results.html', context)

    return render(request, 'users/partner_dashboard.html', context)


# ---------------------------------------------------------------------------
# Log visit
# ---------------------------------------------------------------------------

@partner_required
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

                # Save visit + reset counter atomically (B1-03, B1-04)
                from django.db import transaction as _tx
                with _tx.atomic():
                    visit = form.save(commit=False)
                    visit.member = member
                    visit.partner = partner
                    visit.pin_verified = True
                    visit.status = 'ACTIVE'
                    visit.save()

                    # Reset brute-force counter atomically inside same tx
                    if member.failed_pin_attempts:
                        User.objects.filter(pk=member.pk).update(
                            failed_pin_attempts=0,
                            pin_lockout_until=None,
                        )
                        member.failed_pin_attempts = 0
                        member.pin_lockout_until = None

                # Уведомление — в фоновом потоке, не блокируем response (B1-05)
                if getattr(member, 'telegram_chat_id', None):
                    import threading as _thr
                    _visit_id = visit.pk

                    def _notify_bg():
                        try:
                            from users.models import Visit as _Visit
                            from users.telegram.notify import notify_visit_confirmed as _notify
                            _v = _Visit.objects.select_related('member', 'partner').get(pk=_visit_id)
                            _notify(_v)
                        except Exception as _exc:
                            logger.error("bg notify_visit_confirmed failed: %s", _exc)

                    _thr.Thread(target=_notify_bg, daemon=True).start()
                else:
                    messages.info(
                        request,
                        _('ℹ️ Telegram notification not sent — member has no Telegram linked.')
                    )

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
                # Wrong PIN — атомарный инкремент через F() (B1-02)
                from django.db.models import F as _F
                from django.db import transaction as _tx
                with _tx.atomic():
                    User.objects.filter(pk=member.pk).update(
                        failed_pin_attempts=_F('failed_pin_attempts') + 1
                    )
                    member.refresh_from_db(fields=['failed_pin_attempts'])

                if member.failed_pin_attempts >= PIN_MAX_ATTEMPTS:
                    User.objects.filter(pk=member.pk).update(
                        pin_lockout_until=now + timezone.timedelta(minutes=PIN_LOCKOUT_MINUTES),
                        failed_pin_attempts=0,
                    )
                    member.failed_pin_attempts = 0
                    form.add_error('pin', _('🔒 Too many wrong PINs. PIN locked for %(minutes)d minutes.') % {'minutes': PIN_LOCKOUT_MINUTES})
                else:
                    attempts_left = PIN_MAX_ATTEMPTS - member.failed_pin_attempts
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

@partner_required
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

@partner_required
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
# Partner: per-member visit history
# ---------------------------------------------------------------------------

@partner_required
def partner_member_visits(request, member_id):
    """Full visit history between THIS partner and ONE member."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, _('Partner profile not found.'))
        return redirect('core:home')

    member = get_object_or_404(User, id=member_id)
    member_visits = (
        Visit.objects
        .filter(partner=partner, member=member)
        .order_by('-timestamp')
    )
    total = member_visits.count()
    total_revenue = member_visits.aggregate(r=Sum('cost'))['r'] or 0
    verified_count = member_visits.filter(pin_verified=True).count()
    last_visit = member_visits.first()

    paginator = Paginator(member_visits, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'users/partner_member_visits.html', {
        'partner': partner,
        'member': member,
        'visits': page_obj,
        'total': total,
        'total_revenue': total_revenue,
        'verified_count': verified_count,
        'last_visit': last_visit,
        'now': timezone.now(),
        'edit_window': EDIT_WINDOW,
        'edit_window_cutoff': timezone.now() - timezone.timedelta(seconds=EDIT_WINDOW),
    })


# ---------------------------------------------------------------------------
# Partner analytics
# ---------------------------------------------------------------------------

@partner_required
def partner_analytics(request):
    """Analytics dashboard: charts and statistics for the last 30 days."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, _('Partner profile not found.'))
        return redirect('core:home')

    now = timezone.now()
    thirty_days_ago = now - timezone.timedelta(days=30)
    ninety_days_ago = now - timezone.timedelta(days=90)

    all_visits = Visit.objects.filter(partner=partner)
    visits_30 = all_visits.filter(timestamp__gte=thirty_days_ago)
    visits_90 = all_visits.filter(timestamp__gte=ninety_days_ago)

    from django.db.models.functions import TruncDate
    import json

    daily_data = (
        visits_30
        .annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(count=Count('id'), revenue=Sum('cost'))
        .order_by('day')
    )

    service_breakdown = (
        all_visits
        .values('service_type')
        .annotate(count=Count('id'), total=Sum('cost'))
        .order_by('-count')[:20]  # Лимит топ-20 категорий (B1-15)
    )

    top_members = (
        visits_90
        .filter(status='ACTIVE')
        .values('member__id', 'member__first_name', 'member__last_name',
                'member__username', 'member__pseudonym')
        .annotate(visit_count=Count('id'), total_spent=Sum('cost'))
        .order_by('-visit_count')[:10]
    )

    total_all = all_visits.count()
    total_30 = visits_30.count()
    revenue_30 = visits_30.aggregate(r=Sum('cost'))['r'] or 0
    verified_30 = visits_30.filter(pin_verified=True).count()
    unique_members_30 = visits_30.values('member').distinct().count()

    service_labels = [item['service_type'] for item in service_breakdown]
    service_counts = [item['count'] for item in service_breakdown]

    context = {
        'partner': partner,
        'total_all': total_all,
        'total_30': total_30,
        'revenue_30': revenue_30,
        'verified_30': verified_30,
        'unique_members_30': unique_members_30,
        'top_members': top_members,
        'service_breakdown': service_breakdown,
        'service_labels_json': json.dumps(service_labels),
        'service_counts_json': json.dumps(service_counts),
        'chart_dates_json': json.dumps([str(d['day']) for d in daily_data]),
        'chart_counts_json': json.dumps([d['count'] for d in daily_data]),
        'chart_revenue_json': json.dumps([float(d['revenue'] or 0) for d in daily_data]),
    }
    return render(request, 'users/partner_analytics.html', context)


# ---------------------------------------------------------------------------
# Partner profile edit
# ---------------------------------------------------------------------------

@partner_required
@require_http_methods(['GET', 'POST'])
def partner_profile_edit(request):
    """Edit partner company profile (name, business type)."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, _('Partner profile not found.'))
        return redirect('core:home')

    if request.method == 'POST':
        form = PartnerProfileForm(request.POST, instance=partner)
        if form.is_valid():
            form.save()
            messages.success(request, _('\u2705 Partner profile updated successfully.'))
            return redirect('users:partner_dashboard')
    else:
        form = PartnerProfileForm(instance=partner)

    return render(request, 'users/partner_profile_edit.html', {
        'form': form,
        'partner': partner,
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
                        # asyncio.run() падает если event loop уже существует (ASGI).
                        # Создаём изолированный loop в отдельном потоке (B1-09).
                        import threading as _thr
                        _cmd_result = {}

                        def _run_init():
                            import asyncio
                            loop = asyncio.new_event_loop()
                            try:
                                loop.run_until_complete(init_bot_commands())
                                _cmd_result['ok'] = True
                            except Exception as _e:
                                _cmd_result['err'] = str(_e)
                            finally:
                                loop.close()

                        t = _thr.Thread(target=_run_init, daemon=True)
                        t.start()
                        t.join(timeout=10)
                        if _cmd_result.get('ok'):
                            result_html += '<div class="alert ok">✅ Команды бота зарегистрированы в Telegram</div>'
                        elif 'err' in _cmd_result:
                            result_html += f'<div class="alert err">⚠️ Команды не установлены: {_html.escape(_cmd_result["err"])}</div>'
                        else:
                            result_html += '<div class="alert err">⚠️ Timeout регистрации команд (>10s)</div>'
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
                    request.user.telegram_linked_at = timezone.now()
                    request.user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
                    send_message(
                        f"✅ Telegram привязан к аккаунту <b>{_html.escape(request.user.username)}</b> на IESA Sport!",
                        chat_id=chat_id,
                    )
                    messages.success(request, _("✅ Telegram linked successfully!"))
                    return redirect("users:profile")

    return render(request, "users/connect_telegram_code.html", {
        "error": error,
        "telegram_bot_name": os.environ.get('TELEGRAM_BOT_NAME', 'IESA_Administrator_bot'),
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
    request.user.telegram_linked_at = timezone.now()
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

    # B3-03: manual rate limit — @ratelimit decorator не поддерживает async views
    _ip = request.META.get('REMOTE_ADDR', 'unknown')
    _rl_key = f'webhook_rl_{_ip}'
    from django.core.cache import cache
    _count = cache.get(_rl_key, 0)
    if _count >= 300:
        return JsonResponse({"ok": False}, status=429)
    cache.set(_rl_key, _count + 1, timeout=60)

    # Проверяем, что секрет в URL совпадает с ожидаемым
    from users.telegram.config import webhook_secret as _get_expected_secret
    expected = _get_expected_secret()
    if not expected or secret != expected:
        _wlog.warning("Webhook rejected: invalid secret (ip=%s)", request.META.get("REMOTE_ADDR"))
        return JsonResponse({"ok": False}, status=403)

    try:
        body = request.body.decode("utf-8")
        if not body:
            return JsonResponse({"ok": False, "error": "empty body"}, status=400)
        payload = _json.loads(body)
    except Exception as exc:
        _wlog.error("Webhook JSON parse error: %s", exc)
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    # B3-13: базовая валидация структуры update
    if not isinstance(payload, dict) or "update_id" not in payload:
        _wlog.warning("Webhook: invalid payload structure (keys=%s)", list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__)
        return JsonResponse({"ok": False, "error": "invalid update"}, status=400)

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
        except asyncio.CancelledError:
            # B3-14: CancelledError — graceful shutdown, пробрасываем
            _wlog.warning("Webhook processing cancelled (update_id=%s)", payload.get("update_id"))
            raise
        except Exception as exc:
            _wlog.exception("process_incoming_update raised: %s", exc)
            # B3-02: возвращаем 500 чтобы Telegram переотправил update
            return JsonResponse({"ok": False, "error": "processing failed"}, status=500)
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
