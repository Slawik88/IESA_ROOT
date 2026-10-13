"""Unread counts are shared and invalidated by supported mutations."""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from users.models import User
from .models import Notification
from .services import get_unread_count


class UnreadCounterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(username='notification-budget')

    def create_notification(self):
        return Notification.objects.create(recipient=self.user, notification_type='system', title='Test')

    def test_warm_database_cache_reads_zero_without_recounting(self):
        self.assertEqual(get_unread_count(self.user.pk), 0)
        with self.assertNumQueries(1):
            self.assertEqual(get_unread_count(self.user.pk), 0)

    def test_create_read_delete_invalidate_counter(self):
        self.assertEqual(get_unread_count(self.user.pk), 0)
        notification = self.create_notification()
        self.assertEqual(get_unread_count(self.user.pk), 1)
        notification.mark_as_read()
        self.assertEqual(get_unread_count(self.user.pk), 0)
        notification = self.create_notification()
        self.assertEqual(get_unread_count(self.user.pk), 1)
        notification.delete()
        self.assertEqual(get_unread_count(self.user.pk), 0)

    def test_mark_all_read_invalidates_bulk_update_and_preserves_other_user(self):
        notification = self.create_notification()
        other = User.objects.create_user(username='other-recipient')
        Notification.objects.create(recipient=other, notification_type='system', title='Other')
        self.assertEqual(get_unread_count(self.user.pk), 1)
        self.client.force_login(self.user)
        self.client.post(reverse('notifications:mark_all_read'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)
        self.assertEqual(get_unread_count(self.user.pk), 0)
        self.assertEqual(get_unread_count(other.pk), 1)
