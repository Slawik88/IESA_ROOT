"""Real row-lock tests, enabled on PostgreSQL and skipped on SQLite."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from users.constants import PIN_MAX_ATTEMPTS
from users.models import InviteToken, Partner, User, Visit
from users.forms_verification import InviteRegisterForm
from users.telegram.link import consume_link_code, generate_link_code
from users.services.visit_service import change_visit, log_verified_visit, process_pin_attempt


@skipUnlessDBFeature('has_select_for_update')
class VisitConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='concurrent-operator', is_partner=True)
        self.partner = Partner.objects.create(user=self.operator, company_name='Gym')
        self.member = User.objects.create_user(username='concurrent-member')
        self.data = {'service_type': 'training', 'service_description': '', 'cost': Decimal('10'), 'comments': '', 'reason': 'Correction'}

    def race(self, action):
        barrier = Barrier(2, timeout=10)

        def worker(number):
            close_old_connections()
            try:
                barrier.wait()
                return action(number)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, n) for n in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_concurrent_duplicate_posts_create_exactly_one_visit(self):
        with patch('users.services.visit_notifications.notify_visit_logged'):
            results = self.race(lambda _n: log_verified_visit(partner=self.partner, member=self.member, data=self.data)[1])
        self.assertCountEqual(results, [True, False])
        self.assertEqual(Visit.objects.count(), 1)

    def test_concurrent_wrong_pins_reach_lockout_without_losing_attempts(self):
        User.objects.filter(pk=self.member.pk).update(failed_pin_attempts=PIN_MAX_ATTEMPTS - 2)
        with patch.object(User, 'verify_pin', return_value=False):
            self.race(lambda _n: process_pin_attempt(User.objects.get(pk=self.member.pk), '000000', timezone.now()))
        self.member.refresh_from_db()
        self.assertEqual(self.member.failed_pin_attempts, 0)
        self.assertGreater(self.member.pin_lockout_until, timezone.now())

    def test_concurrent_edits_preserve_both_previous_states(self):
        visit = Visit.objects.create(partner=self.partner, member=self.member, cost=Decimal('1'))
        with patch('users.services.visit_notifications.notify_visit_edited'):
            self.race(lambda n: change_visit(
                visit_id=visit.pk, partner=self.partner, actor=self.operator,
                data={**self.data, 'cost': Decimal(n + 2)},
            ))
        visit.refresh_from_db()
        previous = set(visit.audits.values_list('previous_cost', flat=True))
        self.assertEqual(visit.audits.count(), 2)
        self.assertIn(Decimal('1'), previous)
        self.assertEqual(previous | {visit.cost}, {Decimal('1'), Decimal('2'), Decimal('3')})

    def test_concurrent_link_code_consumption_has_one_winner(self):
        code = generate_link_code(12345)
        results = self.race(lambda _n: consume_link_code(code))
        self.assertCountEqual(results, ['12345', None])

    def test_concurrent_invite_registration_cannot_exceed_max_uses(self):
        invite = InviteToken.objects.create(
            created_by=self.operator, expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        url = reverse('users:invite_register', args=[invite.token])
        validated = Barrier(2, timeout=10)
        original = InviteRegisterForm.is_valid

        def validate_together(form):
            valid = original(form)
            validated.wait()
            return valid

        def register(number):
            return Client().post(url, {
                'username': f'concurrent-invited-{number}', 'email': f'concurrent-{number}@example.com',
                'company_name': 'New partner', 'business_type': 'gym',
                'password1': 'A-unique-invite-password-4739', 'password2': 'A-unique-invite-password-4739',
            }).status_code

        with patch.object(InviteRegisterForm, 'is_valid', validate_together):
            with patch('users.views.invites.send_email_verification', return_value=True):
                results = self.race(register)
        self.assertCountEqual(results, [302, 410])
        invite.refresh_from_db()
        self.assertEqual(invite.use_count, 1)
        self.assertEqual(User.objects.filter(username__startswith='concurrent-invited-').count(), 1)
