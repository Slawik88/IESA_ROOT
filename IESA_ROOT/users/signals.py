from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import logging
import os

from .models import User
from .qr_utils import generate_qr_code_for_user

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def ensure_qr_on_card_activation(sender, instance, created, **kwargs):
    """
    Генерирует QR код автоматически для ВСЕХ пользователей.
    QR код и идентификатор создаются при создании пользователя.
    Физическая карта (has_physical_card) - это просто отметка в админке.
    """
    try:
        if not instance.permanent_id:
            return
        # MEDIA_ROOT is None in production (S3/DigitalOcean Spaces) — skip local check
        if not settings.MEDIA_ROOT:
            generate_qr_code_for_user(instance)
            return
        cards_dir = os.path.join(settings.MEDIA_ROOT, 'cards')
        filepath = os.path.join(cards_dir, f"{str(instance.permanent_id)}.png")
        if not os.path.exists(filepath):
            generate_qr_code_for_user(instance)
    except Exception as exc:
        # Не прерываем сохранение пользователя, но логируем для диагностики (B1-06)
        logger.error(
            "ensure_qr_on_card_activation failed for user %s (permanent_id=%s): %s",
            instance.pk, instance.permanent_id, exc,
            exc_info=True,
        )
