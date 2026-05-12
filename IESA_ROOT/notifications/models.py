from django.db import models
from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """
    User notifications for various events (post approved, new comment, new like, etc.)
    """
    NOTIFICATION_TYPES = [
        ('post_approved', _('Post Approved')),
        ('post_rejected', _('Post Rejected')),
        ('new_comment', _('New Comment')),
        ('comment_reply', _('Comment Reply')),
        ('new_like', _('New Like')),
        ('new_follower', _('New Follower')),
        ('event_reminder', _('Event Reminder')),
        ('new_message', _('New Message')),
        ('system', _('System Notification')),
    ]
    
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('Recipient')
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        null=True,
        blank=True,
        verbose_name=_('Sender')
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        verbose_name=_('Type')
    )
    title = models.CharField(max_length=255, verbose_name=_('Title'))
    message = models.TextField(verbose_name=_('Message'))
    link = models.CharField(max_length=500, blank=True, verbose_name=_('Link'))
    
    is_read = models.BooleanField(default=False, verbose_name=_('Read'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Read at'))
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['is_read']),
        ]
    
    def __str__(self):
        return f"{self.notification_type} for {self.recipient.username}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
            cache.delete(f'notif_unread_{self.recipient_id}')


@receiver(post_save, sender=Notification)
def _invalidate_unread_cache(sender, instance, created, **kwargs):
    """Инвалидирует кэш счётчика при создании или изменении уведомления (Block 6c)."""
    cache.delete(f'notif_unread_{instance.recipient_id}')
