from django.core.cache import cache
from notifications.models import Notification


def unread_notifications(request):
    """Добавляет счётчик непрочитанных уведомлений в контекст каждого шаблона.
    Кэшируется на 30 сек — баланс актуальности и нагрузки на БД (Block 6c)."""
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}

    cache_key = f'notif_unread_{request.user.pk}'
    count = cache.get(cache_key)
    if count is None:
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        cache.set(cache_key, count, 30)

    return {'unread_notifications_count': count}
