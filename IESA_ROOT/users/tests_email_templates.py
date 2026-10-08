from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from users import email_service


class VisitEmailTemplateTests(TestCase):
    """The visit e-mails are rendered from users/email/*.html on the shared dark layout (no more f-string HTML)."""

    def setUp(self):
        self.member = SimpleNamespace(
            email='anna@example.test', username='anna', get_full_name=lambda: 'Anna Keller',
        )
        self.partner = SimpleNamespace(company_name='Alpine <Gym> & Spa')
        self.visit = SimpleNamespace(
            member=self.member, partner=self.partner, cost='45.00', service_description='Day pass <b>x</b>',
            timestamp=datetime(2026, 10, 8, 18, 30), get_service_type_display=lambda: 'Day pass',
        )
        self.audit = SimpleNamespace(previous_service_type='Single entry', previous_cost='30.00', reason='Typo <i>fix</i>')

    def _sent(self, func, *args):
        with mock.patch.object(email_service, '_send') as send:
            func(*args)
        self.assertEqual(send.call_count, 1)
        subject, plain, html, recipients = send.call_args.args
        self.assertEqual(recipients, ['anna@example.test'])
        return subject, plain, html

    def test_confirmed_escapes_user_text_and_uses_the_layout(self):
        subject, plain, html = self._sent(email_service.send_visit_confirmed, self.visit)
        self.assertIn('Alpine &lt;Gym&gt; &amp; Spa', html)
        self.assertNotIn('<Gym>', html)
        self.assertIn('Day pass &lt;b&gt;x&lt;/b&gt;', html)
        self.assertIn('45.00 CHF', html)
        self.assertIn('role="presentation"', html)
        self.assertIn('IESA', html)
        self.assertIn('Alpine <Gym> & Spa', subject)   # subject stays plain text
        self.assertIn('Cost: 45.00 CHF', plain)

    def test_edited_shows_old_and_new_values(self):
        _, plain, html = self._sent(email_service.send_visit_edited, self.visit, self.audit)
        self.assertIn('Single entry', html)
        self.assertIn('30.00 CHF', html)
        self.assertIn('Typo &lt;i&gt;fix&lt;/i&gt;', html)
        self.assertIn('Reason: Typo <i>fix</i>', plain)

    def test_cancelled_mentions_the_reason(self):
        _, plain, html = self._sent(email_service.send_visit_cancelled, self.visit, self.audit)
        self.assertIn('Typo &lt;i&gt;fix&lt;/i&gt;', html)
        self.assertIn('cancelled', plain)

    def test_member_without_address_gets_nothing(self):
        self.member.email = ''
        with mock.patch.object(email_service, '_send') as send:
            email_service.send_visit_confirmed(self.visit)
        send.assert_not_called()
