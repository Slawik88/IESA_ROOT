from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# Try to use CKEditor 5 RichTextField when available, otherwise fall back to TextField
try:
    from django_ckeditor_5.fields import CKEditor5Field
    RichTextField = CKEditor5Field
except Exception:
    RichTextField = models.TextField

class Post(models.Model):
    """
    Модель поста в блоге, подлежит модерации.
    """
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('pending', _('Pending moderation')),
        ('published', _('Published')),
        ('rejected', _('Rejected')),
    ]
    
    title = models.CharField(max_length=255, verbose_name=_('Title'))
    # Use a RichTextField with extended config when ckeditor is installed; otherwise a normal TextField
    text = RichTextField(config_name='extends', verbose_name=_('Post text'))
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_posts', verbose_name=_('Author'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creation date'))
    preview_image = models.ImageField(upload_to='media/blog/previews/', blank=True, null=True, verbose_name=_('Preview image'))
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', db_index=True, verbose_name=_('Status'))
    views_count = models.PositiveIntegerField(default=0, verbose_name=_('Views'))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Post')
        verbose_name_plural = _('Posts')
        indexes = [
            models.Index(fields=['status', '-created_at'], name='post_status_created_idx'),
        ]
        
    def __str__(self):
        return self.title
        
    def get_absolute_url(self):
        return reverse('blog:post_detail', args=[str(self.pk)])
    
    def get_recommended_posts(self, limit=5):
        """
        Get recommended posts based on:
        1. Same author (excluding self)
        2. Random published posts
        """
        from django.db.models import Q
        
        # Get posts by same author (excluding self)
        same_author = Post.objects.filter(
            author=self.author,
            status='published'
        ).exclude(pk=self.pk).order_by('-created_at')[:limit]
        
        # Материализуем один раз — убираем двойной .count() (B2-16)
        same_author_list = list(same_author)
        if len(same_author_list) < limit:
            remaining = limit - len(same_author_list)
            other_posts = Post.objects.filter(
                status='published'
            ).exclude(
                Q(pk=self.pk) | Q(author=self.author)
            ).order_by('-views_count', '-created_at')[:remaining]
            return same_author_list + list(other_posts)

        return same_author_list

class Comment(models.Model):
    """
    Комментарии под постом с поддержкой ответов (replies).
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments', verbose_name=_('Post'))
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments_authored', verbose_name=_('Author'))
    text = models.TextField(verbose_name=_('Comment text'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creation date'))
    
    # Self-referential FK для replies
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies', verbose_name=_('Parent comment'))
    
    class Meta:
        ordering = ['created_at']
        verbose_name = _('Comment')
        verbose_name_plural = _('Comments')
        
    def __str__(self):
        return f'Comment from {self.author.username} to {self.post.title[:20]}...'


class CommentLike(models.Model):
    """
    Лайки для комментариев.
    """
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes', verbose_name=_('Comment'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name=_('User'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user')
        verbose_name = _('Comment Like')
        verbose_name_plural = _('Comment Likes')

    def __str__(self):
        return f'Like from {self.user.username} to comment {self.comment.pk}'

class Like(models.Model):
    """
    Модель для отслеживания лайков. Используем отдельную модель для простоты HTMX.
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes', verbose_name=_('Post'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name=_('User'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Уникальность: один лайк от пользователя на один пост
        unique_together = ('post', 'user')
        verbose_name = _('Like')
        verbose_name_plural = _('Likes')
        
    def __str__(self):
        return f'Like from {self.user.username} to {self.post.title[:20]}...'


class PostView(models.Model):
    """
    Track unique views per user to prevent counting multiple views from same user.
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='user_views', verbose_name=_('Post'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_('User'))
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name=_('IP Address'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('View date'))

    class Meta:
        verbose_name = _('Post View')
        verbose_name_plural = _('Post Views')
        constraints = [
            # (post, user) уникален только для авторизованных (B2-02)
            models.UniqueConstraint(
                fields=['post', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_post_authenticated_view',
            ),
            # (post, ip) уникален только для анонимов
            models.UniqueConstraint(
                fields=['post', 'ip_address'],
                condition=models.Q(user__isnull=True),
                name='unique_post_anonymous_view',
            ),
        ]

    def __str__(self):
        return f'View of {self.post.title} by {self.user or self.ip_address}'

class Event(models.Model):
    """
    Model for association events with improved functionality.
    """
    STATUS_CHOICES = [
        ('upcoming', _('Upcoming')),
        ('ongoing', _('Ongoing')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
    ]
    
    title = models.CharField(max_length=255, verbose_name=_('Event Title'))
    description = models.TextField(verbose_name=_('Description'))
    date = models.DateTimeField(verbose_name=_('Event Date & Time'))
    end_date = models.DateTimeField(null=True, blank=True, verbose_name=_('End Date & Time'))
    location = models.CharField(max_length=255, verbose_name=_('Location'))
    image = models.ImageField(upload_to='media/events/', blank=True, null=True, verbose_name=_('Event Image'))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='upcoming', db_index=True, verbose_name=_('Status'))
    max_participants = models.PositiveIntegerField(null=True, blank=True, verbose_name=_('Max Participants'))
    min_age = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_('Minimum Age'))
    max_age = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_('Maximum Age'))
    registration_deadline = models.DateTimeField(null=True, blank=True, verbose_name=_('Registration Deadline'))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_events', verbose_name=_('Created by'))
    created_at = models.DateTimeField(auto_now_add=True, null=True, verbose_name=_('Created at'))
    updated_at = models.DateTimeField(auto_now=True, null=True, verbose_name=_('Updated at'))
    
    class Meta:
        ordering = ['date']
        verbose_name = _('Event')
        verbose_name_plural = _('Events')
        indexes = [
            models.Index(fields=['date', 'status']),
        ]
        
    def __str__(self):
        return self.title

    def get_absolute_url(self):
        """Canonical URL for this event."""
        from django.urls import reverse
        return reverse('blog:event_detail', kwargs={'pk': self.pk})

    @property
    def is_registration_open(self):
        """Check if registration is still open"""
        from django.utils import timezone
        if self.registration_deadline:
            return timezone.now() < self.registration_deadline
        return self.status == 'upcoming'
    
    def _get_confirmed_count(self):
        """Return confirmed registrations count, cached on the instance for request lifetime."""
        if not hasattr(self, '_confirmed_reg_count'):
            self._confirmed_reg_count = self.registrations.filter(status='confirmed').count()
        return self._confirmed_reg_count

    @property
    def is_full(self):
        """Check if event is at capacity"""
        if self.max_participants:
            return self._get_confirmed_count() >= self.max_participants
        return False

    @property
    def available_spots(self):
        """Get number of available spots"""
        if self.max_participants:
            return max(0, self.max_participants - self._get_confirmed_count())
        return None

    @property
    def has_age_restriction(self):
        return self.min_age is not None or self.max_age is not None

    @property
    def is_teen_event(self):
        return self.min_age is not None and self.max_age is not None and self.max_age <= 18


class EventRegistration(models.Model):
    """
    Event registration tracking.
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('confirmed', _('Confirmed')),
        ('cancelled', _('Cancelled')),
        ('attended', _('Attended')),
    ]
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations', verbose_name=_('Event'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='event_registrations', verbose_name=_('User'))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='confirmed', verbose_name=_('Status'))
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Registered at'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    
    class Meta:
        unique_together = ('event', 'user')
        verbose_name = _('Event Registration')
        verbose_name_plural = _('Event Registrations')
        ordering = ['-registered_at']
    
    def __str__(self):
        return f'{self.user.username} - {self.event.title}'


class BlogSubscription(models.Model):
    """
    User blog subscriptions. Track which users are subscribed to receive notifications
    when new posts are published by specific authors.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_subscriptions', verbose_name=_('Subscriber'))
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscribers', verbose_name=_('Author'))
    subscribed_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Subscription date'))

    class Meta:
        unique_together = ('user', 'author')
        verbose_name = _('Blog Subscription')
        verbose_name_plural = _('Blog Subscriptions')
        ordering = ['-subscribed_at']

    def __str__(self):
        return f'{self.user.username} subscribed to {self.author.username}'

