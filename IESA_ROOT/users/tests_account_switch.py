"""Switching between several accounts on one device, and the scanner-path hardening."""
from django.core.cache import caches
from django.test import TestCase
from django.urls import reverse

from users import account_switch
from users.models import User

PASSWORD_A = 'First-Account-Pass1'
PASSWORD_B = 'Second-Account-Pass2'


def _cookie(client):
    morsel = client.cookies.get(account_switch.COOKIE_NAME)
    return morsel.value if morsel else ''


class AccountSwitchTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()
        self.a = User.objects.create_user(username='personal', email='a@example.com', password=PASSWORD_A)
        self.b = User.objects.create_user(username='business', email='b@example.com', password=PASSWORD_B)

    def _whoami(self):
        return int(self.client.session['_auth_user_id'])

    def _add_b_while_signed_in_as_a(self):
        self.client.login(username='personal', password=PASSWORD_A)
        return self.client.post(
            reverse('users:login'),
            {'username': 'business', 'password': PASSWORD_B, 'add_account': '1', 'next': ''},
        )

    # -- adding ----------------------------------------------------------------
    def test_signed_in_member_can_open_the_login_form_to_add_an_account(self):
        self.client.login(username='personal', password=PASSWORD_A)
        response = self.client.get(reverse('users:login') + '?add_account=1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'add_account')
        self.assertContains(response, 'personal')

    def test_login_form_still_redirects_signed_in_members_normally(self):
        self.client.login(username='personal', password=PASSWORD_A)
        self.assertEqual(self.client.get(reverse('users:login')).status_code, 302)

    def test_adding_signs_in_to_the_new_account_and_links_both(self):
        response = self._add_b_while_signed_in_as_a()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._whoami(), self.b.pk)
        self.assertTrue(_cookie(self.client))
        page = self.client.get(reverse('users:profile'))
        self.assertContains(page, reverse('users:switch_account', args=[self.a.pk]))
        self.assertNotContains(page, reverse('users:switch_account', args=[self.b.pk]))

    def test_wrong_password_while_adding_changes_nothing(self):
        self.client.login(username='personal', password=PASSWORD_A)
        self.client.post(reverse('users:login'), {'username': 'business', 'password': 'nope', 'add_account': '1'})
        self.assertEqual(self._whoami(), self.a.pk)
        self.assertEqual(_cookie(self.client), '')

    # -- switching -------------------------------------------------------------
    def test_switch_back_and_forth(self):
        self._add_b_while_signed_in_as_a()
        self.assertEqual(self.client.post(reverse('users:switch_account', args=[self.a.pk])).status_code, 302)
        self.assertEqual(self._whoami(), self.a.pk)
        self.client.post(reverse('users:switch_account', args=[self.b.pk]))
        self.assertEqual(self._whoami(), self.b.pk)

    def test_switch_returns_to_a_safe_next_page_only(self):
        self._add_b_while_signed_in_as_a()
        response = self.client.post(reverse('users:switch_account', args=[self.a.pk]), {'next': '/blog/'})
        self.assertEqual(response['Location'], '/blog/')
        response = self.client.post(reverse('users:switch_account', args=[self.b.pk]), {'next': 'https://evil.example/x'})
        self.assertEqual(response['Location'], reverse('users:profile'))

    def test_cannot_switch_to_an_account_that_was_never_linked(self):
        stranger = User.objects.create_user(username='stranger', password='Stranger-Pass-3')
        self.client.login(username='personal', password=PASSWORD_A)
        self.client.post(reverse('users:switch_account', args=[stranger.pk]))
        self.assertEqual(self._whoami(), self.a.pk)

    def test_switch_needs_post_and_a_session(self):
        self._add_b_while_signed_in_as_a()
        self.assertEqual(self.client.get(reverse('users:switch_account', args=[self.a.pk])).status_code, 405)
        self.client.logout()
        response = self.client.post(reverse('users:switch_account', args=[self.a.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:login'), response['Location'])
        self.assertNotIn('_auth_user_id', self.client.session)

    # -- revocation ------------------------------------------------------------
    def test_changing_a_password_revokes_that_link(self):
        self._add_b_while_signed_in_as_a()
        self.a.set_password('Brand-New-Pass-9')
        self.a.save()
        self.client.post(reverse('users:switch_account', args=[self.a.pk]))
        self.assertEqual(self._whoami(), self.b.pk)               # still B: the link to A is dead

    def test_deactivated_account_cannot_be_switched_to(self):
        self._add_b_while_signed_in_as_a()
        User.objects.filter(pk=self.a.pk).update(is_active=False)
        self.client.post(reverse('users:switch_account', args=[self.a.pk]))
        self.assertEqual(self._whoami(), self.b.pk)

    def test_tampered_cookie_is_ignored(self):
        self._add_b_while_signed_in_as_a()
        self.client.cookies[account_switch.COOKIE_NAME] = _cookie(self.client)[:-4] + 'AAAA'
        self.client.post(reverse('users:switch_account', args=[self.a.pk]))
        self.assertEqual(self._whoami(), self.b.pk)

    def test_forged_cookie_for_another_user_is_ignored(self):
        from django.core import signing
        self.client.login(username='personal', password=PASSWORD_A)
        victim = User.objects.create_user(username='victim', password='Victim-Pass-4')
        self.client.cookies[account_switch.COOKIE_NAME] = signing.dumps(
            {str(victim.pk): 'guessed-fingerprint'}, salt=account_switch.SALT)
        self.client.post(reverse('users:switch_account', args=[victim.pk]))
        self.assertEqual(self._whoami(), self.a.pk)

    # -- shared-computer safety ------------------------------------------------
    def test_logout_wipes_the_linked_list(self):
        self._add_b_while_signed_in_as_a()
        self.client.post(reverse('users:logout'))
        self.assertEqual(_cookie(self.client), '')

    def test_an_ordinary_login_wipes_the_linked_list(self):
        self._add_b_while_signed_in_as_a()
        self.client.post(reverse('users:logout'))
        stranger = User.objects.create_user(username='stranger', password='Stranger-Pass-3')
        response = self.client.post(reverse('users:login'), {'username': 'stranger', 'password': 'Stranger-Pass-3'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(_cookie(self.client), '')
        self.assertEqual(account_switch.linked_accounts(response.wsgi_request, exclude=stranger), [])

    def test_cookie_is_httponly_and_lax(self):
        response = self._add_b_while_signed_in_as_a()
        morsel = response.cookies[account_switch.COOKIE_NAME]
        self.assertTrue(morsel['httponly'])
        self.assertEqual(morsel['samesite'], 'Lax')

    def test_list_is_capped(self):
        self.client.login(username='personal', password=PASSWORD_A)
        extra = [User.objects.create_user(username=f'extra{i}', password=f'Extra-Pass-{i}-x') for i in range(7)]
        for i, user in enumerate(extra):
            self.client.post(reverse('users:login'), {
                'username': user.username, 'password': f'Extra-Pass-{i}-x', 'add_account': '1'})
        from django.core import signing
        data = signing.loads(_cookie(self.client), salt=account_switch.SALT)
        self.assertEqual(len(data), account_switch.MAX_ACCOUNTS)

    def test_menu_offers_add_account_to_everyone_signed_in(self):
        self.client.login(username='personal', password=PASSWORD_A)
        self.assertContains(self.client.get(reverse('users:profile')), 'add_account=1')


class ScannerPathTests(TestCase):
    def test_double_slash_wordpress_probes_get_the_cheap_404(self):
        for path in ('//test/wp-includes/wlwmanifest.xml', '//site/wp-admin/install.php', '/blog//wp-content/x.js', '/xmlrpc.php'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.content, b'')

    def test_real_pages_are_untouched(self):
        self.assertEqual(self.client.get('/').status_code, 200)
