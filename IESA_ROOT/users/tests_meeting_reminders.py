"""Reminder delivery uses the actual Telegram client and skips repeat sends."""
from datetime import datetime, time, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from notifications.models import Notification
from users.management.commands.send_meeting_reminders import Command
from users.models import Meeting, Partner, User


class MeetingReminderTests(TestCase):
    def test_telegram_uses_public_client_with_correct_argument_order(self):
        user = User.objects.create_user(username='reminder-member', telegram_chat_id=12345)
        with patch('users.telegram.send_message', return_value=True) as send:
            Command()._send_tg(user, 'Reminder <name>')
        send.assert_called_once_with('Reminder &lt;name&gt;', chat_id=12345)

    def test_repeated_scheduler_runs_do_not_resend_telegram(self):
        now = timezone.make_aware(datetime.combine(timezone.localdate(), time(12)))
        operator = User.objects.create_user(username='reminder-operator', is_partner=True)
        partner = Partner.objects.create(user=operator, company_name='Gym')
        member = User.objects.create_user(username='reminder-recipient')
        Meeting.objects.create(partner=partner, member=member, date=(now + timedelta(days=1)).date(), title='Training', start_time=time(12))
        with patch('users.management.commands.send_meeting_reminders.timezone.localtime', return_value=now):
            with patch.object(Command, '_send_tg') as send:
                call_command('send_meeting_reminders', stdout=StringIO())
                call_command('send_meeting_reminders', stdout=StringIO())
        self.assertEqual(send.call_count, 2)  # One member and one partner, once each.
        self.assertEqual(Notification.objects.filter(notification_type='event_reminder').count(), 2)

    def test_dry_run_creates_no_notifications(self):
        with patch.object(Command, '_send_tg') as send:
            call_command('send_meeting_reminders', dry_run=True, stdout=StringIO())
        send.assert_not_called()
        self.assertFalse(Notification.objects.exists())
