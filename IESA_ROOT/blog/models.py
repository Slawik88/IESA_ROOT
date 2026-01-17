from django.db import models
from django.conf import settings
from django.urls import reverse

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
        ('draft', 'Черновик'),
        ('pending', 'На модерации'),
        ('published', 'Опубликован'),
        ('rejected', 'Отклонен'),
    ]
    
    title = models.CharField(max_length=255, verbose_name='Заголовок')
    # Use a RichTextField with extended config when ckeditor is installed; otherwise a normal TextField
    text = RichTextField(config_name='extends', verbose_name='Текст поста')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_posts', verbose_name='Автор')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    preview_image = models.ImageField(upload_to='media/blog/previews/', blank=True, null=True, verbose_name='Изображение превью')
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    views_count = models.PositiveIntegerField(default=0, verbose_name='Просмотры')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Пост'
        verbose_name_plural = 'Посты'
        
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
        
        # If not enough, fill with random published posts from other authors
        if same_author.count() < limit:
            remaining = limit - same_author.count()
            other_posts = Post.objects.filter(
                status='published'
            ).exclude(
                Q(pk=self.pk) | Q(author=self.author)
            ).order_by('-views_count', '-created_at')[:remaining]
            return list(same_author) + list(other_posts)
        
        return list(same_author)

class Comment(models.Model):
    """
    Комментарии под постом с поддержкой ответов (replies).
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments', verbose_name='Post')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments_authored', verbose_name='Author')
    text = models.TextField(verbose_name='Comment text')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creation date')
    
    # Self-referential FK для replies
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies', verbose_name='Parent comment')
    
    class Meta:
        ordering = ['created_at']
        verbose_name = 'Comment'
        verbose_name_plural = 'Comments'
        
    def __str__(self):
        return f'Comment from {self.author.username} to {self.post.title[:20]}...'


class CommentLike(models.Model):
    """
    Лайки для комментариев.
    """
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes', verbose_name='Comment')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='User')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user')
        verbose_name = 'Comment Like'
        verbose_name_plural = 'Comment Likes'

    def __str__(self):
        return f'Like from {self.user.username} to comment {self.comment.pk}'

class Like(models.Model):
    """
    Модель для отслеживания лайков. Используем отдельную модель для простоты HTMX.
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes', verbose_name='Post')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='User')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Уникальность: один лайк от пользователя на один пост
        unique_together = ('post', 'user')
        verbose_name = 'Like'
        verbose_name_plural = 'Likes'
        
    def __str__(self):
        return f'Like from {self.user.username} to {self.post.title[:20]}...'


class PostView(models.Model):
    """
    Track unique views per user to prevent counting multiple views from same user.
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='user_views', verbose_name='Post')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, verbose_name='User')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP Address')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='View date')

    class Meta:
        unique_together = (('post', 'user'), ('post', 'ip_address'))
        verbose_name = 'Post View'
        verbose_name_plural = 'Post Views'

    def __str__(self):
        return f'View of {self.post.title} by {self.user or self.ip_address}'

class Event(models.Model):
    """
    Model for association events with improved functionality.
    """
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    title = models.CharField(max_length=255, verbose_name='Event Title')
    description = models.TextField(verbose_name='Description')
    date = models.DateTimeField(verbose_name='Event Date & Time')
    end_date = models.DateTimeField(null=True, blank=True, verbose_name='End Date & Time')
    location = models.CharField(max_length=255, verbose_name='Location')
    image = models.ImageField(upload_to='media/events/', blank=True, null=True, verbose_name='Event Image')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='upcoming', verbose_name='Status')
    max_participants = models.PositiveIntegerField(null=True, blank=True, verbose_name='Max Participants')
    registration_deadline = models.DateTimeField(null=True, blank=True, verbose_name='Registration Deadline')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_events', verbose_name='Created by')
    created_at = models.DateTimeField(auto_now_add=True, null=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, null=True, verbose_name='Updated at')
    
    class Meta:
        ordering = ['date']
        verbose_name = 'Event'
        verbose_name_plural = 'Events'
        indexes = [
            models.Index(fields=['date', 'status']),
        ]
        
    def __str__(self):
        return self.title
    
    @property
    def is_registration_open(self):
        """Check if registration is still open"""
        from django.utils import timezone
        if self.registration_deadline:
            return timezone.now() < self.registration_deadline
        return self.status == 'upcoming'
    
    @property
    def is_full(self):
        """Check if event is at capacity"""
        if self.max_participants:
            return self.registrations.filter(status='confirmed').count() >= self.max_participants
        return False
    
    @property
    def available_spots(self):
        """Get number of available spots"""
        if self.max_participants:
            confirmed = self.registrations.filter(status='confirmed').count()
            return max(0, self.max_participants - confirmed)
        return None


class EventRegistration(models.Model):
    """
    Event registration tracking.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('attended', 'Attended'),
    ]
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations', verbose_name='Event')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='event_registrations', verbose_name='User')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='confirmed', verbose_name='Status')
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name='Registered at')
    notes = models.TextField(blank=True, verbose_name='Notes')
    
    class Meta:
        unique_together = ('event', 'user')
        verbose_name = 'Event Registration'
        verbose_name_plural = 'Event Registrations'
        ordering = ['-registered_at']
    
    def __str__(self):
        return f'{self.user.username} - {self.event.title}'


class BlogSubscription(models.Model):
    """
    User blog subscriptions. Track which users are subscribed to receive notifications
    when new posts are published by specific authors.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_subscriptions', verbose_name='Subscriber')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscribers', verbose_name='Author')
    subscribed_at = models.DateTimeField(auto_now_add=True, verbose_name='Subscription date')

    class Meta:
        unique_together = ('user', 'author')
        verbose_name = 'Blog Subscription'
        verbose_name_plural = 'Blog Subscriptions'
        ordering = ['-subscribed_at']

    def __str__(self):
        return f'{self.user.username} subscribed to {self.author.username}'

