"""Partner + user calendar views and MeetingForm."""
import calendar as _cal_mod
import json
import logging
from datetime import date as _date_cls

from django import forms as _dj_forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from ..constants import EDIT_WINDOW
from ..models import Meeting, Partner, User
from ..services.calendar_service import (
    build_month_grid, get_jump_options, mark_selected, serialize_day_meetings,
)
from .utils import partner_required

logger = logging.getLogger(__name__)


class MeetingForm(_dj_forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ['member', 'title', 'date', 'start_time', 'end_time',
                  'address', 'notes', 'notify_member', 'is_recurring', 'series_label']
        widgets = {
            'date':       _dj_forms.DateInput(attrs={'type': 'date', 'class': 'dash-search-input'}),
            'start_time': _dj_forms.TimeInput(attrs={'type': 'time', 'class': 'dash-search-input'}),
            'end_time':   _dj_forms.TimeInput(attrs={'type': 'time', 'class': 'dash-search-input'}),
            'title':      _dj_forms.TextInput(attrs={'class': 'dash-search-input', 'placeholder': _('E.g. Personal training, Consultation...')}),
            'address':    _dj_forms.TextInput(attrs={'class': 'dash-search-input', 'placeholder': _('Street, city...')}),
            'notes':      _dj_forms.Textarea(attrs={'class': 'dash-search-input', 'rows': 3, 'placeholder': _('Additional details for the member')}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].required       = False
        self.fields['start_time'].required = False
        self.fields['end_time'].required   = False


def _notify_meeting_created(meeting, partner) -> None:
    if not meeting.notify_member:
        return
    from notifications.models import Notification as _Notif
    _date_txt = meeting.date.strftime('%d %b %Y') if meeting.date else _('today')
    _time_txt = (
        f"{meeting.start_time.strftime('%H:%M')} — {meeting.end_time.strftime('%H:%M')}"
        if meeting.start_time and meeting.end_time else _('time not specified')
    )
    _Notif.objects.create(
        recipient=meeting.member, notification_type='system',
        title=f'📅 {partner.company_name}: {meeting.title}',
        message=_(
            'Partner %(company)s has scheduled a meeting with you.\n'
            '"%(title)s"\nDate: %(date)s\nTime: %(time)s\n%(addr)s%(series)s'
        ) % {
            'company': partner.company_name, 'title': meeting.title,
            'date': _date_txt, 'time': _time_txt,
            'addr':   f'Address: {meeting.address}\n' if meeting.address else '',
            'series': f'Series: {meeting.series_label}\n' if meeting.series_label else '',
        },
        link='/auth/my-calendar/',
    )
    if getattr(meeting.member, 'telegram_chat_id', None):
        import threading as _thr
        _mid = meeting.pk
        def _tg():
            try:
                from users.telegram.notify import send_message as _sm
                from users.models import Meeting as _M
                m = _M.objects.select_related('partner', 'member').get(pk=_mid)
                _d = m.date.strftime('%d %b %Y') if m.date else 'today'
                _t = (f"{m.start_time.strftime('%H:%M')} — {m.end_time.strftime('%H:%M')}"
                      if m.start_time and m.end_time else 'time TBD')
                _sm(m.member.telegram_chat_id, (
                    f"📅 <b>Meeting scheduled</b>\n\n<b>{m.partner.company_name}</b>: {m.title}\n"
                    f"📆 {_d} | 🕐 {_t}\n"
                    + (f"📍 {m.address}\n" if m.address else '')
                    + (f"🔄 Series: {m.series_label}\n" if m.series_label else '')
                ), parse_mode='HTML')
            except Exception as _e:
                logger.error("meeting TG notify failed: %s", _e)
        _thr.Thread(target=_tg, daemon=True).start()
    meeting.notification_sent = True
    meeting.save(update_fields=['notification_sent'])


@partner_required
@require_http_methods(["GET", "POST"])
def partner_calendar(request):
    from ..models import ClientNote
    partner = request.user.partner_profile
    today   = _date_cls.today()

    month_str = request.GET.get('jump') or request.GET.get('month', '')
    try:
        parts = month_str.split('-')
        cal_year, cal_month = int(parts[0]), int(parts[1])
    except (ValueError, IndexError, AttributeError):
        cal_year, cal_month = today.year, today.month
    cal_year  = max(2020, min(cal_year, today.year + 5))
    cal_month = max(1,    min(cal_month, 12))

    try:
        selected_day = _date_cls.fromisoformat(request.GET.get('day', ''))
    except ValueError:
        selected_day = today

    first_day = _date_cls(cal_year, cal_month, 1)
    last_day  = _date_cls(cal_year, cal_month, _cal_mod.monthrange(cal_year, cal_month)[1])
    prev_m = cal_month - 1 or 12;    prev_y = cal_year - (1 if cal_month == 1 else 0)
    next_m = (cal_month % 12) + 1;   next_y = cal_year + (1 if cal_month == 12 else 0)

    month_meetings_qs = Meeting.objects.filter(
        partner=partner, date__range=(first_day, last_day),
    ).select_related('member').order_by('date', 'start_time')
    meetings_by_date: dict = {}
    for m in month_meetings_qs:
        if m.date:
            meetings_by_date.setdefault(m.date, []).append(m)

    cal_grid = build_month_grid(cal_year, cal_month, meetings_by_date)
    mark_selected(cal_grid, selected_day)

    day_meetings = Meeting.objects.filter(partner=partner, date=selected_day).select_related('member').order_by('start_time')
    upcoming     = Meeting.objects.filter(partner=partner, date__gte=today, status__in=['scheduled', 'confirmed']).select_related('member').order_by('date', 'start_time')[:20]

    if request.method == 'POST' and request.POST.get('action') == 'add_note':
        note_mid  = request.POST.get('note_member_id')
        note_text = request.POST.get('note_text', '').strip()
        if note_mid and note_text:
            ClientNote.objects.create(partner=partner, member_id=note_mid, note=note_text)
            messages.success(request, _('Note saved.'))
        return redirect(request.get_full_path())

    all_members = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')
    form = MeetingForm(request.POST or None)
    form.fields['member'].queryset = all_members

    if request.method == 'POST' and form.is_valid():
        meeting = form.save(commit=False)
        meeting.partner = partner; meeting.date = meeting.date or today
        meeting.save()
        _notify_meeting_created(meeting, partner)
        messages.success(request, _('Meeting scheduled successfully!'))
        _mstr = f'{meeting.date.year}-{meeting.date.month:02d}'
        return redirect(f"{request.path}?month={_mstr}&day={meeting.date.isoformat()}")
    elif request.method != 'POST':
        form = MeetingForm(); form.fields['member'].queryset = all_members

    day_member_ids = list(day_meetings.values_list('member_id', flat=True))
    client_notes_by_member: dict = {}
    if day_member_ids:
        for note in ClientNote.objects.filter(partner=partner, member_id__in=day_member_ids).select_related('member'):
            client_notes_by_member.setdefault(note.member_id, []).append(note)

    _meet_stats = Meeting.objects.filter(partner=partner, status__in=['scheduled', 'confirmed']).aggregate(
        total=Count('id'), this_month=Count('id', filter=Q(date__year=today.year, date__month=today.month)),
    )

    return render(request, 'users/partner_calendar.html', {
        'partner': partner, 'form': form,
        'cal_grid': cal_grid, 'cal_year': cal_year, 'cal_month': cal_month,
        'cal_month_name': first_day.strftime('%B %Y'),
        'prev_month_str': f'{prev_y}-{prev_m:02d}', 'next_month_str': f'{next_y}-{next_m:02d}',
        'jump_options': get_jump_options(cal_year, cal_month),
        'meetings_by_date': meetings_by_date, 'day_meetings': day_meetings,
        'day_meetings_json': json.dumps(serialize_day_meetings(day_meetings)),
        'selected_day': selected_day, 'today': today, 'upcoming': upcoming,
        'hour_slots': list(range(8, 23)),
        'prefill_date': request.GET.get('prefill_date', selected_day.strftime('%Y-%m-%d')),
        'prefill_time': request.GET.get('prefill_time', ''),
        'client_notes_by_member': client_notes_by_member,
        'total_meetings': _meet_stats['total'] or 0, 'month_meetings': _meet_stats['this_month'] or 0,
        'all_members': all_members,
    })


@partner_required
@require_POST
def delete_meeting(request, meeting_id):
    partner = request.user.partner_profile
    meeting = get_object_or_404(Meeting, pk=meeting_id, partner=partner)
    member  = meeting.member
    meeting.status = 'cancelled'
    meeting.save(update_fields=['status'])
    from notifications.models import Notification as _Notif
    _Notif.objects.create(
        recipient=member, notification_type='system',
        title=_('Meeting cancelled'),
        message=_('Meeting "%(title)s" at %(company)s on %(date)s has been cancelled.') % {
            'title': meeting.title, 'company': partner.company_name,
            'date':  meeting.date.strftime('%d %b %Y'),
        },
        link='/auth/my-calendar/',
    )
    messages.success(request, _('Meeting cancelled.'))
    return redirect('users:partner_calendar')


@login_required
def user_calendar(request):
    today = _date_cls.today()
    upcoming = Meeting.objects.filter(member=request.user, date__gte=today, status__in=['scheduled', 'confirmed']).select_related('partner').order_by('date', 'start_time')
    past     = Meeting.objects.filter(member=request.user, date__lt=today).select_related('partner').order_by('-date', '-start_time')[:20]
    return render(request, 'users/user_calendar.html', {'upcoming': upcoming, 'past': past, 'today': today})


@login_required
def user_calendar_ics(request):
    """10a: Экспорт всех предстоящих встреч в формате RFC 5545 iCalendar (.ics)."""
    from django.http import HttpResponse
    import uuid as _uuid

    today = _date_cls.today()
    meetings = (Meeting.objects
                .filter(member=request.user, date__gte=today, status__in=['scheduled', 'confirmed'])
                .select_related('partner')
                .order_by('date', 'start_time'))

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//IESA Sport//Calendar//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:IESA Sport Meetings',
    ]

    for m in meetings:
        dt_date = m.date.strftime('%Y%m%d')
        uid = str(_uuid.uuid4())
        summary = m.title or _('Meeting')
        description = f'Partner: {m.partner.company_name}' if hasattr(m, 'partner') and m.partner else ''
        if m.start_time:
            dtstart = f'DTSTART:{dt_date}T{m.start_time.strftime("%H%M%S")}'
            dtend   = f'DTEND:{dt_date}T{m.end_time.strftime("%H%M%S")}' if m.end_time else dtstart
        else:
            dtstart = f'DTSTART;VALUE=DATE:{dt_date}'
            dtend   = f'DTEND;VALUE=DATE:{dt_date}'
        lines += [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            dtstart, dtend,
            f'SUMMARY:{summary}',
            f'DESCRIPTION:{description}',
            'END:VEVENT',
        ]

    lines.append('END:VCALENDAR')
    content = '\r\n'.join(lines) + '\r\n'
    resp = HttpResponse(content, content_type='text/calendar; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="iesa-meetings.ics"'
    return resp
