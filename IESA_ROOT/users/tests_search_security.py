"""Unhighlighted search results and invited usernames are untrusted text."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.forms_verification import InviteRegisterForm
from users.models import InviteToken, User


class SearchEscapingTests(TestCase):
    def test_role_only_search_escapes_legacy_username_and_email(self):
        attack = '<img src=x onerror=alert(1)>'
        User.objects.create_user(username=attack, email=attack, is_verified=True)
        response = self.client.get(reverse('users:users_search'), {'role': 'verified'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, attack)
        self.assertContains(response, '&lt;img src=x onerror=alert(1)&gt;')

    def test_invite_form_rejects_html_or_path_components_in_username(self):
        staff = User.objects.create_user(username='username-admin', is_staff=True)
        invite = InviteToken.objects.create(created_by=staff, expires_at=timezone.now() + timedelta(days=1))
        for username in ('<b>member</b>', 'path/name', 'name with spaces'):
            with self.subTest(username=username):
                form = InviteRegisterForm({
                    'username': username, 'email': 'valid@example.com',
                    'company_name': 'Valid company', 'business_type': 'gym',
                    'password1': 'Unique-valid-password-597', 'password2': 'Unique-valid-password-597',
                }, invite=invite)
                self.assertFalse(form.is_valid())
                self.assertIn('username', form.errors)
