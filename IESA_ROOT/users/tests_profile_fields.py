"""Inline saves must validate the same input as the full profile form."""
from urllib.parse import urlencode
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from users.forms import UserProfileEditForm
from users.models import User


class ProfileFieldTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='inline-member', email='inline@example.com', first_name='Original')
        self.client.force_login(self.user)
        self.url = reverse('users:profile_field_save')

    def test_invalid_contact_values_are_rejected_and_not_saved(self):
        for field, value in (
            ('github_url', 'javascript:alert(1)'),
            ('github_url', 'https://attacker.example/name'),
            ('website_url', 'javascript:alert(1)'),
            ('phone_number', '<script>alert(1)</script>'),
            ('telegram_url', 'https://attacker.example/name'),
            ('discord_url', '<b>handle</b>'),
            ('first_name', 'A' * 151),
        ):
            with self.subTest(field=field, value=value):
                self.user.refresh_from_db()
                previous = getattr(self.user, field)
                response = self.client.post(self.url, {'field': field, 'value': value})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['ok'])
                self.user.refresh_from_db()
                self.assertEqual(getattr(self.user, field), previous)

    def test_valid_handles_and_urls_are_accepted(self):
        for field, value in (
            ('github_url', 'https://github.com/member'),
            ('website_url', 'https://example.com/about'),
            ('telegram_url', '@example_member'),
            ('telegram_url', 't.me/example_member'),
            ('discord_url', 'member_name#1234'),
            ('pseudonym', 'New nickname'),
        ):
            with self.subTest(field=field, value=value):
                response = self.client.post(self.url, {'field': field, 'value': value})
                self.assertEqual(response.status_code, 200, response.content)
                self.user.refresh_from_db()
                self.assertEqual(getattr(self.user, field), value)

    def test_phone_is_normalized_without_qr_generation(self):
        with patch('users.signals.generate_qr_code_for_user') as generate:
            response = self.client.post(self.url, {'field': 'phone_number', 'value': '+41  79  123 45 67'})
        generate.assert_not_called()
        self.assertEqual(response.json()['saved_value'], '+41 79 123 45 67')

    def test_urlencoded_patch_saves_field(self):
        response = self.client.patch(self.url, urlencode({'field': 'first_name', 'value': 'Patched'}), content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Patched')

    def test_partial_form_does_not_require_email_or_other_fields(self):
        response = self.client.post(self.url, {'field': 'first_name', 'value': 'New'})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.email), ('New', 'inline@example.com'))

    def test_cannot_write_role_password_or_email(self):
        for field in ('is_staff', 'is_partner', 'password', 'email_verified_at', 'email', '__class__'):
            with self.subTest(field=field):
                self.assertEqual(self.client.post(self.url, {'field': field, 'value': 'true'}).status_code, 400)

    def test_valid_social_handles_also_work_in_full_profile_form(self):
        form = UserProfileEditForm({
            'email': self.user.email, 'first_name': 'Member',
            'telegram_url': '@example_member', 'discord_url': 'member_name#1234',
        }, instance=self.user)
        self.assertTrue(form.is_valid(), form.errors)
