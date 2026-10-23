from .services import get_unread_count


def unread_notifications(request):
    """Добавляет счётчик непрочитанных уведомлений в контекст каждого шаблона.
    Кэшируется на 30 сек — баланс актуальности и нагрузки на БД (Block 6c)."""
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}

    return {'unread_notifications_count': get_unread_count(request.user.pk)}
