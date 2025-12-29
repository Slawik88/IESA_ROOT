from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    """
    Custom user model with additional fields.
    """
    avatar = models.ImageField(
        upload_to='avatars/', 
        default='avatars/default.png', 
        blank=True, 
        verbose_name='Avatar'
    )
    date_of_birth = models.DateField(
        null=True, 
        blank=True, 
        verbose_name='Date of Birth'
    )
    last_online = models.DateTimeField(
        default=timezone.now, 
        verbose_name='Last Online'
    )
    is_verified = models.BooleanField(
        default=False, 
        verbose_name='Verified User'
    )

    # Permanent card identifier (immutable). Used for QR cards and stable linking.
    permanent_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name=_('Permanent ID'))
    # Indicates whether the physical card is currently active/issued
    card_active = models.BooleanField(default=False, verbose_name=_('Card active'))
    card_issued_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Card issued at'))

    # Social / contact links (optional)
    github_url = models.URLField(blank=True, max_length=255, verbose_name='GitHub')
    discord_url = models.URLField(blank=True, max_length=255, verbose_name='Discord')
    telegram_url = models.URLField(blank=True, max_length=255, verbose_name='Telegram')
    website_url = models.URLField(blank=True, max_length=255, verbose_name='Website')
    other_links = models.TextField(blank=True, verbose_name='Other links (one per line)')
    # Statistics (computed but stored for performance)
    total_posts = models.PositiveIntegerField(default=0, verbose_name='Total Posts Published')
    total_likes_received = models.PositiveIntegerField(default=0, verbose_name='Total Likes Received')
    total_comments_made = models.PositiveIntegerField(default=0, verbose_name='Total Comments Made')

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.username
    
    def update_statistics(self):
        """Update cached statistics from database"""
        from blog.models import Post, Like, Comment
        
        self.total_posts = Post.objects.filter(author=self, status='published').count()
        self.total_likes_received = Like.objects.filter(post__author=self).count()
        self.total_comments_made = Comment.objects.filter(author=self).count()
        self.save(update_fields=['total_posts', 'total_likes_received', 'total_comments_made'])
    
    def get_achievement_level(self):
        """Return achievement level based on activity"""
        score = (self.total_posts * 10) + (self.total_likes_received * 2) + (self.total_comments_made * 1)
        
        if score >= 1000:
            return 'Legend'
        elif score >= 500:
            return 'Expert'
        elif score >= 200:
            return 'Advanced'
        elif score >= 50:
            return 'Intermediate'
        else:
            return 'Beginner'
