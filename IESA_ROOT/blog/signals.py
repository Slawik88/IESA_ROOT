from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Like, Comment


@receiver(post_save, sender=Like)
def update_user_stats_on_like_created(sender, instance, created, **kwargs):
    """Update user statistics when a like is created"""
    if created and instance.post.author:
        instance.post.author.update_statistics()


@receiver(post_delete, sender=Like)
def update_user_stats_on_like_deleted(sender, instance, **kwargs):
    """Update user statistics when a like is deleted"""
    if instance.post.author:
        instance.post.author.update_statistics()


@receiver(post_save, sender=Comment)
def update_user_stats_on_comment_created(sender, instance, created, **kwargs):
    """Update user statistics when a comment is created"""
    if created:
        # Update author of post stats (they received a comment)
        if instance.post.author:
            instance.post.author.update_statistics()
        # Update author of comment stats (they made a comment)
        if instance.author:
            instance.author.update_statistics()


@receiver(post_delete, sender=Comment)
def update_user_stats_on_comment_deleted(sender, instance, **kwargs):
    """Update user statistics when a comment is deleted"""
    # Update author of post stats
    if instance.post.author:
        instance.post.author.update_statistics()
    # Update author of comment stats
    if instance.author:
        instance.author.update_statistics()
