from django.db import models
from django.conf import settings
from django.utils import timezone


class Notification(models.Model):
    """
    User notifications for various events (post approved, new comment, new like, etc.)
    """
    NOTIFICATION_TYPES = [
        ('post_approved', 'Post Approved'),
        ('post_rejected', 'Post Rejected'),
        ('new_comment', 'New Comment'),
        ('comment_reply', 'Comment Reply'),
        ('new_like', 'New Like'),
        ('new_follower', 'New Follower'),
        ('event_reminder', 'Event Reminder'),
        ('new_message', 'New Message'),
        ('system', 'System Notification'),
    ]
    
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Recipient'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        null=True,
        blank=True,
        verbose_name='Sender'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        verbose_name='Type'
    )
    title = models.CharField(max_length=255, verbose_name='Title')
    message = models.TextField(verbose_name='Message')
    link = models.CharField(max_length=500, blank=True, verbose_name='Link')
    
    is_read = models.BooleanField(default=False, verbose_name='Read')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Read at')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
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
