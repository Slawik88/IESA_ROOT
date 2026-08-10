"""Partner portal views: dashboard, visit management, analytics, profile edit."""
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from ..constants import EDIT_WINDOW, IDEMPOTENCY_WINDOW, PIN_LOCKOUT_MINUTES, PIN_MAX_ATTEMPTS
from ..forms_verification import CancelVisitForm, EditVisitForm, MemberSearchForm, PartnerProfileForm, VisitForm
from ..models import Partner, User, Visit, VisitAudit
from .utils import _try_parse_uuid, partner_required

logger = logging.getLogger(__name__)


@partner_required
def partner_dashboard(request):
    """Partner dashboard: member search, visit log, statistics."""
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        # A partner flag can be granted before the business profile is filled
        # in. Keep the portal usable and create the minimal one-to-one record
        # atomically instead of raising a production 500.
        if not request.user.is_partner:
            messages.error(request, _('⚠️ Partner profile not configured. Contact administrator.'))
            return redirect('core:home')
        partner, _created = Partner.objects.get_or_create(
            user=request.user,
            defaults={
                'company_name': request.user.get_full_name() or request.user.username,
            },
        )

    visits = Visit.objects.filter(partner=partner).select_related('member').order_by('-timestamp')
    _stats = Visit.objects.filter(partner=partner).aggregate(
        total_visits=Count('id'),
        verified_visits=Count('id', filter=Q(pin_verified=True)),
        total_cost=Sum('cost'),
        unique_members=Count('member', distinct=True),
    )
    total_visits    = _stats['total_visits']    or 0
    verified_visits = _stats['verified_visits'] or 0
    total_cost      = _stats['total_cost']      or 0
    unique_members  = _stats['unique_members']  or 0

    today = timezone.localdate()
    today_visits_qs = visits.filter(timestamp__date=today)
    today_count     = today_visits_qs.count()
    today_revenue   = today_visits_qs.aggregate(r=Sum('cost'))['r'] or 0
    today_visit_list = today_visits_qs.order_by('-timestamp')[:20]

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
            sf = (Q(pseudonym__icontains=query) | Q(first_name__icontains=query) |
                  Q(last_name__icontains=query)  | Q(username__icontains=query))
            if len(query.replace('-', '')) >= 32:
                _parsed = _try_parse_uuid(query)
                if _parsed:
                    sf |= Q(permanent_id=_parsed)
            search_results = User.objects.filter(sf).distinct()[:20]

    page_obj = Paginator(visits, 15).get_page(request.GET.get('page'))
    now = timezone.now()
    # Interactive tour (2026-05-27) — показываем при первом заходе партнёра
    _tours = request.user.tours_completed or {}
    context = {
        'partner': partner, 'search_form': search_form, 'search_results': search_results,
        'visits': page_obj, 'total_visits': total_visits, 'verified_visits': verified_visits,
        'total_cost': total_cost, 'unique_members': unique_members,
        'today_count': today_count, 'today_revenue': today_revenue, 'today_visit_list': today_visit_list,
        'recent_members': recent_members, 'now': now,
        'edit_window': EDIT_WINDOW,
        'edit_window_cutoff': now - timezone.timedelta(seconds=EDIT_WINDOW),
        'show_tour': not _tours.get('partner', False),
        'tour_name': 'partner',
    }
    if request.headers.get('HX-Request'):
        return render(request, 'users/partials/partner_search_results.html', context)
    return render(request, 'users/partner_dashboard.html', context)


@partner_required
@require_http_methods(["GET", "POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def log_visit(request, member_id):
    """Логировать визит участника. Brute-force защита + идемпотентность."""
    partner = request.user.partner_profile
    member  = get_object_or_404(User, id=member_id)

    if member.membership_status != 'active':
        messages.warning(request, _(
            '⚠️ Warning: %(name)s membership is currently inactive.'
        ) % {'name': member.get_full_name()})

    if request.method == 'POST':
        form = VisitForm(request.POST)
        if form.is_valid():
            now = timezone.now()
            from ..services.visit_service import check_pin_lockout, process_pin_attempt, check_idempotent_visit

            locked, remaining = check_pin_lockout(member, now)
            if locked:
                messages.error(request, _(
                    '🔒 PIN entry locked for this member. Please wait %(remaining)d minute(s).'
                ) % {'remaining': remaining})
                return render(request, 'users/log_visit.html', {'form': form, 'member': member, 'partner': partner})

            if not member.totp_secret:
                messages.error(request, _('⚠️ Member PIN system not configured. Contact administrator.'))
                return redirect('users:partner_dashboard')

            pin_ok, pin_error = process_pin_attempt(member, form.cleaned_data['pin'], now)
            if not pin_ok:
                form.add_error('pin', pin_error)
            else:
                existing = check_idempotent_visit(partner, member, form.cleaned_data['service_type'], form.cleaned_data.get('cost'))
                if existing:
                    messages.warning(request, _(
                        'ℹ️ Duplicate detected: identical visit already logged within the last 5 minutes for %(name)s. No new record created.'
                    ) % {'name': member.get_full_name() or member.username})
                    return redirect('users:partner_dashboard')

                from django.db import transaction as _tx
                with _tx.atomic():
                    visit = form.save(commit=False)
                    visit.member = member; visit.partner = partner
                    visit.pin_verified = True; visit.status = 'ACTIVE'
                    visit.save()

                from ..services.visit_notifications import notify_visit_logged as _nv
                _nv(visit, partner, member)
                if not getattr(member, 'telegram_chat_id', None):
                    messages.info(request, _('ℹ️ Member has no Telegram linked — in-site notification sent instead.'))

                messages.success(request, _(
                    '✅ Visit logged! Member: %(name)s | Service: %(service)s | Cost: %(cost)s'
                ) % {
                    'name':    member.get_full_name() or member.username,
                    'service': visit.get_service_type_display(),
                    'cost':    f'{visit.cost} CHF' if visit.cost else 'N/A',
                })
                return redirect('users:partner_dashboard')
    else:
        form = VisitForm()
    return render(request, 'users/log_visit.html', {'form': form, 'member': member, 'partner': partner})


@partner_required
@require_http_methods(["GET", "POST"])
def edit_visit(request, visit_id):
    partner = request.user.partner_profile
    visit   = get_object_or_404(Visit, id=visit_id, partner=partner)
    age     = (timezone.now() - visit.timestamp).total_seconds()

    if age > EDIT_WINDOW:
        messages.error(request, _('⏰ Edit window expired. Visits can only be edited within 20 minutes of logging.'))
        return redirect('users:partner_dashboard')
    if visit.status == 'CANCELLED':
        messages.error(request, _('❌ Cancelled visits cannot be edited.'))
        return redirect('users:partner_dashboard')

    if request.method == 'POST':
        form = EditVisitForm(request.POST, instance=visit)
        if form.is_valid():
            audit = VisitAudit(
                visit=visit, action=VisitAudit.ACTION_EDIT,
                previous_service_type=visit.get_service_type_display(),
                previous_service_description=visit.service_description,
                previous_cost=visit.cost, previous_comments=visit.comments,
                reason=form.cleaned_data.get('reason', ''), changed_by=request.user,
            )
            updated_visit = form.save(commit=False)
            updated_visit.status = 'EDITED'
            updated_visit.save(); audit.save()

            from ..services.visit_notifications import notify_visit_edited as _nv
            _nv(updated_visit, audit, partner)
            messages.success(request, _('✅ Visit updated. Member notified.'))
            return redirect('users:partner_dashboard')
    else:
        form = EditVisitForm(instance=visit)
    return render(request, 'users/edit_visit.html', {
        'form': form, 'visit': visit, 'partner': partner,
        'seconds_left': max(0, int(EDIT_WINDOW - age)),
        'crumbs': [
            {'label': _('Partner Portal'), 'url': '/auth/partner/dashboard/'},
            {'label': _('Visit History'),  'url': '/auth/partner/dashboard/#history-section'},
            {'label': f'#{visit.pk} — {_("Edit")}', 'url': None},
        ],
    })


@partner_required
@require_http_methods(["GET", "POST"])
def cancel_visit(request, visit_id):
    partner = request.user.partner_profile
    visit   = get_object_or_404(Visit, id=visit_id, partner=partner)
    age     = (timezone.now() - visit.timestamp).total_seconds()

    if age > EDIT_WINDOW:
        messages.error(request, _('⏰ Edit window expired. Visits can only be cancelled within 20 minutes of logging.'))
        return redirect('users:partner_dashboard')
    if visit.status == 'CANCELLED':
        messages.warning(request, _('This visit is already cancelled.'))
        return redirect('users:partner_dashboard')

    if request.method == 'POST':
        form = CancelVisitForm(request.POST)
        if form.is_valid():
            audit = VisitAudit(
                visit=visit, action=VisitAudit.ACTION_CANCEL,
                previous_service_type=visit.get_service_type_display(),
                previous_service_description=visit.service_description,
                previous_cost=visit.cost, previous_comments=visit.comments,
                reason=form.cleaned_data['reason'], changed_by=request.user,
            )
            visit.status = 'CANCELLED'; visit.save(update_fields=['status']); audit.save()
            from ..services.visit_notifications import notify_visit_cancelled as _nv
            _nv(visit, audit, partner)
            messages.success(request, _('✅ Visit cancelled. Member notified.'))
            return redirect('users:partner_dashboard')
    else:
        form = CancelVisitForm()
    return render(request, 'users/cancel_visit.html', {
        'form': form, 'visit': visit, 'partner': partner,
        'seconds_left': max(0, int(EDIT_WINDOW - age)),
        'crumbs': [
            {'label': _('Partner Portal'), 'url': '/auth/partner/dashboard/'},
            {'label': _('Visit History'),  'url': '/auth/partner/dashboard/#history-section'},
            {'label': f'#{visit.pk} — {_("Cancel")}', 'url': None},
        ],
    })


@partner_required
def partner_member_visits(request, member_id):
    partner = request.user.partner_profile
    member  = get_object_or_404(User, id=member_id)
    now = timezone.now()
    member_visits = Visit.objects.filter(partner=partner, member=member).order_by('-timestamp')
    total         = member_visits.count()
    total_revenue = member_visits.aggregate(r=Sum('cost'))['r'] or 0
    verified_count = member_visits.filter(pin_verified=True).count()
    last_visit    = member_visits.first()
    page_obj = Paginator(member_visits, 20).get_page(request.GET.get('page'))
    return render(request, 'users/partner_member_visits.html', {
        'partner': partner, 'member': member, 'visits': page_obj,
        'total': total, 'total_revenue': total_revenue,
        'verified_count': verified_count, 'last_visit': last_visit,
        'edit_window_cutoff': now - timezone.timedelta(seconds=EDIT_WINDOW),
        'crumbs': [
            {'label': _('Partner Portal'), 'url': '/auth/partner/dashboard/'},
            {'label': member.get_full_name() or member.username, 'url': None},
        ],
    })


@partner_required
def partner_analytics(request):
    from django.db.models.functions import TruncDate
    import json
    partner = request.user.partner_profile
    now = timezone.now()
    thirty_days_ago = now - timezone.timedelta(days=30)
    ninety_days_ago = now - timezone.timedelta(days=90)

    all_visits = Visit.objects.filter(partner=partner)
    visits_30  = all_visits.filter(timestamp__gte=thirty_days_ago)
    visits_90  = all_visits.filter(timestamp__gte=ninety_days_ago)

    daily_data = visits_30.annotate(day=TruncDate('timestamp')).values('day').annotate(count=Count('id'), revenue=Sum('cost')).order_by('day')
    service_breakdown = all_visits.values('service_type').annotate(count=Count('id'), total=Sum('cost')).order_by('-count')[:20]
    top_members = visits_90.filter(status='ACTIVE').values('member__id', 'member__first_name', 'member__last_name', 'member__username', 'member__pseudonym').annotate(visit_count=Count('id'), total_spent=Sum('cost')).order_by('-visit_count')[:10]

    _agg = visits_30.aggregate(total_30=Count('id'), revenue_30=Sum('cost'), verified_30=Count('id', filter=Q(pin_verified=True)), unique_30=Count('member', distinct=True))

    return render(request, 'users/partner_analytics.html', {
        'partner': partner,
        'total_all': all_visits.count(), 'total_30': _agg['total_30'] or 0,
        'revenue_30': _agg['revenue_30'] or 0, 'verified_30': _agg['verified_30'] or 0,
        'unique_members_30': _agg['unique_30'] or 0,
        'top_members': top_members, 'service_breakdown': service_breakdown,
        'service_labels_json': json.dumps([i['service_type'] for i in service_breakdown]),
        'service_counts_json': json.dumps([i['count'] for i in service_breakdown]),
        'chart_dates_json':   json.dumps([str(d['day']) for d in daily_data]),
        'chart_counts_json':  json.dumps([d['count'] for d in daily_data]),
        'chart_revenue_json': json.dumps([float(d['revenue'] or 0) for d in daily_data]),
        'crumbs': [
            {'label': _('Partner Portal'), 'url': '/auth/partner/dashboard/'},
            {'label': _('Analytics'), 'url': None},
        ],
    })


@partner_required
def partner_today_stats(request):
    """7a: HTMX-partial — полный stats-grid (today + all-time), polling каждые 60s."""
    partner = request.user.partner_profile
    today = timezone.localdate()
    all_qs = Visit.objects.filter(partner=partner)
    today_qs = all_qs.filter(timestamp__date=today)
    _agg = all_qs.aggregate(
        total=Count('id'),
        unique=Count('member', distinct=True),
    )
    today_count   = today_qs.count()
    today_revenue = today_qs.aggregate(r=Sum('cost'))['r'] or 0
    cutoff = timezone.now() - timezone.timedelta(minutes=30)
    has_recent = today_qs.filter(timestamp__gte=cutoff).exists()
    return render(request, 'users/partials/partner_today_stats.html', {
        'today_count':   today_count,
        'today_revenue': today_revenue,
        'unique_members': _agg['unique'] or 0,
        'total_visits':  _agg['total'] or 0,
        'has_recent':    has_recent,
    })


@partner_required
def partner_visit_history(request):
    """7b: HTMX-partial для фильтрованной истории визитов."""
    partner = request.user.partner_profile
    now = timezone.now()
    period = request.GET.get('period', 'all')
    status_f = request.GET.get('status_f', '')

    qs = Visit.objects.filter(partner=partner).select_related('member').order_by('-timestamp')

    if period == 'today':
        qs = qs.filter(timestamp__date=timezone.localdate())
    elif period == 'week':
        week_start = timezone.localdate() - timezone.timedelta(days=timezone.localdate().weekday())
        qs = qs.filter(timestamp__date__gte=week_start)
    elif period == 'month':
        qs = qs.filter(timestamp__year=now.year, timestamp__month=now.month)

    if status_f == 'verified':
        qs = qs.filter(pin_verified=True)
    elif status_f == 'cancelled':
        qs = qs.filter(status='CANCELLED')

    page_obj = Paginator(qs, 15).get_page(request.GET.get('page'))
    edit_window_cutoff = now - timezone.timedelta(seconds=EDIT_WINDOW)
    periods = [
        ('all', _('All')),
        ('today', _('Today')),
        ('week', _('This week')),
        ('month', _('This month')),
    ]
    return render(request, 'users/partials/partner_visit_history.html', {
        'visits': page_obj,
        'edit_window_cutoff': edit_window_cutoff,
        'period': period,
        'status_f': status_f,
        'periods': periods,
    })


@partner_required
def partner_visits_csv(request):
    """7e: Экспорт истории визитов в CSV."""
    import csv
    from django.http import StreamingHttpResponse

    partner = request.user.partner_profile
    qs = (Visit.objects
          .filter(partner=partner)
          .select_related('member')
          .order_by('-timestamp'))

    class Echo:
        def write(self, value): return value

    def generate():
        writer = csv.writer(Echo())
        yield writer.writerow(['Date', 'Member', 'Username', 'Service', 'Cost CHF', 'PIN Verified', 'Status'])
        for v in qs.iterator():
            yield writer.writerow([
                v.timestamp.strftime('%Y-%m-%d %H:%M'),
                v.member.get_full_name() or v.member.username,
                v.member.username,
                v.get_service_type_display(),
                float(v.cost) if v.cost else '',
                'Yes' if v.pin_verified else 'No',
                v.status,
            ])

    fname = f"visits_{partner.company_name.replace(' ', '_')}_{timezone.localdate()}.csv"
    resp = StreamingHttpResponse(generate(), content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="{fname}"'
    return resp


@partner_required
@require_http_methods(['GET', 'POST'])
def partner_profile_edit(request):
    partner = request.user.partner_profile
    if request.method == 'POST':
        form = PartnerProfileForm(request.POST, instance=partner)
        if form.is_valid():
            form.save()
            messages.success(request, _('✅ Partner profile updated successfully.'))
            return redirect('users:partner_dashboard')
    else:
        form = PartnerProfileForm(instance=partner)
    return render(request, 'users/partner_profile_edit.html', {'form': form, 'partner': partner})
