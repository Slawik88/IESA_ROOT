from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import os

from .models import User
from .qr_utils import generate_qr_code_for_user


@receiver(post_save, sender=User)
def ensure_qr_on_card_activation(sender, instance, created, **kwargs):
    """
    Генерирует QR код, если у пользователя активирована карта (card_active=True)
    и файл с QR отсутствует на диске.

    Это покрывает случай: пользователь был создан без выдачи карты, а затем
    через админку поставили галочку "card_active" и сохранили — QR должен быть создан.
    """
    try:
        if instance.card_active and instance.permanent_id:
            cards_dir = os.path.join(settings.MEDIA_ROOT, 'cards')
            filepath = os.path.join(cards_dir, f"{str(instance.permanent_id)}.png")
            # Если файл не существует — генерируем
            if not os.path.exists(filepath):
                generate_qr_code_for_user(instance)
    except Exception:
        # Нельзя выкидывать ошибки в сигналах — логирование опционально
        pass
