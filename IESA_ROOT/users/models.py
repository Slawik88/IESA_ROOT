from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
import uuid
import secrets
import pyotp
import base64
from django.utils.translation import gettext_lazy as _


def _validate_avatar_size(file):
    """Лимит размера аватара 5 MB (B1-13)."""
    limit = 5 * 1024 * 1024
    if file.size > limit:
        raise ValidationError(_('Avatar file size must not exceed 5 MB.'))


class UserQuerySet(models.QuerySet):
    """Custom queryset for User with a reusable search() method.

    Eliminates duplicate Q-object patterns scattered across views.
    Usage::

        User.objects.search("john doe")
    """

    def search(self, query):
        """Case-insensitive search across username, name, email and pseudonym.

        Supports single-word and two-word (first + last name) queries.
        Returns an empty queryset for blank/None input.
        """
        if not query or not query.strip():
            return self.none()
        normalized = query.strip()
        qs = self.filter(
            Q(username__icontains=normalized) |
            Q(first_name__icontains=normalized) |
            Q(last_name__icontains=normalized) |
            Q(email__icontains=normalized) |
            Q(pseudonym__icontains=normalized) |
            Q(permanent_id__icontains=normalized)
        )
        # Support "Firstname Lastname" two-word queries
        parts = normalized.split()
        if len(parts) == 2:
            t1, t2 = parts
            qs = (qs | self.filter(
                Q(first_name__icontains=t1, last_name__icontains=t2) |
                Q(first_name__icontains=t2, last_name__icontains=t1)
            ))
        return qs.distinct()


class UserManager(DjangoUserManager):
    """Preserve all built-in auth manager functionality while adding UserQuerySet."""

    def get_queryset(self):
        return UserQuerySet(self.model, using=self._db)

    def search(self, query):
        """Shortcut: User.objects.search(query) → UserQuerySet.search(query)."""
        return self.get_queryset().search(query)


class User(AbstractUser):
    """
    Custom user model with additional fields.
    """
    avatar = models.ImageField(
        upload_to='avatars/',
        default='avatars/default.png',
        blank=True,
        validators=[_validate_avatar_size],
        verbose_name=_('Avatar')
    )
    date_of_birth = models.DateField(
        null=True, 
        blank=True, 
        verbose_name=_('Date of Birth')
    )
    
    # Phone number with privacy option
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_('Phone Number')
    )
    is_phone_hidden = models.BooleanField(
        default=True,
        verbose_name=_('Hide Phone Number'),
        help_text=_('If checked, only admins can see your phone number')
    )
    
    last_online = models.DateTimeField(
        default=timezone.now, 
        verbose_name=_('Last Online')
    )
    is_verified = models.BooleanField(
        default=False, 
        verbose_name=_('Verified User')
    )
    is_partner = models.BooleanField(
        default=False,
        verbose_name=_('Partner Status'),
        help_text=_('Grant partner portal access without displaying on homepage. '
                    'Partner can log member visits via the partner portal.')
    )

    # Permanent card identifier (immutable). Used for QR cards and stable linking.
    permanent_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name=_('Permanent ID'))
    # Indicates whether the physical card is currently active/issued
    card_active = models.BooleanField(default=False, verbose_name=_('Card active'))
    card_issued_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Card issued at'))

    # MEMBERSHIP VERIFICATION SYSTEM
    membership_status = models.CharField(
        max_length=20,
        choices=[('active', _('Active')), ('inactive', _('Inactive'))],
        default='inactive',
        verbose_name=_('Membership Status')
    )
    totp_secret = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_('TOTP Secret'),
        help_text=_('Base32-encoded secret for PIN generation')
    )

    # Brute-force PIN protection
    failed_pin_attempts = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_('Failed PIN Attempts')
    )
    pin_lockout_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('PIN Lockout Until')
    )

    pseudonym = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Pseudonym')
    )

    # Telegram integration
    telegram_chat_id = models.BigIntegerField(
        null=True, blank=True, unique=True,
        verbose_name=_('Telegram Chat ID'),
        help_text=_('Linked Telegram chat id (set automatically when user connects via bot or widget)'),
    )
    telegram_linked_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_('Telegram Linked At'),
    )

    # Social / contact links (optional)
    github_url = models.URLField(blank=True, max_length=255, verbose_name=_('GitHub'))
    discord_url = models.URLField(blank=True, max_length=255, verbose_name=_('Discord'))
    telegram_url = models.URLField(blank=True, max_length=255, verbose_name=_('Telegram'))
    website_url = models.URLField(blank=True, max_length=255, verbose_name=_('Website'))
    other_links = models.TextField(blank=True, verbose_name=_('Other links (one per line)'))
    # Statistics (computed but stored for performance)
    total_posts = models.PositiveIntegerField(default=0, verbose_name=_('Total Posts Published'))
    total_likes_received = models.PositiveIntegerField(default=0, verbose_name=_('Total Likes Received'))
    total_comments_made = models.PositiveIntegerField(default=0, verbose_name=_('Total Comments Made'))
    
    # Activity points for gamification
    activity_points = models.PositiveIntegerField(default=0, verbose_name=_('Activity Points'))

    # Custom manager with search() support
    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        # FIX: Add indexes for fields used in searches and filters
        # This improves query performance dramatically for high-traffic operations
        indexes = [
            models.Index(fields=['username'], name='user_username_idx'),
            models.Index(fields=['email'], name='user_email_idx'),
            models.Index(fields=['permanent_id'], name='user_permanent_id_idx'),
            models.Index(fields=['is_verified', 'username'], name='user_verified_username_idx'),
            models.Index(fields=['membership_status'], name='user_membership_idx'),
            models.Index(fields=['pseudonym'], name='user_pseudonym_idx'),
        ]

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
        """Update cached statistics from database using single aggregation query.
        
        FIX: Was doing 3 separate count queries (N+1 problem).
        Now uses single aggregate() call for efficiency.
        """
        from blog.models import Post, Like, Comment
        from django.db.models import Count, Q
        
        # OPTIMIZATION: Single aggregate query instead of 3 separate count() queries
        # This replaces 3 database queries with 1 aggregate query
        stats = Post.objects.filter(
            author=self, status='published'
        ).aggregate(
            post_count=Count('id'),
            likes_count=Count('likes'),
            comments_count=Count('comments')
        )

        # Also fetch comments made by user (separate aggregate)
        comment_stats = Comment.objects.filter(
            author=self
        ).aggregate(total=Count('id'))
        
        self.total_posts = stats['post_count']
        self.total_likes_received = stats['likes_count']
        self.total_comments_made = comment_stats['total']
        self.activity_points = self.calculate_activity_points()
        
        # Batch update only changed fields
        self.save(update_fields=[
            'total_posts', 'total_likes_received', 
            'total_comments_made', 'activity_points'
        ])
    
    def get_age(self):
        """Calculate user's age from date_of_birth"""
        if not self.date_of_birth:
            return None
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
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
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate TOTP secret if not set"""
        if not self.totp_secret:
            # Generate 20 random bytes and encode as base32 for TOTP
            random_bytes = secrets.token_bytes(20)
            self.totp_secret = base64.b32encode(random_bytes).decode('utf-8')
        super().save(*args, **kwargs)
    
    def get_current_pin(self):
        """Generate current 6-digit PIN using TOTP (12-minute refresh interval)"""
        if not self.totp_secret:
            return None
        totp = pyotp.TOTP(self.totp_secret, interval=720)  # 720 seconds = 12 minutes
        return totp.now()
    
    def verify_pin(self, pin, valid_window=1):
        """
        Verify provided PIN against TOTP secret.
        valid_window=1 means accept previous/current/next interval (36 min total).
        """
        if not self.totp_secret or not pin:
            return False
        totp = pyotp.TOTP(self.totp_secret, interval=720)
        return totp.verify(pin, valid_window=valid_window)

    def get_avatar_url(self):
        """Return the avatar URL safely, or None if unavailable.

        Use this instead of accessing user.avatar.url directly to avoid
        ValueError when the underlying file is missing from storage.
        """
        try:
            if self.avatar:
                return self.avatar.url
        except Exception:
            pass
        return None

    def get_absolute_url(self):
        """Canonical URL to this user's public profile (scan-card page)."""
        from django.urls import reverse
        return reverse('users:public_profile', kwargs={'uuid': str(self.permanent_id)})

    def get_post_counts(self):
        """Return aggregate post counts grouped by status.

        Example::

            counts = user.get_post_counts()
            # {'pending': 2, 'published': 10, 'rejected': 0, 'draft': 1}
        """
        from blog.models import Post
        from django.db.models import Count, Q
        return Post.objects.filter(author=self).aggregate(
            pending=Count('id', filter=Q(status='pending')),
            published=Count('id', filter=Q(status='published')),
            rejected=Count('id', filter=Q(status='rejected')),
            draft=Count('id', filter=Q(status='draft')),
        )

    def get_pin_remaining_seconds(self):
        """Seconds remaining until the current TOTP PIN expires (720 s interval)."""
        import time
        interval = 720
        return interval - (int(time.time()) % interval)


class Partner(models.Model):
    """
    Partner model for businesses/services that log member visits.
    OneToOne with User - partner users are in 'Partners' group.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='partner_profile',
        verbose_name=_('User Account')
    )
    company_name = models.CharField(
        max_length=255,
        verbose_name=_('Company Name')
    )
    business_type = models.CharField(
        max_length=100,
        choices=[
            ('shop', _('Shop/Retail')),
            ('service', _('Service Provider')),
            ('gym', _('Gym/Fitness')),
            ('restaurant', _('Restaurant/Cafe')),
            ('other', _('Other')),
        ],
        default='other',
        verbose_name=_('Business Type')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    
    class Meta:
        verbose_name = _('Partner')
        verbose_name_plural = _('Partners')
        db_table = 'users_partner'
        ordering = ['company_name']
        indexes = [
            models.Index(fields=['company_name'], name='partner_company_idx'),
            models.Index(fields=['business_type'], name='partner_business_idx'),
        ]
    
    def __str__(self):
        return f"{self.company_name} ({self.user.username})"
    
    def get_total_visits(self):
        """Get total number of visits logged by this partner"""
        return self.logged_visits.count()


class Visit(models.Model):
    """
    Visit log model - records when a member visits a partner.
    Stores service details and PIN verification status.
    """
    member = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='visits',
        verbose_name=_('Member')
    )
    partner = models.ForeignKey(
        Partner,
        on_delete=models.CASCADE,
        related_name='logged_visits',
        verbose_name=_('Partner')
    )
    service_type = models.CharField(
        max_length=100,
        choices=[
            ('purchase', _('Purchase')),
            ('consultation', _('Consultation')),
            ('training', _('Training Session')),
            ('event', _('Event Attendance')),
            ('other', _('Other')),
        ],
        default='other',
        verbose_name=_('Service Type')
    )
    service_description = models.TextField(
        blank=True,
        verbose_name=_('Service Description')
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Cost')
    )
    comments = models.TextField(
        blank=True,
        verbose_name=_('Comments')
    )
    pin_verified = models.BooleanField(
        default=False,
        verbose_name=_('PIN Verified')
    )
    status = models.CharField(
        max_length=10,
        choices=[
            ('ACTIVE', _('Active')),
            ('EDITED', _('Edited')),
            ('CANCELLED', _('Cancelled')),
        ],
        default='ACTIVE',
        verbose_name=_('Status')
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Visit Time')
    )
    
    class Meta:
        verbose_name = _('Visit')
        verbose_name_plural = _('Visits')
        db_table = 'users_visit'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp'], name='visit_timestamp_idx'),
            models.Index(fields=['partner', '-timestamp'], name='visit_partner_time_idx'),
            models.Index(fields=['member', '-timestamp'], name='visit_member_time_idx'),
            models.Index(fields=['pin_verified'], name='visit_verified_idx'),
        ]
        constraints = [
            # Гарантируем целостность статуса на уровне БД (B1-12)
            models.CheckConstraint(
                check=Q(status__in=['ACTIVE', 'EDITED', 'CANCELLED']),
                name='valid_visit_status',
            ),
        ]
    
    def __str__(self):
        status = "✓" if self.pin_verified else "✗"
        return f"{status} {self.member.username} @ {self.partner.company_name} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"


class VisitAudit(models.Model):
    """
    Audit trail for visit edits and cancellations.
    Created each time a partner edits or cancels a Visit within the 20-minute window.
    """
    ACTION_EDIT = 'EDIT'
    ACTION_CANCEL = 'CANCEL'
    ACTION_CHOICES = [
        (ACTION_EDIT, _('Edit')),
        (ACTION_CANCEL, _('Cancel')),
    ]

    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name='audits',
        verbose_name=_('Visit')
    )
    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES,
        verbose_name=_('Action')
    )
    previous_service_type = models.CharField(max_length=100, blank=True, verbose_name=_('Previous Service Type'))
    previous_service_description = models.TextField(blank=True, verbose_name=_('Previous Description'))
    previous_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_('Previous Cost'))
    previous_comments = models.TextField(blank=True, verbose_name=_('Previous Comments'))
    reason = models.TextField(verbose_name=_('Reason'))
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Changed At'))
    changed_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='visit_audits',
        verbose_name=_('Changed By')
    )

    class Meta:
        verbose_name = _('Visit Audit')
        verbose_name_plural = _('Visit Audits')
        db_table = 'users_visitaudit'
        ordering = ['-changed_at']
        indexes = [
            # Ускоряет выборку истории по конкретному визиту (B1-16)
            models.Index(fields=['visit', '-changed_at'], name='audit_visit_time_idx'),
        ]

    def __str__(self):
        return f"{self.action} visit #{self.visit_id} by {self.changed_by} at {self.changed_at.strftime('%Y-%m-%d %H:%M')}"
