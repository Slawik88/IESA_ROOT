"""Regression tests for visit history, PIN state and invite transactions."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import caches
from django.db import DatabaseError, transaction
from django.http import Http404
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from blog.models import Comment, Like, Post
from users.constants import PIN_MAX_ATTEMPTS
from users.forms_verification import InviteRegisterForm
from users.models import InviteToken, Partner, User, Visit, VisitAudit
from users.services.visit_service import VisitChangeError, change_visit, log_verified_visit, process_pin_attempt


class VisitIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username='visit-operator', is_partner=True)
        cls.partner = Partner.objects.create(user=cls.operator, company_name='Gym')
        cls.member = User.objects.create_user(username='visit-member')

    def setUp(self):
        caches['ratelimit'].clear()
        self.client.force_login(self.operator)
        self.visit = Visit.objects.create(
            partner=self.partner, member=self.member, service_type='training',
            service_description='Original description', cost=Decimal('10.50'), comments='Original comment',
        )
        self.data = {
            'service_type': 'purchase', 'service_description': 'Updated description',
            'cost': Decimal('20.75'), 'comments': 'Updated comment', 'reason': 'Correction',
        }

    def change(self, **extra):
        return change_visit(visit_id=self.visit.pk, partner=self.partner, actor=self.operator, data=self.data, **extra)

    def test_edit_endpoint_keeps_original_values_after_model_form_validation(self):
        response = self.client.post(reverse('users:edit_visit', args=[self.visit.pk]), self.data)
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        audit = self.visit.audits.get()
        self.assertEqual(self.visit.cost, Decimal('20.75'))
        self.assertEqual(self.visit.status, 'EDITED')
        self.assertEqual(audit.previous_cost, Decimal('10.50'))
        self.assertEqual(audit.previous_service_description, 'Original description')
        self.assertEqual(audit.previous_comments, 'Original comment')
        self.assertNotEqual(audit.previous_service_type, self.visit.get_service_type_display())

    def test_failed_audit_rolls_back_visit_update(self):
        with patch.object(VisitAudit, 'save', side_effect=DatabaseError('audit unavailable')):
            with self.assertRaises(DatabaseError):
                self.client.post(reverse('users:edit_visit', args=[self.visit.pk]), self.data)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.cost, Decimal('10.50'))
        self.assertEqual(self.visit.status, 'ACTIVE')
        self.assertFalse(self.visit.audits.exists())

    def test_failed_visit_save_rolls_back_audit(self):
        with patch.object(Visit, 'save', side_effect=DatabaseError('write unavailable')):
            with self.assertRaises(DatabaseError):
                self.change()
        self.assertFalse(self.visit.audits.exists())

    def test_latest_persisted_state_is_used_for_each_audit(self):
        self.change()
        self.data['cost'] = Decimal('30')
        _visit, audit = self.change()
        self.assertEqual(audit.previous_cost, Decimal('20.75'))
        self.assertEqual(self.visit.audits.count(), 2)

    def test_cancel_is_audited_once_and_blocks_later_edits(self):
        self.change(cancel=True)
        for cancel in (True, False):
            with self.subTest(cancel=cancel), self.assertRaises(VisitChangeError):
                self.change(cancel=cancel)
        self.assertEqual(self.visit.audits.count(), 1)

    def test_expired_change_is_rejected_inside_service(self):
        Visit.objects.filter(pk=self.visit.pk).update(timestamp=timezone.now() - timedelta(minutes=21))
        with self.assertRaises(VisitChangeError):
            self.change()
        self.assertFalse(self.visit.audits.exists())

    def test_other_partner_cannot_change_record(self):
        other = User.objects.create_user(username='other-operator', is_partner=True)
        partner = Partner.objects.create(user=other, company_name='Other')
        with self.assertRaises(Http404):
            change_visit(visit_id=self.visit.pk, partner=partner, actor=other, data=self.data)

    def test_notification_runs_after_commit_only(self):
        with patch('users.services.visit_notifications.notify_visit_edited') as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.change()
                notify.assert_not_called()
            notify.assert_called_once()

    def test_rollback_discards_notification(self):
        with patch('users.services.visit_notifications.notify_visit_edited') as notify:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(ValueError), transaction.atomic():
                    self.change()
                    raise ValueError('rollback')
            notify.assert_not_called()
        self.assertFalse(self.visit.audits.exists())

    def test_notification_failure_does_not_turn_committed_edit_into_500(self):
        with patch('users.services.visit_notifications.notify_visit_edited', side_effect=OSError('delivery failed')):
            with self.assertLogs('django.test', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    self.change()
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, 'EDITED')

    def test_verified_duplicate_creates_one_record_and_one_notification(self):
        data = {**self.data, 'service_type': 'consultation'}
        with patch('users.services.visit_notifications.notify_visit_logged') as notify:
            with self.captureOnCommitCallbacks(execute=True):
                first, created = log_verified_visit(partner=self.partner, member=self.member, data=data)
                second, duplicate_created = log_verified_visit(partner=self.partner, member=self.member, data=data)
            notify.assert_called_once()
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(first.pk, second.pk)


class PinStateTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username='pin-state')
        self.now = timezone.now()

    def test_stale_instance_cannot_bypass_new_lockout_even_with_correct_pin(self):
        until = self.now + timedelta(minutes=15)
        User.objects.filter(pk=self.member.pk).update(pin_lockout_until=until)
        with patch.object(User, 'verify_pin', return_value=True) as verify:
            ok, error = process_pin_attempt(self.member, '123456', self.now)
        self.assertFalse(ok)
        self.assertTrue(error)
        verify.assert_not_called()
        self.assertEqual(self.member.pin_lockout_until, until)

    def test_stale_instance_does_not_lose_failed_attempts(self):
        User.objects.filter(pk=self.member.pk).update(failed_pin_attempts=PIN_MAX_ATTEMPTS - 1)
        with patch.object(User, 'verify_pin', return_value=False):
            ok, _error = process_pin_attempt(self.member, '000000', self.now)
        self.assertFalse(ok)
        self.member.refresh_from_db()
        self.assertEqual(self.member.failed_pin_attempts, 0)
        self.assertGreater(self.member.pin_lockout_until, self.now)

    def test_correct_pin_clears_failed_attempts_from_newer_database_state(self):
        User.objects.filter(pk=self.member.pk).update(failed_pin_attempts=4, pin_lockout_until=self.now - timedelta(seconds=1))
        with patch.object(User, 'verify_pin', return_value=True):
            self.assertEqual(process_pin_attempt(self.member, '123456', self.now), (True, None))
        self.member.refresh_from_db()
        self.assertEqual(self.member.failed_pin_attempts, 0)
        self.assertIsNone(self.member.pin_lockout_until)


class InviteTransactionTests(TestCase):
    def setUp(self):
        staff = User.objects.create_user(username='invite-admin', is_staff=True)
        self.invite = InviteToken.objects.create(created_by=staff, expires_at=timezone.now() + timedelta(days=1))
        self.url = reverse('users:invite_register', args=[self.invite.token])
        self.data = {
            'username': 'new-invited', 'email': 'invited@example.com',
            'company_name': 'New partner', 'business_type': 'gym',
            'password1': 'Invited-unique-password-597', 'password2': 'Invited-unique-password-597',
        }

    def test_failed_partner_creation_leaves_no_orphan_user_or_consumed_invite(self):
        with patch('users.views.invites.Partner.objects.create', side_effect=DatabaseError('profile failed')):
            with self.assertRaises(DatabaseError):
                self.client.post(self.url, self.data)
        self.assertFalse(User.objects.filter(username=self.data['username']).exists())
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.use_count, 0)

    def test_token_consumed_during_form_validation_is_rechecked(self):
        original = InviteRegisterForm.is_valid

        def consume_during_validation(form):
            valid = original(form)
            InviteToken.objects.filter(pk=self.invite.pk).update(is_active=False, use_count=1)
            return valid

        with patch.object(InviteRegisterForm, 'is_valid', consume_during_validation):
            response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 410)
        self.assertFalse(User.objects.filter(username=self.data['username']).exists())

    @patch('users.views.invites.send_email_verification', return_value=True)
    def test_multi_use_invite_stops_at_limit(self, _send):
        self.invite.max_uses = 2
        self.invite.save(update_fields=['max_uses'])
        for number in range(2):
            self.client.logout()
            data = {**self.data, 'username': f'partner-{number}', 'email': f'partner-{number}@example.com'}
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.data).status_code, 410)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.use_count, 2)
        self.assertFalse(self.invite.is_active)


class ActivityStatisticsTests(TestCase):
    def test_multiple_likes_and_comments_do_not_multiply_posts_or_likes(self):
        author = User.objects.create_user(username='stats-author')
        readers = [User.objects.create_user(username=f'stats-reader-{number}') for number in range(3)]
        post = Post.objects.create(author=author, title='Published', text='Text', status='published')
        for reader in readers:
            Like.objects.create(post=post, user=reader)
            Comment.objects.create(post=post, author=reader, text='Comment')
        author.update_statistics()
        author.refresh_from_db()
        self.assertEqual(author.total_posts, 1)
        self.assertEqual(author.total_likes_received, 3)
        self.assertEqual(author.activity_points, 16)

    def test_statistics_partial_save_does_not_regenerate_qr_in_spaces(self):
        author = User.objects.create_user(username='stats-qr')
        with self.settings(MEDIA_ROOT=None), patch('users.signals.generate_qr_code_for_user') as generate:
            author.update_statistics()
        generate.assert_not_called()
