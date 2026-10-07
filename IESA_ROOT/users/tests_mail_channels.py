"""Which mail channel is used first, and that a broken one does not lose the message."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from users import email_service


@patch('users.cleverreach_client.send_cleverreach_email')
@patch('users.cleverreach_client.is_configured')
@patch('users.email_service._smtp_send')
class MailChannelOrderTests(SimpleTestCase):
    args = ('Subject', 'plain', '<p>html</p>', ['a@example.com'])

    @override_settings(EMAIL_PREFER_SMTP=True)
    def test_smtp_first_and_cleverreach_untouched_when_smtp_works(self, smtp, cr_configured, cr_send):
        smtp.return_value = 1
        cr_configured.return_value = True
        self.assertEqual(email_service._send(*self.args), 1)
        smtp.assert_called_once()
        cr_send.assert_not_called()

    @override_settings(EMAIL_PREFER_SMTP=True)
    def test_cleverreach_is_the_backup_when_smtp_fails(self, smtp, cr_configured, cr_send):
        smtp.return_value = 0
        cr_configured.return_value = True
        cr_send.return_value = True
        self.assertEqual(email_service._send(*self.args), 1)
        cr_send.assert_called_once()

    @override_settings(EMAIL_PREFER_SMTP=True)
    def test_nothing_delivered_is_reported_as_zero(self, smtp, cr_configured, cr_send):
        smtp.return_value = 0
        cr_configured.return_value = False
        self.assertEqual(email_service._send(*self.args), 0)

    @override_settings(EMAIL_PREFER_SMTP=False)
    def test_default_order_is_unchanged_cleverreach_then_smtp(self, smtp, cr_configured, cr_send):
        cr_configured.return_value = True
        cr_send.return_value = False
        smtp.return_value = 1
        self.assertEqual(email_service._send(*self.args), 1)
        cr_send.assert_called_once()
        smtp.assert_called_once()
