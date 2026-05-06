import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Like, Comment

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Like)
def update_user_stats_on_like_created(sender, instance, created, **kwargs):
    """Update user statistics when a like is created"""
    if created and instance.post.author:
        try:
            instance.post.author.update_statistics()
        except Exception as exc:
            # B2-05: не прерываем транзакцию создания лайка
            logger.error("update_statistics failed after Like create (like=%s): %s", instance.pk, exc, exc_info=True)


@receiver(post_delete, sender=Like)
def update_user_stats_on_like_deleted(sender, instance, **kwargs):
    """Update user statistics when a like is deleted"""
    if instance.post.author:
        try:
            instance.post.author.update_statistics()
        except Exception as exc:
            logger.error("update_statistics failed after Like delete (like=%s): %s", instance.pk, exc, exc_info=True)


@receiver(post_save, sender=Comment)
def update_user_stats_on_comment_created(sender, instance, created, **kwargs):
    """Update user statistics when a comment is created"""
    if not created:
        return
    try:
        if instance.post.author:
            instance.post.author.update_statistics()
        if instance.author:
            instance.author.update_statistics()
    except Exception as exc:
        logger.error("update_statistics failed after Comment create (comment=%s): %s", instance.pk, exc, exc_info=True)


@receiver(post_delete, sender=Comment)
def update_user_stats_on_comment_deleted(sender, instance, **kwargs):
    """Update user statistics when a comment is deleted"""
    try:
        if instance.post.author:
            instance.post.author.update_statistics()
        if instance.author:
            instance.author.update_statistics()
    except Exception as exc:
        logger.error("update_statistics failed after Comment delete (comment=%s): %s", instance.pk, exc, exc_info=True)
