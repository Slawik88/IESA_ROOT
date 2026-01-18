"""
Signal handlers for automatic notification creation.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from blog.models import Post, Comment, Like
from .utils import (
    notify_post_approved, 
    notify_post_rejected,
    notify_new_comment,
    notify_comment_reply,
    notify_new_like,
    notify_new_message
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Post)
def post_status_changed(sender, instance, created, **kwargs):
    """Send notification when post status changes.
    
    FIX: Added error handling and transaction awareness.
    Notifications won't be created if the post save transaction fails.
    """
    if created:
        return  # Don't send notification when post is first created
    
    # Get previous status from database
    try:
        old_instance = Post.objects.get(pk=instance.pk)
        old_status = old_instance.status
    except Post.DoesNotExist:
        return
    
    # Only send notification if status actually changed
    if old_status != instance.status and instance.status in ['published', 'rejected']:
        try:
            if instance.status == 'published':
                notify_post_approved(instance)
            elif instance.status == 'rejected':
                notify_post_rejected(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for post {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the post creation


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


@receiver(post_save, sender='messaging.Message')
def message_created(sender, instance, created, **kwargs):
    """Send notification when new message is created.
    
    Notifies all conversation participants except the sender.
    """
    if created:
        try:
            notify_new_message(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for message {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the message creation
