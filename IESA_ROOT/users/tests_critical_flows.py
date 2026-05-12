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

    def test_partner_goes_to_partner_dashboard(self):
        user, _ = make_partner_user('p_redirect')
        self.client.login(username='p_redirect', password='pass123X!')
        response = self.client.get(reverse('users:dashboard'))
        self.assertRedirects(response, reverse('users:partner_dashboard'), fetch_redirect_response=False)

    def test_regular_user_goes_to_profile(self):
        user = User.objects.create_user(username='regular', password='pass123X!')
        self.client.login(username='regular', password='pass123X!')
        response = self.client.get(reverse('users:dashboard'))
        self.assertRedirects(response, reverse('users:profile'), fetch_redirect_response=False)


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
