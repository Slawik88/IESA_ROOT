"""One-time Telegram link codes cannot overwrite or reuse another code."""
from unittest.mock import patch

from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse

from users.models import User
from users.telegram.link import consume_link_code, generate_link_code, verify_telegram_auth


class TelegramLinkCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        caches['ratelimit'].clear()
        self.addCleanup(cache.clear)
        self.addCleanup(caches['ratelimit'].clear)

    def test_collision_does_not_overwrite_first_chat(self):
        with patch('users.telegram.link.secrets.randbelow', side_effect=[123456, 123456, 234567]):
            first = generate_link_code(100)
            second = generate_link_code(200)
        self.assertEqual((first, second), ('123456', '234567'))
        self.assertEqual(consume_link_code(first), '100')
        self.assertEqual(consume_link_code(second), '200')

    def test_code_can_only_be_consumed_once_and_is_not_immediately_reallocated(self):
        with patch('users.telegram.link.secrets.randbelow', return_value=123456):
            code = generate_link_code(100)
        self.assertEqual(consume_link_code(code), '100')
        self.assertIsNone(consume_link_code(code))
        with patch('users.telegram.link.secrets.randbelow', side_effect=[123456, 345678]):
            self.assertEqual(generate_link_code(200), '345678')

    def test_malformed_hash_is_rejected_without_server_error(self):
        with patch('users.telegram.link.token', return_value='test-bot-token'):
            for value in ('☃' * 64, 'g' * 64, '', None):
                with self.subTest(value=value):
                    self.assertFalse(verify_telegram_auth({'hash': value}))

    def test_link_code_guessing_is_rate_limited(self):
        user = User.objects.create_user(username='code-guesser')
        self.client.force_login(user)
        url = reverse('users:connect_telegram_code')
        for _attempt in range(10):
            self.assertEqual(self.client.post(url, {'code': '000000'}).status_code, 200)
        self.assertEqual(self.client.post(url, {'code': '000000'}).status_code, 403)
