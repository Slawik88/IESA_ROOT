from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    """
    Кастомная модель пользователя с дополнительными полями.
    """
    avatar = models.ImageField(
        upload_to='avatars/', 
        default='avatars/default.png', 
        blank=True, 
        verbose_name='Аватар'
    )
    date_of_birth = models.DateField(
        null=True, 
        blank=True, 
        verbose_name='Дата рождения'
    )
    last_online = models.DateTimeField(
        default=timezone.now, 
        verbose_name='Был(а) в сети'
    )
    is_verified = models.BooleanField(
        default=False, 
        verbose_name='Верифицированный пользователь'
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

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.username