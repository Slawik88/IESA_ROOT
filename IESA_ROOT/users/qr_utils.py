import qrcode
import os
from io import BytesIO
from django.core.files.base import ContentFile
from django.conf import settings


def generate_qr_code_for_user(user, request=None):
    """
    Создаёт QR-код для карты пользователя
    
    QR ведёт на: {protocol}://{domain}/auth/card/{permanent_id}/
    Сохраняет PNG в S3/локально через Django storage
    """
    if not user.permanent_id:
        return None

    # Определяем URL для QR-кода
    if request:
        domain = request.get_host()
        protocol = getattr(request, 'scheme', 'https')
    else:
        domain = getattr(settings, 'SITE_DOMAIN', 'iesasport.ch')
        protocol = 'http' if settings.DEBUG else 'https'
    
    profile_url = f"{protocol}://{domain}/auth/card/{user.permanent_id}/"

    # Генерируем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(profile_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Конвертируем в байты
    img_io = BytesIO()
    img.save(img_io, format='PNG')
    img_io.seek(0)

    # Сохраняем через Django storage (S3 или локально)
    from django.core.files.storage import default_storage
    
    filename = f"cards/{str(user.permanent_id)}.png"
    
    # Удаляем старый файл
    if default_storage.exists(filename):
        default_storage.delete(filename)
    
    # Сохраняем новый
    filepath = default_storage.save(filename, ContentFile(img_io.getvalue()))

    return f"{settings.MEDIA_URL}{filepath}"
