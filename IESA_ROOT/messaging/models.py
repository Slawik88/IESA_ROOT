from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Q


class Conversation(models.Model):
    """
    Represents a conversation between participants.
    Scalable design: supports future group messaging (participants ManyToMany).
    """
    # ManyToMany allows for future group chats
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='conversations',
        verbose_name='Participants'
    )
    # Roles
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_conversations',
        verbose_name='Creator'
    )
    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='admin_conversations',
        verbose_name='Admins'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last Updated')
    
    # Future: add is_group, group_name, group_avatar fields
    is_group = models.BooleanField(default=False, verbose_name='Is Group Chat')
    group_name = models.CharField(max_length=255, blank=True, verbose_name='Group Name')
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
        indexes = [
            models.Index(fields=['-updated_at']),
        ]
    
    def __str__(self):
        if self.is_group:
            return f"Group: {self.group_name or f'Conversation {self.pk}'}"
        participants = self.participants.all()[:2]
        return f"Chat: {' & '.join([p.username for p in participants])}"
    
    def get_other_participant(self, user):
        """Get the other participant in a 1-on-1 conversation"""
        return self.participants.exclude(pk=user.pk).first()

    def is_admin(self, user):
        """Check if user has admin permissions in this conversation."""
        if user is None:
            return False
        return (self.creator_id == user.id) or self.admins.filter(pk=user.pk).exists()
    
    def get_last_message(self):
        """Get the most recent message in this conversation"""
        return self.messages.first()
    
    def get_unread_count(self, user):
        """Get count of unread messages for a specific user"""
        return self.messages.filter(
            ~Q(sender=user)
        ).exclude(read_by=user).count()


class Message(models.Model):
    """
    Represents a single message within a conversation.
    Supports text, files, read receipts, pinning, and deletion.
    """
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Conversation'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        verbose_name='Sender'
    )
    
    # Message content
    text = models.TextField(verbose_name='Message Text', blank=True, default='')
    
    # File/media support
    file = models.FileField(
        upload_to='messages/files/',
        blank=True,
        null=True,
        verbose_name='Attached File'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Sent At')
    edited_at = models.DateTimeField(null=True, blank=True, verbose_name='Edited At')
    
    # Read receipts - ManyToMany to track who read the message
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='read_messages',
        blank=True,
        verbose_name='Read By'
    )
    
    # Message status
    is_pinned = models.BooleanField(default=False, verbose_name='Pinned')
    is_deleted = models.BooleanField(default=False, verbose_name='Deleted')
    deleted_for_everyone = models.BooleanField(default=False, verbose_name='Deleted for Everyone')
    
    # Reply/thread support (future enhancement)
    reply_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replies',
        verbose_name='Reply To'
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['is_deleted', '-created_at']),  # For filtering deleted messages
        ]
    
    def __str__(self):
        return f"{self.sender.username}: {self.text[:50]}"
    
    def mark_as_read(self, user):
        """Mark message as read by a user"""
        if user != self.sender:
            self.read_by.add(user)
    
    def is_read_by(self, user):
        """Check if message was read by a user"""
        return self.read_by.filter(pk=user.pk).exists()


class TypingIndicator(models.Model):
    """
    DEPRECATED: This model is replaced by cache-based typing indicators (see typing_cache.py).
    Kept for backwards compatibility. Can be safely removed after migration.
    
    Old: Temporary model to track who is typing in which conversation.
    Now: Use typing_cache.set_typing_v2() and typing_cache.get_typing_users_v2() instead.
    """
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='typing_indicators',
        verbose_name='Conversation'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='User'
    )
    timestamp = models.DateTimeField(auto_now=True, verbose_name='Last Update')
    
    class Meta:
        unique_together = ['conversation', 'user']
        verbose_name = 'Typing Indicator'
        verbose_name_plural = 'Typing Indicators'
    
    def __str__(self):
        return f"{self.user.username} typing in {self.conversation}"
    
    @classmethod
    def set_typing(cls, conversation, user):
        """Set user as typing in conversation"""
        obj, created = cls.objects.update_or_create(
            conversation=conversation,
            user=user,
            defaults={'timestamp': timezone.now()}
        )
        return obj
    
    @classmethod
    def get_typing_users(cls, conversation, exclude_user=None):
        """Get list of users currently typing (within last 5 seconds)"""
        threshold = timezone.now() - timezone.timedelta(seconds=5)
        queryset = cls.objects.filter(
            conversation=conversation,
            timestamp__gte=threshold
        )
        if exclude_user:
            queryset = queryset.exclude(user=exclude_user)
        return queryset.select_related('user')
