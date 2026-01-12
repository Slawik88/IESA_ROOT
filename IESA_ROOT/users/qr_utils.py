import qrcode
import os
from io import BytesIO
from django.core.files.base import ContentFile
from django.conf import settings


def generate_qr_code_for_user(user, request=None):
    """
    Генерирует QR код для пользователя на основе его permanent_id.
    QR код ведёт на маршрут /auth/card/<permanent_id>/

    Сохраняет PNG в MEDIA_ROOT/cards/ и возвращает путь файла.
    Если QR уже существует — обновляет.
    """
    if not user.permanent_id:
        return None

    # URL, который кодируется в QR - используем правильный домен
    # Prefer request host/scheme in runtime if available, else fallback to settings
    domain = (request.get_host() if request is not None else getattr(settings, 'SITE_DOMAIN', 'iesasport.ch'))
    protocol = (getattr(request, 'scheme', None) or ('https' if not settings.DEBUG else 'http'))
    profile_url = f"{protocol}://{domain}/auth/card/{user.permanent_id}/"

    # Создаём QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(profile_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Имя файла на основе permanent_id
    filename = f"cards/{str(user.permanent_id)}.png"

    # Сохраняем в BytesIO
    img_io = BytesIO()
    img.save(img_io, format='PNG')
    img_io.seek(0)

    # Сохраняем в MEDIA_ROOT через Django
    # (используя save() метод для работы с FileField)
    # Но так как это не FileField на модели, сохраняем напрямую на диск

    # Сохраняем через Django storage (поддерживает S3 и локальный диск)
    from django.core.files.storage import default_storage
    filename = f"cards/{str(user.permanent_id)}.png"
    img_io.seek(0)
    filepath = default_storage.save(filename, ContentFile(img_io.getvalue()))

    # Возвращаем медиа URL для отображения в админке
    return f"{settings.MEDIA_URL}cards/{str(user.permanent_id)}.png"
