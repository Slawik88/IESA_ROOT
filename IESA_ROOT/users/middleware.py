from django.utils import timezone
from django.utils import translation

class LastOnlineMiddleware:
    """
    Middleware, обновляющий поле last_online для авторизованного пользователя
    при каждом его запросе.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Обработка запроса
        response = self.get_response(request)

        # Логика обновления только для авторизованных пользователей
        if request.user.is_authenticated:
            # Обновление поля last_online
            # Используем update_fields для повышения производительности
            request.user.last_online = timezone.now()
            request.user.save(update_fields=['last_online'])

        return response


class AdminLocaleMiddleware:
    """Middleware для принудительной установки русского языка в админ-панели.

    Сайт по умолчанию остаётся на английском (LANGUAGE_CODE='en'),
    но для всех путей, начинающихся с /admin/, мы активируем русскую локаль,
    чтобы встроенный интерфейс администратора и системные сообщения отображались по-русски.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Если запрос в админ-панель — активируем русскую локаль на время обработки
        if request.path.startswith('/admin'):
            translation.activate('ru')
            request.LANGUAGE_CODE = 'ru'
            response = self.get_response(request)
            translation.deactivate()
            return response

        return self.get_response(request)