"""Сервис для работы с QR-кодами"""

import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings


class QRCodeService:
    """Сервис генерации QR-кодов для карт"""
    
    @staticmethod
    def generate(user, request=None):
        """
        Создать QR-код для пользователя
        
        Returns:
            str: URL файла в MEDIA_URL
        """
        if not user.permanent_id:
            return None

        # Определяем URL профиля
        url = QRCodeService._build_profile_url(user.permanent_id, request)
        
        # Генерируем QR
        img = QRCodeService._create_qr_image(url)
        
        # Сохраняем в storage
        filename = f"cards/{user.permanent_id}.png"
        return QRCodeService._save_to_storage(img, filename)
    
    @staticmethod
    def _build_profile_url(permanent_id, request=None):
        """Построить URL профиля для QR"""
        if request:
            domain = request.get_host()
            protocol = getattr(request, 'scheme', 'https')
        else:
            domain = getattr(settings, 'SITE_DOMAIN', 'iesasport.ch')
            protocol = 'http' if settings.DEBUG else 'https'
        
        return f"{protocol}://{domain}/auth/card/{permanent_id}/"
    
    @staticmethod
    def _create_qr_image(data):
        """Создать изображение QR-кода"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white")
    
    @staticmethod
    def _save_to_storage(img, filename):
        """Сохранить QR в storage (S3 или локально)"""
        # Конвертируем в байты
        img_io = BytesIO()
        img.save(img_io, format='PNG')
        img_io.seek(0)
        
        # Удаляем старый файл
        if default_storage.exists(filename):
            default_storage.delete(filename)
        
        # Сохраняем новый
        filepath = default_storage.save(filename, ContentFile(img_io.getvalue()))
        return f"{settings.MEDIA_URL}{filepath}"
