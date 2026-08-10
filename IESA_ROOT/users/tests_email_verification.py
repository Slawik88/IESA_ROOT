from unittest.mock import patch

from django.core import signing
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.forms import CustomUserCreationForm, UserProfileEditForm
from users.forms_verification import InviteRegisterForm
from users.models import User
from users.services.email_verification import (
    EmailVerificationConflict,
    EmailVerificationExpired,
    EmailVerificationInvalid,
    make_email_verification_token,
    send_email_verification,
    verify_email_token,
)


class EmailVerificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='rider',
            email='Rider@Example.com',
            password='Strong!Pass123',
        )

    @patch('users.services.email_verification._send', return_value=True)
    def test_send_uses_normalized_account_and_records_success(self, send_mock):
        delivered = send_email_verification(self.user)

        self.assertTrue(delivered)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.email_verification_sent_at)
        self.assertEqual(send_mock.call_args.args[3], [self.user.email])
        self.assertIn('/auth/email/verify/', send_mock.call_args.args[1])

    @patch('users.services.email_verification._send', return_value=False)
    def test_failed_delivery_does_not_claim_message_was_sent(self, _send_mock):
        self.assertFalse(send_email_verification(self.user))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verification_sent_at)

    def test_valid_token_confirms_current_email_and_is_idempotent(self):
        token = make_email_verification_token(self.user)

        first = verify_email_token(token)
        second = verify_email_token(token)

        self.assertFalse(first.already_verified)
        self.assertTrue(second.already_verified)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

    def test_changing_email_invalidates_old_token(self):
        token = make_email_verification_token(self.user)
        self.user.email = 'new@example.com'
        self.user.save(update_fields=['email'])

        with self.assertRaises(EmailVerificationInvalid):
            verify_email_token(token)

    @patch('users.services.email_verification.signing.loads')
    def test_expired_token_has_separate_safe_error(self, loads_mock):
        loads_mock.side_effect = signing.SignatureExpired('expired')
        with self.assertRaises(EmailVerificationExpired):
            verify_email_token('expired-token')

    def test_address_already_verified_by_another_account_is_rejected(self):
        User.objects.create_user(
            username='verified-owner',
            email='rider@example.com',
            password='Strong!Pass123',
            email_verified_at=timezone.now(),
        )

        with self.assertRaises(EmailVerificationConflict):
            verify_email_token(make_email_verification_token(self.user))


class EmailVerificationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='Strong!Pass123',
        )

    def test_confirmation_link_works_without_login(self):
        response = self.client.get(reverse(
            'users:verify_email',
            kwargs={'token': make_email_verification_token(self.user)},
        ))

        self.assertRedirects(response, reverse('users:login'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

    @patch('users.views.auth.send_email_verification', return_value=True)
    def test_regular_registration_sends_confirmation(self, send_mock):
        response = self.client.post(reverse('users:register'), data={
            'username': 'new-rider',
            'email': 'NEW.RIDER@example.com',
            'password1': 'Strong!Pass123',
            'password2': 'Strong!Pass123',
            'membership_consent': True,
        })

        self.assertRedirects(response, reverse('users:login'))
        created = User.objects.get(username='new-rider')
        self.assertEqual(created.email, 'new.rider@example.com')
        send_mock.assert_called_once_with(created, response.wsgi_request)

    def test_resend_requires_login_and_post(self):
        url = reverse('users:resend_email_verification')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)

    @patch('users.views.auth.send_email_verification', return_value=True)
    def test_resend_has_per_account_cooldown(self, send_mock):
        self.client.force_login(self.user)
        url = reverse('users:resend_email_verification')

        first = self.client.post(url)
        second = self.client.post(url)

        self.assertRedirects(first, reverse('users:profile'))
        self.assertRedirects(second, reverse('users:profile'))
        self.assertEqual(send_mock.call_count, 1)

    @patch('users.views.auth.send_email_verification', return_value=True)
    def test_verified_account_does_not_send_again(self, send_mock):
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields=['email_verified_at'])
        self.client.force_login(self.user)

        self.client.post(reverse('users:resend_email_verification'))

        send_mock.assert_not_called()

    def test_auth_pages_suppress_navigation_that_would_cover_forms(self):
        for route_name in ('users:login', 'users:register'):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'id="mobileBottomNav"')
            self.assertNotContains(response, 'id="pwa-install-sheet"')


class EmailVerificationFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='existing',
            email='Owner@Example.com',
            password='Strong!Pass123',
            email_verified_at=timezone.now(),
        )

    def test_registration_rejects_case_insensitive_duplicate_email(self):
        form = CustomUserCreationForm(data={
            'username': 'new-member',
            'email': 'owner@example.com',
            'password1': 'Another!Pass123',
            'password2': 'Another!Pass123',
            'membership_consent': True,
        })

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_partner_invite_rejects_case_insensitive_duplicate_email(self):
        form = InviteRegisterForm(data={
            'username': 'invited-partner',
            'email': 'owner@example.com',
            'first_name': '',
            'last_name': '',
            'company_name': 'Example Partner',
            'business_type': 'gym',
            'password1': 'Another!Pass123',
            'password2': 'Another!Pass123',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_profile_email_change_resets_verification(self):
        form = UserProfileEditForm(data={
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'email': 'new-owner@example.com',
            'date_of_birth': '',
            'phone_number': '',
            'is_phone_hidden': True,
            'github_url': '',
            'discord_url': '',
            'telegram_url': '',
            'website_url': '',
            'other_links': '',
        }, instance=self.user)

        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.email, 'new-owner@example.com')
        self.assertIsNone(updated.email_verified_at)
        self.assertIsNone(updated.email_verification_sent_at)

    def test_duplicate_email_error_is_visible_on_profile_edit_page(self):
        other = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='Strong!Pass123',
        )
        self.client.force_login(other)

        response = self.client.post(reverse('users:profile_edit'), data={
            'first_name': '',
            'last_name': '',
            'email': 'OWNER@example.com',
            'date_of_birth': '',
            'phone_number': '',
            'is_phone_hidden': True,
            'github_url': '',
            'discord_url': '',
            'telegram_url': '',
            'website_url': '',
            'other_links': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'An account with this e-mail address already exists.')
        self.assertContains(response, 'role="alert"')
