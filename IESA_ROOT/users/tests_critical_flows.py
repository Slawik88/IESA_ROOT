"""
Critical-path tests for users app (Block 10).

Покрывают: log_visit (PIN, lockout, idempotency), edit/cancel (20-min window),
           invite_register (token validation), insurance (duplicate prevention),
           dashboard_redirect (role routing), ProfileView (PIN in context).
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from users.models import InviteToken, InsuranceAgentRequest, Partner, User, Visit
from users.services.visit_service import check_idempotent_visit, check_pin_lockout, process_pin_attempt


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_member(username='member1', membership='active'):
    u = User.objects.create_user(username=username, password='pass123X!', membership_status=membership)
    u.totp_secret = 'JBSWY3DPEHPK3PXP'  # known secret for PIN tests
    u.save(update_fields=['totp_secret'])
    return u


def make_partner_user(username='partner1'):
    u = User.objects.create_user(username=username, password='pass123X!', is_partner=True)
    p = Partner.objects.create(user=u, company_name='Test Gym')
    return u, p


# ── visit_service unit tests ──────────────────────────────────────────────────

class CheckPinLockoutTest(TestCase):
    def test_not_locked(self):
        user = make_member()
        locked, _ = check_pin_lockout(user, timezone.now())
        self.assertFalse(locked)

    def test_locked(self):
        user = make_member()
        user.pin_lockout_until = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=['pin_lockout_until'])
        locked, remaining = check_pin_lockout(user, timezone.now())
        self.assertTrue(locked)
        self.assertGreater(remaining, 0)

    def test_expired_lockout_not_locked(self):
        user = make_member()
        user.pin_lockout_until = timezone.now() - timedelta(seconds=1)
        user.save(update_fields=['pin_lockout_until'])
        locked, _ = check_pin_lockout(user, timezone.now())
        self.assertFalse(locked)


class ProcessPinAttemptTest(TestCase):
    def test_correct_pin_returns_ok(self):
        user = make_member()
        pin = user.get_current_pin()
        ok, err = process_pin_attempt(user, pin, timezone.now())
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_wrong_pin_increments_counter(self):
        user = make_member()
        ok, err = process_pin_attempt(user, '000000', timezone.now())
        self.assertFalse(ok)
        self.assertIsNotNone(err)
        user.refresh_from_db()
        self.assertEqual(user.failed_pin_attempts, 1)

    def test_lockout_after_10_attempts(self):
        from users.constants import PIN_MAX_ATTEMPTS
        user = make_member()
        user.failed_pin_attempts = PIN_MAX_ATTEMPTS - 1
        user.save(update_fields=['failed_pin_attempts'])
        ok, err = process_pin_attempt(user, '000000', timezone.now())
        self.assertFalse(ok)
        user.refresh_from_db()
        self.assertIsNotNone(user.pin_lockout_until)
        self.assertEqual(user.failed_pin_attempts, 0)


class CheckIdempotentVisitTest(TestCase):
    def test_no_duplicate_returns_none(self):
        member_user, partner = make_partner_user()
        member = make_member()
        result = check_idempotent_visit(partner, member, 'training', None)
        self.assertIsNone(result)

    def test_recent_duplicate_detected(self):
        partner_user, partner = make_partner_user()
        member = make_member()
        Visit.objects.create(
            member=member, partner=partner,
            service_type='training', cost=None,
            pin_verified=True, status='ACTIVE',
        )
        result = check_idempotent_visit(partner, member, 'training', None)
        self.assertIsNotNone(result)


# ── Edit/Cancel window tests ──────────────────────────────────────────────────

class EditVisitWindowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.partner_user, self.partner = make_partner_user()
        self.member = make_member()
        self.client.login(username='partner1', password='pass123X!')

    def _make_visit(self, age_seconds=0):
        v = Visit.objects.create(
            member=self.member, partner=self.partner,
            service_type='training', pin_verified=True, status='ACTIVE',
        )
        if age_seconds:
            Visit.objects.filter(pk=v.pk).update(
                timestamp=timezone.now() - timedelta(seconds=age_seconds)
            )
        return v

    def test_edit_within_window_allowed(self):
        visit = self._make_visit(60)  # 1 minute ago
        url = reverse('users:edit_visit', kwargs={'visit_id': visit.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_outside_window_redirects(self):
        visit = self._make_visit(1300)  # 21+ minutes ago
        url = reverse('users:edit_visit', kwargs={'visit_id': visit.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_cancel_outside_window_redirects(self):
        visit = self._make_visit(1300)
        url = reverse('users:cancel_visit', kwargs={'visit_id': visit.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_member_history_only_shows_actions_inside_edit_window(self):
        current = self._make_visit(60)
        expired = self._make_visit(1300)

        response = self.client.get(
            reverse('users:partner_member_visits', kwargs={'member_id': self.member.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('users:edit_visit', kwargs={'visit_id': current.pk}),
        )
        self.assertNotContains(
            response,
            reverse('users:edit_visit', kwargs={'visit_id': expired.pk}),
        )


# ── invite_register tests ─────────────────────────────────────────────────────

class InviteRegisterTest(TestCase):
    def setUp(self):
        self.client = Client()
        staff = User.objects.create_user(username='staff', password='pass123X!', is_staff=True)
        self.invite = InviteToken.objects.create(
            partner_type='partner',
            company_name='Test Co',
            expires_at=timezone.now() + timedelta(days=7),
            created_by=staff,
        )

    def test_valid_invite_renders_form(self):
        url = reverse('users:invite_register', kwargs={'token': self.invite.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_generated_invite_message_uses_real_registration_route(self):
        self.client.login(username='staff', password='pass123X!')

        response = self.client.post(reverse('users:invite_generate'), data={
            'partner_type': 'partner',
            'company_name': 'New Partner',
            'max_uses': 1,
            'expires_days': 7,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        created = InviteToken.objects.exclude(pk=self.invite.pk).get()
        expected_path = reverse('users:invite_register', kwargs={'token': created.token})
        messages = [str(message) for message in response.context['messages']]
        self.assertTrue(any(expected_path in message for message in messages))
        self.assertFalse(any('/users/invite/' in message for message in messages))

    def test_expired_invite_returns_410(self):
        self.invite.expires_at = timezone.now() - timedelta(seconds=1)
        self.invite.save(update_fields=['expires_at'])
        url = reverse('users:invite_register', kwargs={'token': self.invite.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 410)

    def test_used_invite_returns_410(self):
        self.invite.is_active = False
        self.invite.save(update_fields=['is_active'])
        url = reverse('users:invite_register', kwargs={'token': self.invite.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 410)

    @patch('users.views.invites.send_email_verification', return_value=True)
    def test_partner_registration_sends_email_verification(self, send_mock):
        url = reverse('users:invite_register', kwargs={'token': self.invite.token})

        response = self.client.post(url, data={
            'username': 'invited_partner',
            'email': 'INVITED@Example.com',
            'first_name': 'Invited',
            'last_name': 'Partner',
            'company_name': 'Test Co',
            'business_type': 'gym',
            'password1': 'Partner!Pass123',
            'password2': 'Partner!Pass123',
        })

        self.assertRedirects(response, reverse('users:partner_dashboard'), fetch_redirect_response=False)
        created = User.objects.get(username='invited_partner')
        self.assertEqual(created.email, 'invited@example.com')
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args.args[0], created)


# ── insurance_agent_request tests ─────────────────────────────────────────────

class InsuranceAgentRequestTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='pass123X!')
        self.client.login(username='testuser', password='pass123X!')

    def test_get_renders_form(self):
        url = reverse('users:insurance_agent')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_submit_creates_request(self):
        url = reverse('users:insurance_agent')
        response = self.client.post(url, {'full_name': 'Test User', 'request_type': 'new_agent'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(InsuranceAgentRequest.objects.filter(user=self.user).count(), 1)

    def test_duplicate_prevented(self):
        InsuranceAgentRequest.objects.create(
            user=self.user, full_name='Test User', request_type='new_agent', status='new',
        )
        url = reverse('users:insurance_agent')
        response = self.client.get(url)
        # Should show status card (не форму), context должен иметь existing
        self.assertIsNotNone(response.context.get('existing'))
        self.assertEqual(response.context['existing'].status, 'new')


# ── dashboard_redirect tests ──────────────────────────────────────────────────

class DashboardRedirectTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_partner_my_cabinet_goes_to_personal_profile(self):
        user, _ = make_partner_user('p_redirect')
        self.client.login(username='p_redirect', password='pass123X!')
        response = self.client.get(reverse('users:dashboard'))
        self.assertRedirects(response, reverse('users:profile'), fetch_redirect_response=False)

    def test_regular_user_goes_to_profile(self):
        user = User.objects.create_user(username='regular', password='pass123X!')
        self.client.login(username='regular', password='pass123X!')
        response = self.client.get(reverse('users:dashboard'))
        self.assertRedirects(response, reverse('users:profile'), fetch_redirect_response=False)

    def test_partner_flag_without_profile_gets_safe_minimal_profile(self):
        user = User.objects.create_user(
            username='flag_only_partner',
            password='pass123X!',
            is_partner=True,
            first_name='Flag',
            last_name='Partner',
        )
        self.client.login(username='flag_only_partner', password='pass123X!')

        response = self.client.get(reverse('users:partner_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.partner_profile.company_name, 'Flag Partner')

    def test_empty_partner_dashboard_has_an_explicit_search_focus_action(self):
        user, _ = make_partner_user('partner_empty_action')
        self.client.force_login(user)

        response = self.client.get(reverse('users:partner_dashboard'))

        self.assertContains(response, 'data-focus-member-search')
        self.assertContains(response, 'type="button"')

    def test_anonymous_partner_route_redirects_to_login_instead_of_400(self):
        response = self.client.get(reverse('users:partner_dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('users:login')}?next={reverse('users:partner_dashboard')}",
        )

    def test_non_staff_telegram_tool_gets_helpful_403_page(self):
        user = User.objects.create_user(username='regular_403', password='pass123X!')
        self.client.force_login(user)

        response = self.client.get(reverse('users:test_telegram'))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')
        self.assertContains(response, 'Access restricted', status_code=403)


class HtmxSessionStateTest(TestCase):
    def test_expired_session_returns_explicit_401_for_htmx(self):
        response = self.client.get(
            reverse('notifications:unread_count'),
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers['X-Session-Expired'], '1')
        self.assertIn(reverse('users:login'), response.headers['X-Login-URL'])
        self.assertIn('next=', response.headers['X-Login-URL'])

    def test_real_permission_denial_stays_403(self):
        user = User.objects.create_user(username='member_no_partner', password='pass123X!')
        self.client.force_login(user)

        response = self.client.get(
            reverse('users:member_autocomplete'),
            {'q': 'member'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn('X-Session-Expired', response.headers)


# ── ProfileView context tests ─────────────────────────────────────────────────

class ProfileViewContextTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_member('profile_test')
        self.client.login(username='profile_test', password='pass123X!')

    def test_profile_page_loads(self):
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)

    def test_pin_in_context_for_active_member(self):
        response = self.client.get(reverse('users:profile'))
        self.assertIn('current_pin', response.context)
        self.assertIn('seconds_remaining', response.context)

    def test_visit_history_in_context(self):
        response = self.client.get(reverse('users:profile'))
        self.assertIn('recent_visits', response.context)
        self.assertIn('total_visits', response.context)

    def test_cabinet_redirect_goes_to_profile(self):
        response = self.client.get('/auth/cabinet/')
        # Should be 301 redirect
        self.assertIn(response.status_code, [301, 302])
