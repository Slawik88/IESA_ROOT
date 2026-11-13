"""Регрессии: уведомления о визитах и напоминания о встречах в Telegram реально отправляются.

Раньше `chat_id, ..., _ = ctx` затирал gettext `_` (TypeError «str is not callable» при правке/отмене
визита), а напоминания импортировали несуществующий `users.telegram_bot` — ошибка глоталась молча.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from users.management.commands.send_meeting_reminders import Command
from users.telegram import notify


def _visit():
    member = SimpleNamespace(telegram_chat_id=42, username="anna", get_full_name=lambda: "Anna B")
    return SimpleNamespace(
        member=member,
        partner=SimpleNamespace(company_name="Gym"),
        timestamp=datetime(2026, 11, 4, 10, 30),
        cost=25,
        get_service_type_display=lambda: "Fitness",
    )


class VisitNotifyTests(SimpleTestCase):
    def test_edited_and_cancelled_send(self):
        audit = SimpleNamespace(previous_cost=30, previous_service_type="Spa", reason="typo")
        with mock.patch.object(notify, "send_message", return_value=True) as send:
            self.assertTrue(notify.notify_visit_edited(_visit(), audit))
            self.assertTrue(notify.notify_visit_cancelled(_visit(), audit))
        self.assertEqual(send.call_count, 2)
        for call in send.call_args_list:
            self.assertEqual(call.kwargs["chat_id"], 42)
            self.assertIn("Gym", call.args[0])

    def test_user_text_is_escaped_for_html_mode(self):
        visit = _visit()
        visit.partner.company_name = "Gym <b>&</b>"
        audit = SimpleNamespace(previous_cost=None, previous_service_type="Spa", reason="<a href='x'>x</a>")
        with mock.patch.object(notify, "send_message", return_value=True) as send:
            notify.notify_visit_cancelled(visit, audit)
        text = send.call_args.args[0]
        self.assertIn("Gym &lt;b&gt;&amp;&lt;/b&gt;", text)
        self.assertNotIn("<a href", text)
        self.assertIn("<b>", text)   # our own markup stays


class MeetingReminderTelegramTests(SimpleTestCase):
    def test_reminder_reaches_telegram_client(self):
        user = SimpleNamespace(pk=1, telegram_chat_id=77)
        with mock.patch("users.telegram.send_message", return_value=True) as send:
            Command()._send_tg(user, 'hello "<Gym>"')
        send.assert_called_once_with('hello "&lt;Gym&gt;"', chat_id=77)
