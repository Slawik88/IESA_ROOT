"""
Signal handlers for automatic notification creation.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from blog.models import Post, Comment, Like
from .utils import (
    notify_post_approved, 
    notify_post_rejected,
    notify_new_comment,
    notify_comment_reply,
    notify_new_like
)


@receiver(post_save, sender=Post)
def post_status_changed(sender, instance, created, **kwargs):
    """Send notification when post status changes"""
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
        if instance.status == 'published':
            notify_post_approved(instance)
        elif instance.status == 'rejected':
            notify_post_rejected(instance)


@receiver(post_save, sender=Comment)
def comment_created(sender, instance, created, **kwargs):
    """Send notification when new comment is created"""
    if created:
        # Notify post author
        notify_new_comment(instance)
        # Notify parent comment author if it's a reply
        if instance.parent:
            notify_comment_reply(instance)


@receiver(post_save, sender=Like)
def like_created(sender, instance, created, **kwargs):
    """Send notification when new like is created"""
    if created:
        notify_new_like(instance)
