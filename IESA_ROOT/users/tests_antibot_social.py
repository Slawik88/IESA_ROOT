"""Bot defences, social sign-in rules, privacy placeholder and the cleanup command."""
import time
from io import StringIO
from unittest.mock import MagicMock, patch

import requests
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail, signing
from django.core.cache import caches
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from datetime import timedelta

from django.utils import timezone

from users import antispam
from users.models import User
from users.services.email_verification import send_email_verification
from users.social import IESASocialAccountAdapter, generate_username
from users.tests_support import human_fields

SIGNUP = {
    'username': 'real-person',
    'email': 'real.person@example.com',
    'password1': 'a-perfectly-fine-passphrase',
    'password2': 'a-perfectly-fine-passphrase',
    'membership_consent': True,
}


class RegistrationAntiBotTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()
        self.url = reverse('users:register')

    def _post(self, **extra):
        return self.client.post(self.url, {**SIGNUP, **extra})

    def assertRefused(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='real-person').exists())
        self.assertContains(response, 'could not verify that you are human')

    def test_human_post_is_accepted(self):
        with patch('users.views.auth.send_email_verification', return_value=True):
            response = self._post(**human_fields())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='real-person').exists())

    def test_post_without_timer_token_is_refused(self):
        self.assertRefused(self._post())

    def test_honeypot_filled_is_refused(self):
        self.assertRefused(self._post(**human_fields(), **{antispam.HONEYPOT_FIELD: 'http://spam.example'}))

    def test_submitted_too_fast_is_refused(self):
        self.assertRefused(self._post(**human_fields(age_seconds=0)))

    def test_forged_token_is_refused(self):
        self.assertRefused(self._post(**{antispam.TIMER_FIELD: 'forged.value'}))

    def test_token_signed_with_another_salt_is_refused(self):
        wrong = signing.dumps(int(time.time()) - 30, salt='something-else')
        self.assertRefused(self._post(**{antispam.TIMER_FIELD: wrong}))

    def test_form_page_carries_token_and_hidden_honeypot(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'name="{antispam.TIMER_FIELD}"')
        self.assertContains(response, f'name="{antispam.HONEYPOT_FIELD}"')
        self.assertContains(response, 'tabindex="-1"')

    def test_disposable_email_is_refused(self):
        response = self._post(email='bot@mailinator.com', **human_fields())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'permanent e-mail address')
        self.assertFalse(User.objects.filter(username='real-person').exists())

    def test_disposable_subdomain_is_refused(self):
        self.assertTrue(antispam.is_disposable_email('x@foo.yopmail.com'))
        self.assertFalse(antispam.is_disposable_email('x@gmail.com'))

    def test_persistent_ip_cap_blocks_after_60_attempts(self):
        for _ in range(60):
            antispam.throttle('register-ip', '127.0.0.1', 60, 3600)
        response = self._post(**human_fields())
        self.assertContains(response, 'Too many sign-up attempts')
        self.assertFalse(User.objects.filter(username='real-person').exists())


@override_settings(TURNSTILE_SITE_KEY='site-key', TURNSTILE_SECRET_KEY='secret-key')
class TurnstileTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()
        self.url = reverse('users:register')

    def _post(self, **extra):
        return self.client.post(self.url, {**SIGNUP, **human_fields(), **extra})

    def test_widget_is_rendered_when_configured(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'class="cf-turnstile"')
        self.assertContains(response, 'data-sitekey="site-key"')

    def test_missing_token_is_refused(self):
        response = self._post()
        self.assertContains(response, 'could not verify that you are human')
        self.assertFalse(User.objects.filter(username='real-person').exists())

    @patch('users.antispam.requests.post')
    def test_cloudflare_rejection_is_refused(self, post):
        post.return_value = MagicMock(json=lambda: {'success': False})
        response = self._post(**{antispam.TURNSTILE_FIELD: 'bad'})
        self.assertContains(response, 'could not verify that you are human')

    @patch('users.views.auth.send_email_verification', return_value=True)
    @patch('users.antispam.requests.post')
    def test_cloudflare_approval_is_accepted(self, post, _send):
        post.return_value = MagicMock(json=lambda: {'success': True})
        response = self._post(**{antispam.TURNSTILE_FIELD: 'good'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(post.call_args.kwargs['data']['secret'], 'secret-key')

    @patch('users.views.auth.send_email_verification', return_value=True)
    @patch('users.antispam.requests.post', side_effect=requests.ConnectionError('down'))
    def test_cloudflare_outage_does_not_lock_everyone_out(self, _post, _send):
        response = self._post(**{antispam.TURNSTILE_FIELD: 'whatever'})
        self.assertEqual(response.status_code, 302)

    def test_disabled_without_keys(self):
        with override_settings(TURNSTILE_SITE_KEY='', TURNSTILE_SECRET_KEY=''):
            self.assertNotContains(self.client.get(self.url), 'class="cf-turnstile"')


class MailBombProtectionTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()
        self.user = User.objects.create_user(username='victim', email='victim@example.com', password='Some-Long-Pass1')

    @patch('users.services.email_verification._send', return_value=True)
    def test_one_address_gets_at_most_three_verification_mails_per_hour(self, send):
        results = [send_email_verification(self.user) for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])
        self.assertEqual(send.call_count, 3)

    @patch('users.services.email_verification._send', return_value=True)
    def test_one_account_cannot_spray_many_addresses(self, send):
        sent = 0
        for i in range(15):
            self.user.email = f'target{i}@example.com'
            self.user.save()
            sent += bool(send_email_verification(self.user))
        self.assertEqual(sent, 10)

    @patch('users.services.email_verification._send', return_value=True)
    def test_global_hourly_budget(self, send):
        for _ in range(300):
            antispam.throttle('ev-global', 'all', 300, 3600)
        self.assertFalse(send_email_verification(self.user))
        send.assert_not_called()

    def test_password_reset_mails_per_address_are_capped(self):
        for _ in range(5):
            self.client.post(reverse('users:password_reset'), {'email': 'victim@example.com', **human_fields()})
        self.assertEqual(len(mail.outbox), 3)

    def test_password_reset_bot_gets_nothing(self):
        response = self.client.post(
            reverse('users:password_reset'),
            {'email': 'victim@example.com', **human_fields(), antispam.HONEYPOT_FIELD: 'x'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_without_token_gets_nothing(self):
        self.client.post(reverse('users:password_reset'), {'email': 'victim@example.com'})
        self.assertEqual(len(mail.outbox), 0)


GOOGLE = {'google': {'APP': {'client_id': 'cid', 'secret': 'sec', 'key': ''}}}


class SocialLoginTests(TestCase):
    def setUp(self):
        self.adapter = IESASocialAccountAdapter()
        self.request = RequestFactory().get('/')
        self.request.session = {}
        self.request._messages = FallbackStorage(self.request)
        self.request.user = MagicMock(is_authenticated=False)

    def _login(self, email, verified, uid='g-1'):
        return SocialLogin(
            user=User(email=email),
            account=SocialAccount(provider='google', uid=uid, extra_data={}),
            email_addresses=[EmailAddress(email=email, verified=verified, primary=True)],
        )

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE)
    def test_provider_buttons_are_not_nested_inside_the_register_form(self):
        """Nested <form>s are invalid HTML: the inner </form> would cut the real form short."""
        html = self.client.get(reverse('users:register')).content.decode()
        start = html.index('id="reg-form"')
        end = html.index('</form>', start)
        inside = html[start:end]
        self.assertNotIn('<form', inside)
        self.assertIn('id="reg-submit-btn"', inside)
        self.assertIn(f'name="{antispam.TIMER_FIELD}"', inside)

    def test_csp_lets_the_provider_redirect_through(self):
        """form-action also applies to the 302 after a form POST: without the provider host the
        browser blocks the redirect and the sign-in button spins forever."""
        csp = self.client.get(reverse('users:login'))['Content-Security-Policy']
        form_action = next(d for d in csp.split(';') if d.strip().startswith('form-action'))
        for host in ('https://accounts.google.com', 'https://login.microsoftonline.com',
                     'https://www.facebook.com', 'https://appleid.apple.com'):
            self.assertIn(host, form_action)
        self.assertIn("'self'", form_action)

    def test_no_buttons_without_keys(self):
        self.assertNotContains(self.client.get(reverse('users:login')), 'soc-btn')

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE)
    def test_buttons_appear_when_a_provider_is_configured(self):
        for name in ('users:login', 'users:register'):
            response = self.client.get(reverse(name))
            self.assertContains(response, 'soc-btn')
            self.assertContains(response, '/accounts/google/login/')

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE)
    def test_sign_in_is_post_only_and_redirects_to_google(self):
        self.assertNotEqual(self.client.get('/accounts/google/login/').status_code, 302)
        response = self.client.post('/accounts/google/login/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts.google.com', response['Location'])
        self.assertIn('client_id=cid', response['Location'])

    def test_allauth_can_log_a_member_in_with_our_backend_setup(self):
        """With several backends configured Django needs user.backend; allauth must pick one itself."""
        from allauth.account.adapter import get_adapter
        from django.contrib.sessions.middleware import SessionMiddleware
        member = User.objects.create_user(username='sociable', email='s@example.com', password='Some-Long-Pass1')
        request = RequestFactory().get('/')
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        get_adapter().login(request, member)
        self.assertEqual(request.session['_auth_user_id'], str(member.pk))

    def test_allauth_own_signup_and_login_pages_are_not_exposed(self):
        self.assertRedirects(self.client.get('/accounts/signup/'), reverse('users:register'), fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/accounts/login/'), reverse('users:login'), fetch_redirect_response=False)
        self.assertEqual(self.client.get('/accounts/email/').status_code, 404)
        self.assertEqual(self.client.get('/accounts/password/reset/').status_code, 404)

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE)
    def test_verified_email_links_to_existing_member_and_confirms_email(self):
        member = User.objects.create_user(username='member', email='Member@Example.com', password='Some-Long-Pass1')
        sociallogin = self._login('member@example.com', verified=True)
        self.adapter.pre_social_login(self.request, sociallogin)
        self.assertEqual(sociallogin.user.pk, member.pk)
        self.assertTrue(SocialAccount.objects.filter(user=member, provider='google', uid='g-1').exists())
        member.refresh_from_db()
        self.assertIsNotNone(member.email_verified_at)
        self.assertEqual(User.objects.count(), 1)

    def test_unverified_provider_email_is_never_linked(self):
        User.objects.create_user(username='victim', email='victim@example.com', password='Some-Long-Pass1')
        sociallogin = self._login('victim@example.com', verified=False)
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(self.request, sociallogin)
        self.assertFalse(SocialAccount.objects.exists())

    def test_inactive_member_is_not_linked(self):
        User.objects.create_user(username='gone', email='gone@example.com', password='Some-Long-Pass1', is_active=False)
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(self.request, self._login('gone@example.com', verified=True))

    def test_unknown_email_passes_through_to_signup(self):
        sociallogin = self._login('brand.new@example.com', verified=True)
        self.adapter.pre_social_login(self.request, sociallogin)       # no exception, nothing linked
        self.assertFalse(SocialAccount.objects.exists())

    def test_new_member_is_populated_like_a_normal_registration(self):
        User.objects.create_user(username='anna', password='Some-Long-Pass1')
        sociallogin = self._login('Anna@Example.com', verified=True)
        user = self.adapter.populate_user(
            self.request, sociallogin, {'email': 'Anna@Example.com', 'first_name': 'Anna', 'last_name': 'K'},
        )
        self.assertEqual(user.email, 'anna@example.com')
        self.assertTrue(user.username.lower().startswith('anna'))
        self.assertNotEqual(user.username.lower(), 'anna')                          # 'anna' is taken
        self.assertFalse(User.objects.filter(username__iexact=user.username).exists())
        self.assertEqual(user.membership_status, 'active')
        self.assertIsNotNone(user.email_verified_at)

    def test_username_generation_is_unique_and_clean(self):
        User.objects.create_user(username='Maria', password='Some-Long-Pass1')
        name = generate_username('maria@example.com')
        self.assertNotEqual(name.lower(), 'maria')
        self.assertTrue(name.lower().startswith('maria'))
        self.assertEqual(generate_username(None, 'ab@x.com', 'Ünï cödé'), 'Unicode')
        self.assertEqual(generate_username(''), 'member')


class PrivacyPlaceholderTests(TestCase):
    def test_page_says_policy_is_in_preparation(self):
        response = self.client.get(reverse('core:privacy'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not ready yet')
        self.assertContains(response, 'notify every member')

    def test_register_consent_points_to_it_and_does_not_block(self):
        response = self.client.get(reverse('users:register'))
        self.assertContains(response, reverse('core:privacy'))
        self.assertContains(response, 'still being prepared')

    def test_footer_links_to_it(self):
        self.assertContains(self.client.get(reverse('core:home')), reverse('core:privacy'))


class PruneBotAccountsTests(TestCase):
    def setUp(self):
        old = timezone.now() - timedelta(days=60)
        self.bot = User.objects.create_user(username='bot1', email='bot1@example.com', password='x-Long-Pass-1')
        self.confirmed = User.objects.create_user(
            username='confirmed', email='c@example.com', password='x-Long-Pass-1', email_verified_at=timezone.now())
        self.staff = User.objects.create_user(username='staffer', email='s@example.com', password='x-Long-Pass-1', is_staff=True)
        self.fresh = User.objects.create_user(username='fresh', email='f@example.com', password='x-Long-Pass-1')
        User.objects.filter(pk__in=[self.bot.pk, self.confirmed.pk, self.staff.pk]).update(date_joined=old)

    def _run(self, *args):
        out = StringIO()
        call_command('prune_bot_accounts', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing_and_lists_only_the_bot(self):
        output = self._run()
        self.assertIn('1 account(s) match', output)
        self.assertIn('bot1', output)
        self.assertEqual(User.objects.count(), 4)

    def test_delete_removes_only_matching_accounts(self):
        self._run('--delete')
        self.assertEqual(set(User.objects.values_list('username', flat=True)), {'confirmed', 'staffer', 'fresh'})
