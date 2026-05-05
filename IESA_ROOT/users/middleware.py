from django.core.cache import cache
from django.http import HttpResponseNotFound
from django.utils import timezone
from django.utils import translation


class BlockScannerMiddleware:
    """Silently reject requests from vulnerability scanners (.php, wp-* paths)."""
    _BLOCKED_SUFFIXES = ('.php', '.asp', '.aspx', '.cgi', '.env')
    _BLOCKED_PREFIXES = ('/wp-', '/wordpress/', '/.env', '/vendor/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.lower()
        if any(path.endswith(s) for s in self._BLOCKED_SUFFIXES) or \
           any(path.startswith(p) for p in self._BLOCKED_PREFIXES):
            return HttpResponseNotFound(b'', content_type='text/plain')
        return self.get_response(request)

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
            cache_key = f'last_online_{request.user.pk}'
            if not cache.get(cache_key):
                request.user.last_online = timezone.now()
                request.user.save(update_fields=['last_online'])
                cache.set(cache_key, True, 300)

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