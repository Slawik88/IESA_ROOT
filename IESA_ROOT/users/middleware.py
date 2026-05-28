import re
from django.core.cache import cache
from django.http import HttpResponseNotFound
from django.utils import timezone
from django.utils import translation


class BlockScannerMiddleware:
    """Silently reject vulnerability-scanner requests with empty 404.

    Critical for production: scanners hit dozens of paths per second
    looking for /firebase-key.json, /.env*, /.git/HEAD, /gcp-credentials.json,
    etc. Without early rejection each request goes through Session+Auth
    middleware → opens a DB connection → exhausts PostgreSQL connection
    slots ("remaining connection slots are reserved for superuser" errors).

    Expanded 2026-05-28 from production logs (~50+ scan patterns observed).
    Returns 24-byte 404 instead of rendering the 51KB error page.
    """

    # Расширенный список — собран из реальных логов прода (2026-05-28).
    _BLOCKED_SUFFIXES = (
        # Web app scanners
        '.php', '.asp', '.aspx', '.cgi', '.jsp',
        # Backup / config / leaked secrets
        '.env', '.env~', '.env.bak', '.env.backup', '.env.copy',
        '.env.local', '.env.production', '.env.development', '.env.staging',
        '.env.old', '.env.orig', '.env.save', '.env.swp', '.env.production.bak',
        '.env.production.backup', '.env.production.save', '.env.production.swp',
        '.env.production.orig', '.env.production~', '.env.production.copy',
        '.env.production.old', '.env.local.bak', '.env.local.backup',
        '.env.local.swp', '.env.local.orig', '.env.local.save',
        '.env.local.copy', '.env.local.old', '.env.local~',
        # Vim/temp backups
        '.swp', '.swo', '.bak', '~',
    )

    # Префиксы — пути которые нечего делать на сайте.
    _BLOCKED_PREFIXES = (
        '/wp-', '/wordpress/', '/.env', '/vendor/',
        '/.git/', '/.aws/', '/.config/', '/.ssh/',
        '/admin/config', '/phpmyadmin', '/pma/',
    )

    # Точные имена файлов (без / в середине) которые часто сканируются.
    # Покрывает: credentials, service-account, firebase, gcp, sa-key и т.п.
    _BLOCKED_FILES = frozenset((
        '/credentials.json', '/credentials.yaml', '/credentials',
        '/secrets.json', '/secrets.yaml', '/secret.json',
        '/client_secret.json', '/client_secrets.json', '/sa-private-key.json',
        '/service-account.json', '/service-account-key.json', '/serviceaccountkey.json',
        '/service_account.json', '/sa-key.json',
        '/gcp-credentials.json', '/gcp-sa.json', '/gcp_key.json',
        '/gcp-key.json', '/gcp-service-account.json', '/gcloud-service-key.json',
        '/cloud-key.json', '/google-key.json', '/google-credentials.json',
        '/google-service-account.json',
        '/firebase.json', '/firebase-key.json', '/firebase-config.json',
        '/firebase-adminsdk.json', '/firebase-credentials.json',
        '/firebase-service-account.json',
        '/application_default_credentials.json',
        '/config.json', '/keyfile.json', '/key.json',
        '/settings.py', '/local_settings.py', '/config/settings.py',
        '/config/service-account.json', '/config/credentials.json',
        '/app/.env', '/app/credentials.json', '/api/.env', '/api/client_secret.json',
        '/backend/.env',
        '/env', '/ads.txt', '/llms.txt', '/.well-known/llms.txt',
        '/js/config.js',
    ))

    # Дешёвый regex для путей вроде /.env.* и /firebase-*.json
    _BLOCKED_PATTERN = re.compile(
        r'^/(?:'
        r'firebase-[a-z\-]*\.json|'
        r'gcp-[a-z\-]*\.json|'
        r'google-[a-z\-]*\.json|'
        r'\.env(?:\.[a-z]+)*(?:[~]|\.(?:bak|backup|copy|old|orig|save|swp|local|production|development))*'
        r')$',
        re.IGNORECASE,
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def _is_scanner_path(self, path_lower):
        return bool(
            path_lower in self._BLOCKED_FILES
            or any(path_lower.endswith(s) for s in self._BLOCKED_SUFFIXES)
            or any(path_lower.startswith(p) for p in self._BLOCKED_PREFIXES)
            or self._BLOCKED_PATTERN.match(path_lower)
        )

    def __call__(self, request):
        path_lower = request.path.lower()
        if not self._is_scanner_path(path_lower):
            return self.get_response(request)

        # Scanner-path hit. Возвращаем 24-byte 404 без рендеринга шаблона.
        # Также инкрементим counter по IP — если IP делает 20+ scan-запросов
        # за минуту, в логи не пишем (silent block) — это снижает spam в логах.
        # Не используем БД-cache (default), а LocMemCache (ratelimit) — чтобы
        # сами проверки не тянули новые DB connections.
        try:
            from django.core.cache import caches
            ip = (
                request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                or request.META.get('REMOTE_ADDR', '')
            )
            if ip:
                k = f'scan_hits:{ip}'
                rl_cache = caches['ratelimit']
                hits = (rl_cache.get(k) or 0) + 1
                rl_cache.set(k, hits, 60)  # 60-second sliding window
        except Exception:
            pass  # cache недоступен — продолжаем без счётчика

        return HttpResponseNotFound(b'', content_type='text/plain')

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