"""
Signal handlers for automatic notification creation.
"""
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from blog.models import Post, Comment, Like
from .utils import (
    notify_post_approved, 
    notify_post_rejected,
    notify_new_comment,
    notify_comment_reply,
    notify_new_like
)

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Post)
def capture_previous_post_status(sender, instance, **kwargs):
    """Capture previous status before saving so post_save can compare."""
    if instance.pk:
        try:
            prev = sender.objects.get(pk=instance.pk)
            instance._previous_status = prev.status
        except sender.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=Post)
def post_status_changed(sender, instance, created, **kwargs):
    """Send notification when post status changes (published/rejected)."""
    if created:
        return  # Don't send notification when post is first created

    old_status = getattr(instance, '_previous_status', None)
    new_status = instance.status

    if old_status is None or old_status == new_status:
        return

    if new_status in ['published', 'rejected']:
        try:
            if new_status == 'published':
                notify_post_approved(instance)
            elif new_status == 'rejected':
                notify_post_rejected(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for post {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the post save


@receiver(post_save, sender=Comment)
def comment_created(sender, instance, created, **kwargs):
    """Send notification when new comment is created.
    
    FIX: Added error handling to prevent notification failures from breaking comments.
    """
    if created:
        try:
            # Notify post author
            notify_new_comment(instance)
            # Notify parent comment author if it's a reply
            if instance.parent:
                notify_comment_reply(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for comment {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the comment creation


@receiver(post_save, sender=Like)
def like_created(sender, instance, created, **kwargs):
    """Send notification when new like is created.
    
    FIX: Added error handling.
    """
    if created:
        try:
            notify_new_like(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for like {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the like creation


# @receiver(post_save, sender='messaging.Message')
# def message_created(sender, instance, created, **kwargs):
#     """Send notification when new message is created.
#     
#     Notifies all conversation participants except the sender.
#     DISABLED: messaging app removed from project.
#     """
#     if created:
#         try:
#             notify_new_message(instance)
#         except Exception as e:
#             logger.error(f"Failed to create notification for message {instance.id}: {str(e)}", exc_info=True)
#             # Don't raise - notification failure shouldn't break the message creation
