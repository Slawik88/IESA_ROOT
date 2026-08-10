from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.db.models.functions import Lower
import uuid
import secrets
import pyotp
import base64
from django.utils.translation import gettext_lazy as _


def _validate_avatar_size(file):
    """Лимит размера аватара 5 MB (B1-13).
    Игнорируем ошибку если файл не найден в S3 (default.png может отсутствовать)."""
    limit = 5 * 1024 * 1024
    try:
        size = file.size
    except (FileNotFoundError, OSError, Exception):
        return  # файл не существует в хранилище — пропускаем валидацию
    if size > limit:
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

    # Ownership of the current e-mail address.  This is deliberately separate
    # from ``is_verified`` which represents the association/member verification
    # performed by administrators.
    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('E-mail verified at'),
    )
    email_verification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('E-mail verification sent at'),
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
    # BLOCK 10 (audit v4): новая роль «Президент ассоциации»
    is_president = models.BooleanField(
        default=False,
        verbose_name=_('President of Association'),
        help_text=_('Marks user as president of the association. Displayed with a crown badge.')
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
        default='active',
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

    # Onboarding flag — False пока пользователь не закрыл welcome-modal (Block 1a)
    onboarded = models.BooleanField(
        default=False,
        verbose_name=_('Onboarded'),
        help_text=_('True после того как пользователь прошёл welcome-modal'),
    )

    # Interactive tours completion state (Tour system 2026-05-27)
    # JSON: {"user": true, "partner": false, "president": false}
    tours_completed = models.JSONField(
        default=dict, blank=True,
        verbose_name=_('Tours Completed'),
        help_text=_('Tracks which interactive tours user has finished'),
    )

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
        constraints = [
            # Existing accounts are migrated as unverified, so this can be
            # introduced safely even if historical e-mail duplicates exist.
            # From now on only one account may prove ownership of an address.
            models.UniqueConstraint(
                Lower('email'),
                condition=Q(email_verified_at__isnull=False),
                name='unique_verified_user_email_ci',
            ),
        ]

    def __str__(self):
        return self.username

    @property
    def is_email_verified(self):
        """Whether the user proved ownership of their current e-mail address."""
        return bool(self.email and self.email_verified_at)
    
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

    @property
    def profile_completeness(self) -> dict:
        """
        Возвращает процент заполнения профиля и список незаполненных шагов.
        Используется в Block 1b — progress-bar онбординга.
        """
        steps = [
            {
                'key': 'avatar',
                'done': bool(self.avatar and self.avatar.name != 'avatars/default.png'),
                'label': _('Add a profile photo'),
                'url': 'users:profile_edit',
                'icon': 'fas fa-camera',
            },
            {
                'key': 'name',
                'done': bool(self.first_name and self.last_name),
                'label': _('Add your full name'),
                'url': 'users:profile_edit',
                'icon': 'fas fa-user',
            },
            {
                'key': 'phone',
                'done': bool(self.phone_number),
                'label': _('Add a phone number'),
                'url': 'users:profile_edit',
                'icon': 'fas fa-phone',
            },
            {
                'key': 'telegram',
                'done': bool(self.telegram_chat_id),
                'label': _('Connect Telegram for instant notifications'),
                'url': 'users:connect_telegram_code',
                'icon': 'fab fa-telegram',
            },
            {
                'key': 'dob',
                'done': bool(self.date_of_birth),
                'label': _('Add your date of birth'),
                'url': 'users:profile_edit',
                'icon': 'fas fa-birthday-cake',
            },
        ]
        done_count = sum(1 for s in steps if s['done'])
        pct = int(done_count / len(steps) * 100)
        return {
            'percent': pct,
            'done': done_count,
            'total': len(steps),
            'steps': steps,
            'incomplete': [s for s in steps if not s['done']],
            'is_complete': pct == 100,
        }


class Partner(models.Model):
    """
    Partner model for businesses/services that log member visits.
    OneToOne with User - partner users are in 'Partners' group.

    partner_type определяет роль внутри B2B-системы:
      - 'partner'           — внешний партнёр (магазин, спортзал и т.д.)
      - 'association_staff' — сотрудник ассоциации (юрист, бухгалтер и т.д.)
                              НЕ получает is_staff=True, но имеет доступ к своему кабинету.
    """

    PARTNER_TYPE_CHOICES = [
        ('partner',           _('External Partner')),
        ('association_staff', _('Association Staff')),
    ]

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
    partner_type = models.CharField(
        max_length=50,
        choices=PARTNER_TYPE_CHOICES,
        default='partner',
        verbose_name=_('Partner Type'),
        help_text=_(
            'External Partner — внешний бизнес; '
            'Association Staff — сотрудник ассоциации (юрист, бухгалтер). '
            'Сотрудники НЕ получают is_staff=True.'
        )
    )
    # 10d: Map fields
    address_full = models.CharField(
        max_length=512, blank=True, default='',
        verbose_name=_('Full Address'),
        help_text=_('Street, city, country — shown on map')
    )
    lat = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name=_('Latitude'),
    )
    lon = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name=_('Longitude'),
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


# ---------------------------------------------------------------------------
# Система инвайт-ссылок (Задача 2)
# ---------------------------------------------------------------------------

class InviteToken(models.Model):
    """
    Защищённая одноразовая ссылка для регистрации партнёра или сотрудника ассоциации.

    Логика:
      - Создаётся администратором (is_staff=True) вручную через кабинет.
      - По ссылке открывается форма регистрации с предзаполненным типом партнёра.
      - После регистрации: User.is_partner=True, создаётся запись Partner с нужным partner_type.
      - Обычный пользователь НЕ может самостоятельно стать партнёром или сотрудником.
    """

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=_('Token')
    )
    partner_type = models.CharField(
        max_length=50,
        choices=Partner.PARTNER_TYPE_CHOICES,
        default='partner',
        verbose_name=_('Partner Type'),
        help_text=_('Роль, которую получит зарегистрировавшийся по этой ссылке.')
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Pre-filled Company Name'),
        help_text=_('Необязательно. Предзаполнит поле "Компания" в форме регистрации.')
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Internal Note'),
        help_text=_('Внутренняя заметка (например: "Инвайт для FitnessPro Geneva").')
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_invites',
        verbose_name=_('Created By')
    )
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='used_invite',
        verbose_name=_('Used By')
    )
    used_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_('Used At')
    )
    expires_at = models.DateTimeField(
        verbose_name=_('Expires At')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active')
    )
    max_uses = models.PositiveSmallIntegerField(
        default=1,
        verbose_name=_('Max Uses'),
        help_text=_('Сколько раз можно использовать ссылку. Обычно 1.')
    )
    use_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_('Use Count')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )

    class Meta:
        verbose_name = _('Invite Token')
        verbose_name_plural = _('Invite Tokens')
        db_table = 'users_invitetoken'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token'], name='invite_token_idx'),
            models.Index(fields=['is_active', 'expires_at'], name='invite_active_exp_idx'),
        ]

    def __str__(self):
        return f"Invite [{self.get_partner_type_display()}] by {self.created_by} — {'active' if self.is_valid() else 'used/expired'}"

    def is_valid(self) -> bool:
        """Ссылка действительна: активна, не просрочена и не исчерпана."""
        return (
            self.is_active
            and self.use_count < self.max_uses
            and timezone.now() < self.expires_at
        )

    def mark_used(self, user: User):
        """Отмечает инвайт как использованный данным пользователем."""
        self.used_by = user
        self.used_at = timezone.now()
        self.use_count += 1
        if self.use_count >= self.max_uses:
            self.is_active = False
        self.save(update_fields=['used_by', 'used_at', 'use_count', 'is_active'])


# ---------------------------------------------------------------------------
# Заявки на смену типа аккаунта (Часть 1, Задача 1)
# ---------------------------------------------------------------------------

class AccountChangeRequest(models.Model):
    """
    Заявка пользователя на повышение/смену типа аккаунта.

    Процесс:
      1. Пользователь заполняет форму → заявка со статусом 'pending'.
      2. Суперюзер видит заявку в Django Admin (с контактами),
         связывается с пользователем и принимает решение вручную.
      3. Смена роли происходит ТОЛЬКО вручную в Admin — модель НЕ меняет роль автоматически.
    """

    DESIRED_TYPE_CHOICES = [
        ('partner',           _('External Partner')),
        ('association_staff', _('Association Staff (IESA)')),
        # BLOCK 7 (audit v4): новая категория «Президент ассоциации»
        ('president',         _('President of Association')),
    ]

    BUSINESS_CATEGORY_CHOICES = [
        # Спорт и фитнес
        ('gym',              _('Gym / Fitness Center')),
        ('martial_arts',     _('Martial Arts School')),
        ('yoga_pilates',     _('Yoga / Pilates Studio')),
        ('swimming',         _('Swimming Pool / Aquatics')),
        ('sports_club',      _('Sports Club / Team')),
        ('personal_trainer', _('Personal Trainer / Coach')),
        ('crossfit',         _('CrossFit / Functional Training')),
        ('cycling',          _('Cycling / Indoor Cycling')),
        ('dance',            _('Dance School')),
        ('climbing',         _('Climbing / Boulder')),
        # Здоровье и велнес
        ('physiotherapy',    _('Physiotherapy / Rehabilitation')),
        ('massage_spa',      _('Massage / SPA / Wellness')),
        ('nutrition',        _('Nutrition / Dietology')),
        ('medical',          _('Medical / Healthcare')),
        ('psychology',       _('Psychology / Mental Health')),
        ('chiropractic',     _('Chiropractic / Manual Therapy')),
        # Ритейл и оборудование
        ('sports_shop',      _('Sports Equipment Shop')),
        ('clothing',         _('Sports Clothing / Gear')),
        ('supplement',       _('Sports Supplements / Nutrition Products')),
        ('bike_shop',        _('Bike Shop / Service')),
        # HOTFIX 2026-05-23: Insurance & Financial (отсутствовали — фидбэк юзера)
        ('insurance_agent',   _('Insurance Agent / Broker')),
        ('bank',              _('Bank / Banking Services')),
        ('financial_advisor', _('Financial Advisor')),
        # Профессиональные услуги (сотрудники ассоциации)
        ('lawyer',           _('Legal Services / Lawyer')),
        ('accountant',       _('Accounting / Finance')),
        ('consulting',       _('Business Consulting')),
        ('marketing',        _('Marketing / PR / Design')),
        ('hr',               _('HR / Recruitment')),
        ('it',               _('IT / Technology / Software')),
        # Образование и события
        ('coach_trainer',    _('Professional Coaching')),
        ('school',           _('School / Educational Center')),
        ('event_org',        _('Event Organization')),
        ('seminar',          _('Seminar / Workshop Host')),
        # Туризм и активный отдых
        ('travel',           _('Travel / Tourism / Adventure')),
        ('outdoor',          _('Outdoor Activities / Hiking')),
        ('water_sports',     _('Water Sports / Diving / Surfing')),
        ('winter_sports',    _('Winter Sports / Ski')),
        # Питание и гостеприимство
        ('restaurant',       _('Restaurant / Cafe / Bar')),
        ('healthy_food',     _('Healthy Food / Catering')),
        ('hotel',            _('Hotel / Accommodation')),
        # Медиа и другое
        ('media',            _('Media / Content Creation / Photography')),
        ('esports',          _('eSports / Gaming')),
        ('other',            _('Other (describe in the form)')),
    ]

    STATUS_CHOICES = [
        ('pending',   _('Pending Review')),
        ('reviewed',  _('Reviewed')),
        ('approved',  _('Approved')),       # BLOCK 10 (audit v4): новый финальный статус
        ('rejected',  _('Rejected')),
        ('cancelled', _('Cancelled by user')),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='account_change_requests',
        verbose_name=_('User'),
    )
    desired_type = models.CharField(
        max_length=50,
        choices=DESIRED_TYPE_CHOICES,
        verbose_name=_('Desired Account Type'),
    )
    business_category = models.CharField(
        max_length=50,
        choices=BUSINESS_CATEGORY_CHOICES,
        blank=True,
        verbose_name=_('Business Category'),
        help_text=_('Most accurately describes your activity area.'),
    )
    reason = models.TextField(
        verbose_name=_('Reason / Description of Activity'),
        help_text=_('Describe why you want to change your account type and what you do.'),
    )
    # Контактные данные (могут отличаться от аккаунта)
    # BLOCK 7 (audit v4): first_name + last_name отдельно (раньше было одно contact_name)
    first_name = models.CharField(
        max_length=100, blank=True,
        verbose_name=_('First Name'),
    )
    last_name = models.CharField(
        max_length=100, blank=True,
        verbose_name=_('Last Name'),
    )
    contact_name = models.CharField(
        max_length=200, blank=True,
        verbose_name=_('Contact Name'),
        help_text=_('Deprecated: now stored as first_name + last_name. Kept for backward compatibility.'),
    )
    contact_phone = models.CharField(
        max_length=50, blank=True,
        verbose_name=_('Phone / WhatsApp'),
    )
    contact_telegram = models.CharField(
        max_length=100, blank=True,
        verbose_name=_('Telegram'),
        help_text=_('@username or phone number'),
    )
    contact_email = models.EmailField(
        blank=True,
        verbose_name=_('Contact Email'),
    )
    address = models.TextField(
        blank=True,
        verbose_name=_('Address / Location'),
        help_text=_('City, street, or region where you operate.'),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_('Status'),
    )
    admin_note = models.TextField(
        blank=True,
        verbose_name=_('Admin Note'),
        help_text=_('Internal note for the administrator (not shown to user).'),
    )
    # BLOCK 10 (audit v4): audit trail для approve/reject
    rejection_reason = models.TextField(
        blank=True,
        verbose_name=_('Rejection Reason'),
        help_text=_('Shown to user if request is rejected.'),
    )
    reviewed_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_('Reviewed At'),
    )
    reviewed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name=_('Reviewed By'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At'),
    )

    class Meta:
        verbose_name = _('Account Change Request')
        verbose_name_plural = _('Account Change Requests')
        db_table = 'users_accountchangerequest'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='acr_status_date_idx'),
            models.Index(fields=['user', 'status'],        name='acr_user_status_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.get_desired_type_display()} [{self.get_status_display()}]"

    def is_pending(self) -> bool:
        return self.status == 'pending'


# ---------------------------------------------------------------------------
# Календарь встреч (Задача: Partner Calendar / User Calendar)
# ---------------------------------------------------------------------------

class Meeting(models.Model):
    """
    Встреча/запись, созданная партнёром для участника.

    Партнёр создаёт встречу → участник видит её в своём календаре →
    оба получают уведомления в TG и на сайте.
    """

    STATUS_CHOICES = [
        ('scheduled',  _('Scheduled')),
        ('confirmed',  _('Confirmed')),
        ('cancelled',  _('Cancelled')),
        ('completed',  _('Completed')),
    ]

    partner = models.ForeignKey(
        Partner,
        on_delete=models.CASCADE,
        related_name='meetings',
        verbose_name=_('Partner'),
    )
    member = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scheduled_meetings',
        verbose_name=_('Member'),
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_('Meeting Title'),
        help_text=_('E.g. "Personal training", "Consultation", "Trial class"'),
    )
    date = models.DateField(
        null=True, blank=True,
        verbose_name=_('Date'),
        help_text=_('Leave empty if the meeting happened right now.')
    )
    start_time = models.TimeField(
        null=True, blank=True,
        verbose_name=_('Start Time')
    )
    end_time = models.TimeField(
        null=True, blank=True,
        verbose_name=_('End Time')
    )
    address = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_('Address / Location'),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('Notes'),
        help_text=_('Additional details for the member.'),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled',
        verbose_name=_('Status'),
    )
    notify_member = models.BooleanField(
        default=True,
        verbose_name=_('Notify Member'),
        help_text=_('Send TG and site notification to the member when created.'),
    )
    notification_sent = models.BooleanField(
        default=False,
        verbose_name=_('Notification Sent'),
    )
    # Долгосрочные клиенты / серии встреч
    is_recurring = models.BooleanField(
        default=False,
        verbose_name=_('Recurring Meeting'),
        help_text=_('Mark if this is part of an ongoing series (insurance, coaching, therapy...)'),
    )
    series_label = models.CharField(
        max_length=100, blank=True,
        verbose_name=_('Series / Project Label'),
        help_text=_('E.g. "Monthly review", "Rehab program Q1", "Insurance case #123"'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Meeting')
        verbose_name_plural = _('Meetings')
        db_table = 'users_meeting'
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['partner', 'date'], name='meeting_partner_date_idx'),
            models.Index(fields=['member', 'date'],  name='meeting_member_date_idx'),
            models.Index(fields=['date', 'status'],  name='meeting_date_status_idx'),
        ]

    def __str__(self):
        return f"{self.title} — {self.member.username} @ {self.date} {self.start_time}"

    @property
    def duration_minutes(self):
        from datetime import datetime, date
        if not self.start_time or not self.end_time:
            return None
        start = datetime.combine(date.today(), self.start_time)
        end   = datetime.combine(date.today(), self.end_time)
        return int((end - start).total_seconds() / 60)


class ClientNote(models.Model):
    """
    Заметки партнёра о конкретном клиенте.
    Удобно для долгосрочных отношений: страховые, коучинг, терапия, консультирование.
    Видны только партнёру — НЕ видны самому клиенту.
    """
    partner = models.ForeignKey(
        Partner,
        on_delete=models.CASCADE,
        related_name='client_notes',
        verbose_name=_('Partner'),
    )
    member = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='partner_notes',
        verbose_name=_('Member / Client'),
    )
    note = models.TextField(verbose_name=_('Note'))
    is_pinned = models.BooleanField(
        default=False,
        verbose_name=_('Pinned'),
        help_text=_('Show this note at the top'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Client Note')
        verbose_name_plural = _('Client Notes')
        db_table = 'users_clientnote'
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['partner', 'member'], name='clientnote_partner_member_idx'),
        ]

    def __str__(self):
        return f"Note: {self.partner} → {self.member} [{self.created_at.strftime('%d.%m.%Y')}]"


# ---------------------------------------------------------------------------
# Заявка на страхового агента
# ---------------------------------------------------------------------------

class InsuranceAgentRequest(models.Model):
    """
    Заявка пользователя на получение или смену страхового агента IESA.

    Процесс:
      1. Пользователь подаёт заявку через сайт или TG бот → статус 'new'.
      2. Суперюзер/менеджер видит заявку в Admin, назначает агента вручную.
      3. Статус меняется на 'assigned' / 'closed'.
    """

    STATUS_CHOICES = [
        ('new',      _('Новая')),
        ('reviewing', _('На рассмотрении')),
        ('assigned', _('Агент назначен')),
        ('closed',   _('Закрыта')),
    ]

    REQUEST_TYPE_CHOICES = [
        ('new_agent',    _('Нужен страховой агент')),
        ('change_agent', _('Смена страхового агента')),
        ('consultation', _('Консультация по страхованию')),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='insurance_requests',
        verbose_name=_('Пользователь'),
    )
    request_type = models.CharField(
        max_length=20,
        choices=REQUEST_TYPE_CHOICES,
        default='new_agent',
        verbose_name=_('Тип заявки'),
    )
    # Контактные данные (могут не совпадать с аккаунтом)
    full_name = models.CharField(max_length=200, verbose_name=_('Полное имя'))
    phone = models.CharField(max_length=50, blank=True, verbose_name=_('Телефон / WhatsApp'))
    email = models.EmailField(blank=True, verbose_name=_('Email'))
    telegram_username = models.CharField(
        max_length=100, blank=True,
        verbose_name=_('Telegram'),
        help_text=_('@username'),
    )
    city = models.CharField(max_length=100, blank=True, verbose_name=_('Город / Регион'))
    # Страховые потребности
    insurance_types = models.CharField(
        max_length=500, blank=True,
        verbose_name=_('Виды страхования'),
        help_text=_('Жизнь, здоровье, спорт, автомобиль...'),
    )
    message = models.TextField(
        blank=True,
        verbose_name=_('Дополнительная информация'),
        help_text=_('Особые пожелания, вопросы, детали ситуации'),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='new',
        verbose_name=_('Статус'),
    )
    assigned_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_insurance_requests',
        verbose_name=_('Назначенный агент'),
        limit_choices_to={'is_staff': True},
    )
    admin_note = models.TextField(blank=True, verbose_name=_('Внутренняя заметка'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Создана'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Обновлена'))

    class Meta:
        verbose_name = _('Заявка на страхового агента')
        verbose_name_plural = _('Заявки на страховых агентов')
        db_table = 'users_insuranceagentrequest'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='ins_status_date_idx'),
            models.Index(fields=['user'],                  name='ins_user_idx'),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.full_name} — {self.get_request_type_display()}"


# ---------------------------------------------------------------------------
# Настройки сайта + Уведомления для администраторов
# ---------------------------------------------------------------------------

class SiteSettings(models.Model):
    """
    Глобальные настройки сайта — создаётся только одна запись (singleton).
    Управляется через Django Admin.
    """

    class Meta:
        verbose_name = _('Настройки сайта')
        verbose_name_plural = _('Настройки сайта')
        db_table = 'users_sitesettings'

    def __str__(self):
        return 'Настройки сайта'

    @classmethod
    def get(cls):
        """Возвращает единственную запись настроек (создаёт если нет)."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class AdminNotificationProfile(models.Model):
    """
    Настройки уведомлений для конкретного администратора.
    Каждый администратор указывает, какие события ему приходят в TG и на сайте.
    """

    EVENT_CHOICES = [
        ('new_account',      _('Новый аккаунт зарегистрирован')),
        ('post_moderation',  _('Пост отправлен на модерацию')),
        ('account_upgrade',  _('Заявка на повышение аккаунта')),
        ('insurance_request', _('Заявка на страхового агента')),
        ('new_visit',        _('Новый визит партнёра')),
    ]

    admin_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_profile',
        verbose_name=_('Администратор'),
        limit_choices_to={'is_staff': True},
    )
    # Какие события получать в Telegram
    telegram_events = models.JSONField(
        default=list,
        verbose_name=_('События в Telegram'),
        help_text=_('Список кодов событий. Пример: ["new_account", "insurance_request"]'),
    )
    # Какие события получать на сайте (in-site)
    site_events = models.JSONField(
        default=list,
        verbose_name=_('События на сайте'),
        help_text=_('Список кодов событий для уведомлений внутри сайта'),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Активно'),
        help_text=_('Снимите галочку, чтобы приостановить все уведомления для этого администратора'),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Профиль уведомлений администратора')
        verbose_name_plural = _('Профили уведомлений администраторов')
        db_table = 'users_adminnotificationprofile'

    def __str__(self):
        return f"Уведомления: {self.admin_user.username}"

    def should_notify_telegram(self, event: str) -> bool:
        return self.is_active and event in (self.telegram_events or [])

    def should_notify_site(self, event: str) -> bool:
        return self.is_active and event in (self.site_events or [])
