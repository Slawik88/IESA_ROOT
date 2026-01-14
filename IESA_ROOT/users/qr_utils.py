"""
DEPRECATED: Используйте users.services.QRCodeService

Этот модуль сохранён для обратной совместимости
"""

from .services import QRCodeService


def generate_qr_code_for_user(user, request=None):
    """
    DEPRECATED: Используйте QRCodeService.generate()
    
    Обёртка для обратной совместимости
    """
    return QRCodeService.generate(user, request)

