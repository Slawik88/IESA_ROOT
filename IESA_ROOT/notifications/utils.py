"""
Utility functions for creating notifications.
"""
from .models import Notification
from django.urls import reverse


def create_notification(recipient, notification_type, title, message, sender=None, link=''):
    """
    Create a new notification for a user.
    
    Args:
        recipient: User who receives the notification
        notification_type: Type of notification (see Notification.NOTIFICATION_TYPES)
        title: Notification title
        message: Notification message
        sender: User who triggered the notification (optional)
        link: URL link for the notification (optional)
    """
    return Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link
    )


def notify_post_approved(post):
    """Notify user that their post was approved"""
    return create_notification(
        recipient=post.author,
        notification_type='post_approved',
        title='Post Approved! 🎉',
        message=f'Your post "{post.title}" has been approved and is now published.',
        link=reverse('blog:post_detail', args=[post.pk])
    )


def notify_post_rejected(post):
    """Notify user that their post was rejected"""
    return create_notification(
        recipient=post.author,
        notification_type='post_rejected',
        title='Post Needs Review',
        message=f'Your post "{post.title}" was not approved. Please review and edit it.',
        link=reverse('blog:post_detail', args=[post.pk])
    )


def notify_new_comment(comment):
    """Notify post author of a new comment"""
    if comment.author != comment.post.author:  # Don't notify if author comments on own post
        return create_notification(
            recipient=comment.post.author,
            sender=comment.author,
            notification_type='new_comment',
            title='New Comment',
            message=f'{comment.author.username} commented on your post "{comment.post.title}"',
            link=reverse('blog:post_detail', args=[comment.post.pk])
        )


def notify_comment_reply(comment):
    """Notify user of a reply to their comment"""
    if comment.parent and comment.author != comment.parent.author:
        return create_notification(
            recipient=comment.parent.author,
            sender=comment.author,
            notification_type='comment_reply',
            title='New Reply',
            message=f'{comment.author.username} replied to your comment',
            link=reverse('blog:post_detail', args=[comment.post.pk])
        )


def notify_new_like(like):
    """Notify user of a new like on their post"""
    if like.user != like.post.author:
        return create_notification(
            recipient=like.post.author,
            sender=like.user,
            notification_type='new_like',
            title='New Like ❤️',
            message=f'{like.user.username} liked your post "{like.post.title}"',
            link=reverse('blog:post_detail', args=[like.post.pk])
        )


def notify_event_reminder(event, user):
    """Notify user of upcoming event"""
    return create_notification(
        recipient=user,
        notification_type='event_reminder',
        title='Event Reminder 📅',
        message=f'Reminder: "{event.title}" is coming up on {event.date.strftime("%B %d, %Y")}',
        link=reverse('blog:event_detail', args=[event.pk])
    )
