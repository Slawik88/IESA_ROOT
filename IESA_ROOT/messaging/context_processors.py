from django.db.models import Q
from .models import Message


def unread_messages_count(request):
    """Return unread messages count for authenticated user in templates."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'unread_messages_count': 0}

    try:
        count = Message.objects.filter(
            Q(chat__user1=request.user) | Q(chat__user2=request.user),
            is_read=False,
            is_deleted=False
        ).exclude(sender=request.user).count()
    except Exception:
        count = 0

    return {'unread_messages_count': count}
