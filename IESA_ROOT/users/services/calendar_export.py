"""iCalendar serialization (RFC 5545), independent of HTTP views."""
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.utils import timezone


def _text(value):
    return (str(value).replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n')
            .replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,'))


def _fold(line):
    """Fold at 75 UTF-8 octets without splitting a multibyte character."""
    parts, current, size = [], '', 0
    for char in line:
        width = len(char.encode('utf-8'))
        if size + width > 75:
            parts.append(current)
            current, size = ' ', 1
        current += char
        size += width
    parts.append(current)
    return '\r\n'.join(parts)


def _utc(value):
    return value.astimezone(datetime_timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def render_meetings_ics(meetings):
    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//IESA Sport//Calendar//EN',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:IESA Sport Meetings',
    ]
    for meeting in meetings:
        if meeting.date is None:
            continue
        lines += [
            'BEGIN:VEVENT', f'UID:iesa-meeting-{meeting.pk}@iesasport.ch',
            f'DTSTAMP:{_utc(meeting.updated_at)}',
        ]
        if meeting.start_time:
            start = timezone.make_aware(datetime.combine(meeting.date, meeting.start_time), timezone.get_default_timezone())
            lines.append(f'DTSTART:{_utc(start)}')
            if meeting.end_time and meeting.end_time > meeting.start_time:
                end = timezone.make_aware(datetime.combine(meeting.date, meeting.end_time), timezone.get_default_timezone())
                lines.append(f'DTEND:{_utc(end)}')
        else:
            lines += [
                f'DTSTART;VALUE=DATE:{meeting.date:%Y%m%d}',
                f'DTEND;VALUE=DATE:{meeting.date + timedelta(days=1):%Y%m%d}',
            ]
        lines += [
            f'SUMMARY:{_text(meeting.title)}',
            f'DESCRIPTION:{_text("Partner: " + meeting.partner.company_name)}',
            f'LOCATION:{_text(meeting.address)}', 'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'
