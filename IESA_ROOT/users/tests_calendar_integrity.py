"""Calendar security, cancellation, serialization and exports."""
import csv
import io
import json
import re
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import caches
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from notifications.models import Notification
from users.models import ClientNote, Meeting, Partner, User, Visit
from users.services.calendar_export import render_meetings_ics
from users.views.calendar import MeetingForm, _notify_meeting_created


class CalendarIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username='calendar-operator', is_partner=True)
        cls.partner = Partner.objects.create(user=cls.operator, company_name='Gym <north>')
        cls.member = User.objects.create_user(username='calendar-member')

    def setUp(self):
        caches['ratelimit'].clear()
        self.client.force_login(self.operator)
        self.day = timezone.localdate() + timedelta(days=1)
        self.meeting = Meeting.objects.create(
            partner=self.partner, member=self.member, date=self.day,
            title='Training', start_time=time(12), end_time=time(13),
        )

    def test_script_closing_text_roundtrips_through_non_executable_json(self):
        attack = '</script><script>alert("calendar")</script>'
        self.meeting.title = attack
        self.meeting.save(update_fields=['title'])
        response = self.client.get(reverse('users:partner_calendar'), {'day': self.day.isoformat()})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(attack, html)
        payload = re.search(r'<script id="day-meetings-data" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(payload)
        self.assertEqual(json.loads(payload.group(1))[0]['title'], attack)

    def test_cancellation_requires_post_and_changes_only_own_meeting_once(self):
        url = reverse('users:delete_meeting', args=[self.meeting.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'cancelled')
        self.assertEqual(Notification.objects.filter(recipient=self.member, title='Meeting cancelled').count(), 1)

    def test_cancellation_of_undated_legacy_meeting_does_not_raise(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(date=None)
        self.assertEqual(self.client.post(reverse('users:delete_meeting', args=[self.meeting.pk])).status_code, 302)

    def test_other_partner_cannot_cancel_meeting(self):
        other = User.objects.create_user(username='calendar-other', is_partner=True)
        Partner.objects.create(user=other, company_name='Other')
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse('users:delete_meeting', args=[self.meeting.pk])).status_code, 404)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'scheduled')

    def test_completed_meeting_cannot_be_cancelled(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(status='completed')
        self.client.post(reverse('users:delete_meeting', args=[self.meeting.pk]))
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'completed')

    def test_popup_uses_a_csrf_protected_post_form(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        page = client.get(reverse('users:partner_calendar'))
        self.assertContains(page, '<form id="popup-cancel-form" method="post">')
        url = reverse('users:delete_meeting', args=[self.meeting.pk])
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(client.post(url, {'csrfmiddlewaretoken': client.cookies['csrftoken'].value}).status_code, 302)

    def test_invalid_client_note_member_is_rejected_without_500(self):
        for member_id in ('not-an-integer', '999999999', '-1'):
            with self.subTest(member_id=member_id):
                response = self.client.post(reverse('users:partner_calendar'), {
                    'action': 'add_note', 'note_member_id': member_id, 'note_text': 'Private note',
                })
                self.assertEqual(response.status_code, 302)
        self.assertFalse(ClientNote.objects.exists())

    def test_client_note_does_not_accept_inactive_member(self):
        User.objects.filter(pk=self.member.pk).update(is_active=False)
        self.client.post(reverse('users:partner_calendar'), {
            'action': 'add_note', 'note_member_id': self.member.pk, 'note_text': 'Note',
        })
        self.assertFalse(ClientNote.objects.exists())

    def test_client_note_is_owned_by_current_partner(self):
        self.client.post(reverse('users:partner_calendar'), {
            'action': 'add_note', 'note_member_id': self.member.pk, 'note_text': '  Private note  ',
        })
        note = ClientNote.objects.get()
        self.assertEqual((note.partner_id, note.member_id, note.note), (self.partner.pk, self.member.pk, 'Private note'))

    def test_meeting_form_rejects_end_before_start_and_end_without_start(self):
        for start, end in (('12:00', '11:00'), ('12:00', '12:00'), ('', '12:00')):
            with self.subTest(start=start, end=end):
                form = MeetingForm({'member': self.member.pk, 'title': 'Training', 'start_time': start, 'end_time': end})
                self.assertFalse(form.is_valid())

    def test_meeting_form_allows_all_day_or_start_only_meetings(self):
        for start in ('', '12:00'):
            with self.subTest(start=start):
                form = MeetingForm({'member': self.member.pk, 'title': 'Training', 'start_time': start})
                self.assertTrue(form.is_valid(), form.errors)

    def test_meeting_telegram_payload_has_correct_arguments_and_escaped_text(self):
        self.member.telegram_chat_id = 12345
        self.member.save(update_fields=['telegram_chat_id'])
        self.meeting.title = '<a href="https://attacker.example">Click</a>'
        self.meeting.save(update_fields=['title'])
        self.meeting.member = self.member
        with patch('threading.Thread') as thread, patch('users.telegram.notify.send_message', return_value=True) as send:
            _notify_meeting_created(self.meeting, self.partner)
            target = thread.call_args.kwargs['target']
            # The production closure owns its DB connection; this test shares
            # the TestCase connection and must keep that transaction open.
            with patch('users.views.calendar.close_old_connections'):
                target()
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs['chat_id'], 12345)
        self.assertIsInstance(send.call_args.args[0], str)
        self.assertIn('&lt;a href=', send.call_args.args[0])
        self.assertIn('Gym &lt;north&gt;', send.call_args.args[0])

    def test_direct_calendar_route_initializes_flag_only_partner_profile(self):
        flag_only = User.objects.create_user(username='calendar-flag-only', is_partner=True)
        self.client.force_login(flag_only)
        response = self.client.get(reverse('users:partner_calendar'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Partner.objects.filter(user=flag_only).exists())

    def test_ics_endpoint_excludes_other_members_and_cancelled_meetings(self):
        other = User.objects.create_user(username='ics-other')
        Meeting.objects.create(partner=self.partner, member=other, title='Other private meeting', date=self.day)
        Meeting.objects.create(partner=self.partner, member=self.member, title='Cancelled meeting', date=self.day, status='cancelled')
        self.client.force_login(self.member)
        response = self.client.get(reverse('users:user_calendar_ics'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'BEGIN:VEVENT'), 1)
        self.assertNotContains(response, 'Other private meeting')
        self.assertNotContains(response, 'Cancelled meeting')

    def test_ics_uid_and_timestamp_are_stable_between_downloads(self):
        first = render_meetings_ics([self.meeting])
        second = render_meetings_ics([self.meeting])
        self.assertEqual(first, second)
        self.assertIn(f'UID:iesa-meeting-{self.meeting.pk}@iesasport.ch', first)
        self.assertIn('DTSTAMP:', first)
        self.assertEqual(first.count('DTSTART:'), 1)

    def test_ics_text_cannot_inject_properties_and_utf8_lines_are_folded(self):
        self.meeting.title = 'Тренування, раз; два\\три\r\nBEGIN:VEVENT\n' + '☃' * 60
        content = render_meetings_ics([self.meeting])
        self.assertEqual(content.count('\r\nBEGIN:VEVENT\r\n'), 1)
        self.assertIn('\\,', content)
        self.assertIn('\\;', content)
        self.assertIn('\\nBEGIN:VEVENT\\n', content.replace('\r\n ', ''))
        for line in content.split('\r\n'):
            self.assertLessEqual(len(line.encode('utf-8')), 75)

    def test_ics_all_day_end_is_next_day_and_start_only_has_no_fake_end(self):
        self.meeting.start_time = None
        self.meeting.end_time = None
        content = render_meetings_ics([self.meeting])
        self.assertIn(f'DTEND;VALUE=DATE:{self.day + timedelta(days=1):%Y%m%d}', content)
        self.meeting.start_time = time(12)
        content = render_meetings_ics([self.meeting])
        self.assertEqual(content.count('DTSTART:'), 1)
        self.assertNotIn('DTEND', content)

    def test_ics_uses_zurich_utc_offset_for_summer_and_winter(self):
        for day, utc_hour in ((date(2027, 1, 15), 11), (date(2027, 7, 15), 10)):
            with self.subTest(day=day):
                self.meeting.date = day
                content = render_meetings_ics([self.meeting])
                self.assertIn(f'DTSTART:{day:%Y%m%d}T{utc_hour:02d}0000Z', content)

    def test_csv_neutralizes_formula_and_preserves_zero_cost(self):
        self.member.first_name = '=HYPERLINK("https://attacker.example")'
        self.member.save(update_fields=['first_name'])
        Visit.objects.create(member=self.member, partner=self.partner, cost=Decimal('0.00'))
        response = self.client.get(reverse('users:partner_visits_csv'))
        rows = list(csv.reader(io.StringIO(b''.join(response.streaming_content).decode())))
        self.assertTrue(rows[1][1].startswith("'="))
        self.assertEqual(rows[1][4], '0.00')

    def test_csv_filename_cannot_inject_response_headers(self):
        self.partner.company_name = 'Gym"\r\nX-Injected: bad'
        self.partner.save(update_fields=['company_name'])
        response = self.client.get(reverse('users:partner_visits_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('\r', response['Content-Disposition'])
        self.assertNotIn('\n', response['Content-Disposition'])
        response.close()
