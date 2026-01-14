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
    # Indicates if user has physical card (admin marks this)
    has_physical_card = models.BooleanField(default=False, verbose_name=_('Has physical card'))

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
    
    # Activity points for gamification
    activity_points = models.PositiveIntegerField(default=0, verbose_name='Activity Points')

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.username
    
    def calculate_activity_points(self):
        """Calculate total activity points based on user actions"""
        points = 0
        points += self.total_posts * 10  # 10 points per post
        points += self.total_likes_received * 2  # 2 points per like received
        points += self.total_comments_made * 1  # 1 point per comment
        return points
    
    def update_statistics(self):
        """Update cached statistics from database"""
        from blog.models import Post, Like, Comment
        
        self.total_posts = Post.objects.filter(author=self, status='published').count()
        self.total_likes_received = Like.objects.filter(post__author=self).count()
        self.total_comments_made = Comment.objects.filter(author=self).count()
        self.activity_points = self.calculate_activity_points()
        self.save(update_fields=['total_posts', 'total_likes_received', 'total_comments_made', 'activity_points'])
    
    def get_achievement_level(self):
        """Return achievement level based on activity points"""
        score = self.activity_points
        
        if score >= 1000:
            return {'level': 'Legend', 'color': 'gold', 'next_level': None, 'progress': 100}
        elif score >= 500:
            return {'level': 'Expert', 'color': 'purple', 'next_level': 'Legend', 'progress': int((score - 500) / 500 * 100)}
        elif score >= 200:
            return {'level': 'Advanced', 'color': 'blue', 'next_level': 'Expert', 'progress': int((score - 200) / 300 * 100)}
        elif score >= 50:
            return {'level': 'Intermediate', 'color': 'green', 'next_level': 'Advanced', 'progress': int((score - 50) / 150 * 100)}
        else:
            return {'level': 'Beginner', 'color': 'gray', 'next_level': 'Intermediate', 'progress': int(score / 50 * 100)}
