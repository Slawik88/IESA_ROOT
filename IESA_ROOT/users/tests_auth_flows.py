"""Registration, login and password-reset flows — the mobile-signup regressions.

Phone password managers generate passwords without uppercase/special characters
(Chrome) or with hyphens only (Safari); phone keyboards capitalise the username.
These tests pin the behaviour that lets those people in.
"""
import re
from unittest.mock import patch

from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from users.forms import CustomUserCreationForm
from users.models import User
from users.tests_support import human_fields


def _signup_data(**overrides):
    data = {
        'username': 'phone-user',
        'email': 'phone.user@example.com',
        'password1': 'Hyfwiz-5jyqge-tuvzed',
        'password2': 'Hyfwiz-5jyqge-tuvzed',
        'membership_consent': True,
        **human_fields(),
    }
    data.update(overrides)
    return data


class PasswordPolicyTests(TestCase):
    def test_phone_generated_passwords_are_accepted(self):
        for password in (
            'Hyfwiz-5jyqge-tuvzed',      # Safari strong password (hyphens only)
            'kxpmqtzrwcvbnhga',          # lowercase only, long
            'Zq8nVb3LkP9xWm4T',          # Chrome style: letters + digits, no symbol
        ):
            with self.subTest(password=password):
                validate_password(password)

    def test_genuinely_weak_passwords_are_still_rejected(self):
        for password in ('short1', 'password123', '1234567890', 'qwertyuiop'):
            with self.subTest(password=password):
                with self.assertRaises(ValidationError):
                    validate_password(password)

    def test_form_accepts_safari_style_password(self):
        form = CustomUserCreationForm(data=_signup_data())
        self.assertTrue(form.is_valid(), form.errors)


class RegistrationFlowTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()

    @patch('users.views.auth.send_email_verification', return_value=True)
    def test_registration_signs_the_new_member_in(self, _send):
        response = self.client.post(reverse('users:register'), data=_signup_data())

        self.assertRedirects(response, reverse('users:profile'), fetch_redirect_response=False)
        user = User.objects.get(username='phone-user')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(user.membership_status, 'active')

    def test_password_errors_are_rendered_for_the_user(self):
        response = self.client.post(
            reverse('users:register'),
            data=_signup_data(password1='short1', password2='short1'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='phone-user').exists())
        self.assertContains(response, 'id="pw-alert"')
        self.assertContains(response, 'data-start-step="2"')

    def test_missing_consent_reopens_the_last_step(self):
        data = _signup_data()
        del data['membership_consent']
        response = self.client.post(reverse('users:register'), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-start-step="3"')

    def test_signup_form_has_mobile_friendly_inputs(self):
        response = self.client.get(reverse('users:register'))
        html = response.content.decode()
        username_tag = re.search(r'<input[^>]*name="username"[^>]*>', html).group(0)
        email_tag = re.search(r'<input[^>]*name="email"[^>]*>', html).group(0)
        for tag in (username_tag, email_tag):
            self.assertIn('autocapitalize="none"', tag)
            self.assertIn('autocorrect="off"', tag)
        self.assertIn('inputmode="email"', email_tag)
        # Submit must never ship disabled: a stuck disabled button was a dead end on phones.
        submit_tag = re.search(r'<button[^>]*id="reg-submit-btn"[^>]*>', html).group(0)
        self.assertNotIn('disabled', submit_tag)

    def test_register_page_redirects_signed_in_members(self):
        user = User.objects.create_user(username='already', password='Some-Long-Pass1')
        self.client.force_login(user)
        response = self.client.get(reverse('users:register'))
        self.assertRedirects(response, reverse('users:profile'), fetch_redirect_response=False)

    def test_rate_limit_shows_a_message_instead_of_a_403_page(self):
        url = reverse('users:register')
        for _ in range(30):
            self.client.post(url, data={'username': '', **human_fields()})
        response = self.client.post(url, data={'username': '', **human_fields()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many sign-up attempts')


class LoginBackendTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()
        self.user = User.objects.create_user(
            username='slava2004', email='slava@example.com', password='Some-Long-Pass1',
        )

    def _login(self, identifier, password='Some-Long-Pass1'):
        self.client.logout()
        return self.client.login(username=identifier, password=password)

    def test_exact_username(self):
        self.assertTrue(self._login('slava2004'))

    def test_phone_capitalised_username(self):
        self.assertTrue(self._login('Slava2004'))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertTrue(self._login('  slava2004 '))

    def test_login_by_email_any_case(self):
        self.assertTrue(self._login('Slava@Example.com'))

    def test_wrong_password_is_rejected(self):
        self.assertFalse(self._login('Slava2004', 'wrong-password-1'))
        self.assertFalse(self._login('slava@example.com', 'wrong-password-1'))

    def test_ambiguous_email_logs_nobody_in(self):
        User.objects.create_user(username='twin', email='SLAVA@example.com', password='Some-Long-Pass1')
        self.assertFalse(self._login('slava@example.com'))

    def test_exact_username_beats_case_insensitive_twin(self):
        User.objects.create_user(username='Slava2004', password='Other-Long-Pass2')
        self.assertTrue(self._login('slava2004'))
        self.assertTrue(self._login('Slava2004', 'Other-Long-Pass2'))

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertFalse(self._login('slava2004'))

    def test_login_view_posts_work_for_capitalised_name(self):
        response = self.client.post(reverse('users:login'), {'username': 'Slava2004', 'password': 'Some-Long-Pass1'})
        self.assertEqual(response.status_code, 302)


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()
        self.user = User.objects.create_user(
            username='forgetful', email='forgetful@example.com', password='Old-Long-Pass1',
        )

    def test_login_page_links_to_reset(self):
        response = self.client.get(reverse('users:login'))
        self.assertContains(response, reverse('users:password_reset'))

    def test_known_email_receives_a_working_link(self):
        response = self.client.post(reverse('users:password_reset'), {'email': 'Forgetful@Example.com', **human_fields()})
        self.assertRedirects(response, reverse('users:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn('forgetful', body)
        link = re.search(r'https?://[^\s]+/auth/password-reset/[^\s]+/', body).group(0)
        path = '/' + link.split('/', 3)[3]

        # Django swaps the token for a session URL on first visit, then shows the form.
        response = self.client.get(path, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['validlink'])
        self.assertContains(response, 'name="new_password1"')

        post_url = response.redirect_chain[-1][0]
        response = self.client.post(post_url, {
            'new_password1': 'Brand-New-Phone-Pass',
            'new_password2': 'Brand-New-Phone-Pass',
        })
        self.assertRedirects(response, reverse('users:password_reset_complete'))
        self.assertTrue(self.client.login(username='forgetful', password='Brand-New-Phone-Pass'))

    def test_unknown_email_looks_identical_and_sends_nothing(self):
        response = self.client.post(reverse('users:password_reset'), {'email': 'nobody@example.com', **human_fields()})
        self.assertRedirects(response, reverse('users:password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_broken_mail_backend_does_not_leak_a_500(self):
        with patch('django.core.mail.EmailMultiAlternatives.send', side_effect=OSError('smtp down')):
            response = self.client.post(reverse('users:password_reset'), {'email': 'forgetful@example.com', **human_fields()})
        self.assertRedirects(response, reverse('users:password_reset_done'))

    def test_invalid_link_offers_a_new_one(self):
        response = self.client.get(reverse('users:password_reset_confirm', args=['bad', 'bad-token']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('users:password_reset'))

    def test_reset_still_rejects_too_short_passwords(self):
        self.client.post(reverse('users:password_reset'), {'email': 'forgetful@example.com', **human_fields()})
        link = re.search(r'https?://[^\s]+/auth/password-reset/[^\s]+/', mail.outbox[0].body).group(0)
        response = self.client.get('/' + link.split('/', 3)[3], follow=True)
        response = self.client.post(response.redirect_chain[-1][0], {
            'new_password1': 'short1', 'new_password2': 'short1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.login(username='forgetful', password='Old-Long-Pass1'))
