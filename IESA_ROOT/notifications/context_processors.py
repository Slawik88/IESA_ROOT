from notifications.models import Notification

def unread_notifications(request):
    """Add unread notifications count to context"""
    if request.user.is_authenticated:
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0}
