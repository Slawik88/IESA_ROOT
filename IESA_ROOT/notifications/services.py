"""Shared notification counters for templates, polling and streaming."""
from django.core.cache import cache

from .models import Notification


def get_unread_count(user_id):
    key = f'notif_unread_{user_id}'
    count = cache.get(key)
    if count is None:
        count = Notification.objects.filter(recipient_id=user_id, is_read=False).count()
        cache.set(key, count, 30)
    return count
