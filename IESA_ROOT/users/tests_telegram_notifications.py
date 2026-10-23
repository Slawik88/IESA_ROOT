"""Notification formatting and async adaptation without Telegram requests."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from django.test import TestCase

from users.models import Partner, User, Visit, VisitAudit
from users.telegram.notify import (
    notify_membership_activated, notify_visit_cancelled, notify_visit_confirmed,
    notify_visit_confirmed_async, notify_visit_edited,
)


class TelegramNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(username='telegram-member', first_name='<member>', telegram_chat_id=12345)
        cls.operator = User.objects.create_user(username='telegram-operator', is_partner=True)
        cls.partner = Partner.objects.create(user=cls.operator, company_name='<company>')
        cls.visit = Visit.objects.create(member=cls.member, partner=cls.partner, cost=Decimal('0.00'), service_description='<description>')
        cls.audit = VisitAudit.objects.create(
            visit=cls.visit, action='EDIT', previous_cost=Decimal('0.00'),
            previous_service_type='<previous>', reason='<reason>', changed_by=cls.operator,
        )

    def test_sync_messages_escape_user_html_and_preserve_zero_cost(self):
        for notify, args in (
            (notify_visit_confirmed, (self.visit,)),
            (notify_visit_edited, (self.visit, self.audit)),
            (notify_visit_cancelled, (self.visit, self.audit)),
        ):
            with self.subTest(notify=notify.__name__):
                with patch('users.telegram.notify.send_message', return_value=True) as send:
                    self.assertTrue(notify(*args))
                text = send.call_args.args[0]
                self.assertIn('&lt;member&gt;', text)
                self.assertIn('&lt;company&gt;', text)
                self.assertNotIn('<reason>', text)
                self.assertIn('0.00 CHF', text)
                self.assertEqual(send.call_args.kwargs['chat_id'], 12345)

    async def test_async_notification_resolves_lazy_relations_in_sync_context(self):
        # Reload without select_related: both FK descriptors will hit the DB.
        from asgiref.sync import sync_to_async
        visit = await sync_to_async(Visit.objects.get)(pk=self.visit.pk)
        with patch('users.telegram.notify.send_message_async', new_callable=AsyncMock, return_value=True) as send:
            self.assertTrue(await notify_visit_confirmed_async(visit))
        send.assert_awaited_once()
        self.assertIn('&lt;description&gt;', send.call_args.args[0])
        self.assertIn('0.00 CHF', send.call_args.args[0])

    async def test_async_notification_without_chat_returns_false_without_network(self):
        self.visit.member.telegram_chat_id = None
        with patch('users.telegram.notify.send_message_async', new_callable=AsyncMock) as send:
            self.assertFalse(await notify_visit_confirmed_async(self.visit))
        send.assert_not_awaited()

    def test_membership_message_escapes_member_name(self):
        with patch('users.telegram.notify.send_message', return_value=True) as send:
            notify_membership_activated(self.member)
        self.assertIn('&lt;member&gt;', send.call_args.args[0])
