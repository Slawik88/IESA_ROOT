import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Установка BASE_DIR
BASE_DIR = Path(__file__).resolve().parent.parent

# Секретный ключ берется из .env
SECRET_KEY = os.getenv('SECRET_KEY_DJANGO')

# DEBUG установлен в False в продакшене, для разработки можно True
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

# SECURITY: Явно установить разрешённые хосты
# Production: загружаем из переменной окружения ALLOWED_HOSTS (разделённые запятыми)
# Development: используем localhost
if 'ALLOWED_HOSTS' in os.environ:
    ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '').split(',')]
else:
    ALLOWED_HOSTS = [
        'localhost',
        '127.0.0.1',
        'iesasport.ch',
        'www.iesasport.ch',
        '162.159.140.98',  # DigitalOcean static IP 1
        '172.66.0.96',     # DigitalOcean static IP 2
        'iesaroot-app-8kuyb.ondigitalocean.app'  # DigitalOcean App Platform domain
    ]

# Site domain для QR кодов и других URL построений
SITE_DOMAIN = os.getenv('SITE_DOMAIN', 'iesasport.ch')

# CSRF trusted origins for production
CSRF_TRUSTED_ORIGINS = [
    'https://iesasport.ch',
    'https://www.iesasport.ch',
    'https://iesaroot-app-8kuyb.ondigitalocean.app',  # DigitalOcean App Platform
]

# Для локальной разработки добавляем HTTP адреса
if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        'http://127.0.0.1:8000',
        'http://localhost:8000',
        'http://127.0.0.1:8001',
        'http://localhost:8001',
        'https://127.0.0.1:8443',
        'https://localhost:8443',
    ]

# Регистрация всех приложений и HTMX
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.messages',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',

    # Модуль переводов - ОБЯЗАТЕЛЬНО ДО НАШИХ ПРИЛОЖЕНИЙ
    'modeltranslation',

    # Наши приложения
    'core.apps.CoreConfig',
    'users.apps.UsersConfig',
    'blog.apps.BlogConfig',
    'gallery.apps.GalleryConfig',
    'products.apps.ProductsConfig',
    'notifications.apps.NotificationsConfig',  # Notification system

    # Сторонние библиотеки
    'django_htmx',
    'django_cleanup.apps.CleanupConfig', # Для удаления старых файлов при замене
    'django_ckeditor_5', # Безопасный WYSIWYG редактор CKEditor 5
    'imagekit', # Image optimization and thumbnails
    'storages',  # For DigitalOcean Spaces / S3 storage
]

# Dev-only HTTPS server support (optional): add sslserver in DEBUG
if DEBUG:
    INSTALLED_APPS.append('sslserver')

# Наше кастомное Middleware для обновления статуса пользователя
MIDDLEWARE = [
    'users.middleware.BlockScannerMiddleware',  # Silence .php/.wp scanner spam
    'IESA_ROOT.security_middleware.SecurityHeadersMiddleware',  # audit v5: CSP + Permissions-Policy
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Static files for production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    # Force Russian locale for admin panel via custom middleware
    'users.middleware.AdminLocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Custom Middleware
    'users.middleware.LastOnlineMiddleware', 

    # HTMX middleware
    'django_htmx.middleware.HtmxMiddleware',
    # V1: login-редирект в hx-запросе = страница логина внутри страницы; глушим в 204
    'IESA_ROOT.security_middleware.HtmxLoginRedirectMiddleware',
]

ROOT_URLCONF = 'IESA_ROOT.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], # Общая папка шаблонов
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'notifications.context_processors.unread_notifications',
                'core.context_processors.social_networks',
            ],
        },
    },
]

WSGI_APPLICATION = 'IESA_ROOT.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Production database configuration (PostgreSQL via DATABASE_URL)
if 'DATABASE_URL' in os.environ:
    import dj_database_url
    # Persistent connections reduce pool exhaustion.
    # With Daphne's sync-view thread pool (≤10 threads), CONN_MAX_AGE=60
    # means at most ~10 long-lived DB connections instead of a fresh
    # connection per concurrent request.  Override via DB_CONN_MAX_AGE env
    # var (0 = close after each request; -1 = unlimited lifetime).
    # Default 60s — avoids "remaining connection slots reserved for superuser"
    # burst that occurs when every worker opens a new connection simultaneously.
    _CONN_MAX_AGE = int(os.getenv('DB_CONN_MAX_AGE', '60'))
    # DATABASE_POOL_URL can point to DigitalOcean PgBouncer (port 25061) for
    # transaction-mode connection pooling — highly recommended to prevent
    # "remaining connection slots are reserved for superuser" errors.
    # If not set, falls back to the direct DATABASE_URL (port 25060).
    _db_url = os.getenv('DATABASE_POOL_URL') or os.environ['DATABASE_URL']
    DATABASES['default'] = dj_database_url.config(
        default=_db_url,
        conn_max_age=_CONN_MAX_AGE,
        ssl_require=True,
        conn_health_checks=True,
    )
    # Required when using PgBouncer in transaction pooling mode:
    # server-side cursors keep a named cursor open across statements which
    # breaks transaction pooling.
    DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True
    # Short timeout so a saturated DB returns an error quickly rather than
    # holding a worker thread open.
    DATABASES['default'].setdefault('OPTIONS', {})['connect_timeout'] = 10

# Парольная валидация
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'users.validators.UppercaseValidator',
    },
    {
        'NAME': 'users.validators.SpecialCharacterValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Europe/Zurich'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('uk', 'Ukrainian'),
    ('fr', 'French'),
    ('de', 'German'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# django-modeltranslation settings
MODELTRANSLATION_DEFAULT_LANGUAGE = 'en'
MODELTRANSLATION_LANGUAGES = ('en', 'uk', 'fr', 'de')
# V6: полный фолбэк — если язык не заполнен, показываем любой заполненный (пустых карточек не бывает)
MODELTRANSLATION_FALLBACK_LANGUAGES = ('en', 'uk', 'fr', 'de')
MODELTRANSLATION_PREPOPULATE_LANGUAGE = 'en'

# SECURITY: HTTPS and Security Headers
# Для локальной разработки (DEBUG=True) - все HTTPS настройки ОТКЛЮЧЕНЫ
# Для production (DEBUG=False) - все HTTPS настройки ВКЛЮЧЕНЫ

# SSL Redirect
_SECURE_SSL_REDIRECT_ENV = os.getenv('SECURE_SSL_REDIRECT')
if _SECURE_SSL_REDIRECT_ENV is not None:
    SECURE_SSL_REDIRECT = _SECURE_SSL_REDIRECT_ENV.lower() in ('true', '1', 'yes')
else:
    SECURE_SSL_REDIRECT = False if DEBUG else True  # Отключено для DEBUG=True

# Secure Cookies
SESSION_COOKIE_SECURE = False if DEBUG else True  # Отключено для DEBUG=True
CSRF_COOKIE_SECURE = False if DEBUG else True  # Отключено для DEBUG=True

# HTTP Strict Transport Security (HSTS) - ОТКЛЮЧЕНО для разработки
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000  # 0 для DEBUG=True
SECURE_HSTS_INCLUDE_SUBDOMAINS = False if DEBUG else True
SECURE_HSTS_PRELOAD = False if DEBUG else True

# Trust the X-Forwarded-Proto header from DigitalOcean's reverse proxy
# so request.build_absolute_uri() returns https:// URLs in production
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Базовые security headers (работают и на HTTP)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Настройки статических и медиа-файлов




STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Whitenoise configuration for production static files
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
if DEBUG:
    MEDIA_ROOT = BASE_DIR / 'media'
else:
    MEDIA_ROOT = None  # Not used with S3 storage

# DigitalOcean Spaces configuration for media files
# В production используем Spaces вместо локального хранилища
spaces_key = os.getenv('SPACES_KEY')
spaces_secret = os.getenv('SPACES_SECRET')
spaces_bucket = os.getenv('SPACES_BUCKET')

if spaces_key and spaces_secret and spaces_bucket and not DEBUG:
    # AWS S3 settings (DigitalOcean Spaces совместим с S3 API)
    AWS_ACCESS_KEY_ID = spaces_key
    AWS_SECRET_ACCESS_KEY = spaces_secret
    AWS_STORAGE_BUCKET_NAME = spaces_bucket
    AWS_S3_ENDPOINT_URL = os.getenv('SPACES_ENDPOINT', 'https://fra1.digitaloceanspaces.com')
    AWS_S3_REGION_NAME = 'fra1'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=31536000',
    }
    AWS_DEFAULT_ACL = 'public-read'  # Make all uploaded files public by default
    AWS_QUERYSTRING_AUTH = False  # Don't use query string auth for public files
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.fra1.digitaloceanspaces.com'
    # IMPORTANT: Do NOT use AWS_LOCATION - models use upload_to='media/...'
    # AWS_LOCATION would add extra prefix and break URLs
    
    # STORAGES dict (Django 5.x format) - заменяет DEFAULT_FILE_STORAGE
    STORAGES = {
        "default": {
            "BACKEND": "IESA_ROOT.storage.MediaOptimizationStorage",
            "OPTIONS": {
                "file_overwrite": True,   # django-cleanup replaces old files by name
                "default_acl": "public-read",
            },
        },
        # Explicitly use Whitenoise here — Django 5.x ignores the deprecated
        # STATICFILES_STORAGE setting when STORAGES is defined.
        # manifest_strict=False prevents 500s when third-party CSS/JS
        # references assets not listed in staticfiles.json.
        # Uses a subclass because manifest_strict is a class attribute,
        # not an __init__ parameter (Django 5 passes OPTIONS as **kwargs).
        "staticfiles": {
            "BACKEND": "IESA_ROOT.storage.WhitenoiseManifestStorage",
        },
    }
    
    # MEDIA_URL points to CDN without extra 'media/' prefix (models use upload_to='...')
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
else:
    # Development or incomplete config - use local storage
    pass

# CKEditor 5 настройки - современный безопасный редактор
customColorPalette = [
    {'color': 'hsl(4, 90%, 58%)', 'label': 'Red'},
    {'color': 'hsl(340, 82%, 52%)', 'label': 'Pink'},
    {'color': 'hsl(291, 64%, 42%)', 'label': 'Purple'},
    {'color': 'hsl(262, 52%, 47%)', 'label': 'Deep Purple'},
    {'color': 'hsl(231, 48%, 48%)', 'label': 'Indigo'},
    {'color': 'hsl(207, 90%, 54%)', 'label': 'Blue'},
]

CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': ['heading', '|', 'bold', 'italic', 'link',
                    'bulletedList', 'numberedList', 'blockQuote', 'imageUpload', ],
    },
    'extends': {
        'blockToolbar': [
            'paragraph', 'heading1', 'heading2', 'heading3',
            '|',
            'bulletedList', 'numberedList',
            '|',
            'blockQuote',
        ],
        'toolbar': ['heading', '|', 'outdent', 'indent', '|', 'bold', 'italic', 'link', 'underline', 'strikethrough',
        'code','subscript', 'superscript', 'highlight', '|', 'codeBlock', 'insertImage',
                    'bulletedList', 'numberedList', 'todoList', '|',  'blockQuote', 'imageUpload', '|',
                    'fontSize', 'fontFamily', 'fontColor', 'fontBackgroundColor', 'mediaEmbed', 'removeFormat',
                    'insertTable',],
        'image': {
            'toolbar': ['imageTextAlternative', '|', 'imageStyle:alignLeft',
                        'imageStyle:alignRight', 'imageStyle:alignCenter', 'imageStyle:side',  '|'],
            'styles': [
                'full',
                'side',
                'alignLeft',
                'alignRight',
                'alignCenter',
            ]
        },
        'table': {
            'contentToolbar': [ 'tableColumn', 'tableRow', 'mergeTableCells',
            'tableProperties', 'tableCellProperties' ],
            'tableProperties': {
                'borderColors': customColorPalette,
                'backgroundColors': customColorPalette
            },
            'tableCellProperties': {
                'borderColors': customColorPalette,
                'backgroundColors': customColorPalette
            }
        },
        'heading' : {
            'options': [
                { 'model': 'paragraph', 'title': 'Paragraph', 'class': 'ck-heading_paragraph' },
                { 'model': 'heading1', 'view': 'h1', 'title': 'Heading 1', 'class': 'ck-heading_heading1' },
                { 'model': 'heading2', 'view': 'h2', 'title': 'Heading 2', 'class': 'ck-heading_heading2' },
                { 'model': 'heading3', 'view': 'h3', 'title': 'Heading 3', 'class': 'ck-heading_heading3' }
            ]
        }
    },
    'list': {
        'properties': {
            'styles': 'true',
            'startIndex': 'true',
            'reversed': 'true',
        }
    }
}

CKEDITOR_5_UPLOAD_PATH = 'ckeditor5/uploads/'
CKEDITOR_5_ALLOW_ALL_FILE_TYPES = False
CKEDITOR_5_FILE_UPLOAD_PERMISSION = 'staff'

# Image upload size limits (5 MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# django-imagekit: disable on-demand thumbnail generation in production
# (we convert to WebP ourselves in MediaOptimizationStorage)
IMAGEKIT_CACHEFILE_STRATEGY = 'imagekit.cachefiles.strategies.Optimistic'
if not DEBUG:
    IMAGEKIT_DEFAULT_CACHEFILE_STRATEGY = 'imagekit.cachefiles.strategies.Optimistic'
    IMAGEKIT_SPEC_CACHEFILE_NAMER = 'imagekit.cachefiles.namers.source_name_dot_hash'

# Кастомная модель пользователя
AUTH_USER_MODEL = 'users.User'

# Cache Configuration — DatabaseCache (shared across all workers, no Redis required)
# audit v5: LocMemCache был per-process — между gunicorn/daphne воркерами не работал.
# DatabaseCache использует ту же PostgreSQL, что и приложение — shared cache между
# всеми воркерами (важно для rate-limiting, SSE state, expensive queries).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache_table',
        'KEY_PREFIX': 'iesa',
        'TIMEOUT': 3600,  # 1 hour default
        'OPTIONS': {
            'MAX_ENTRIES': 5000,
            'CULL_FREQUENCY': 3,   # При переполнении удаляется 1/3 устаревших записей
        },
    },
    # FIX 2026-05-28: отдельный кэш для rate-limit и других hot-loop проверок.
    # Используем LocMemCache (per-process) чтобы каждый запрос НЕ открывал
    # новое DB-соединение. Trade-off: rate-limit per worker, не глобальный
    # для всего кластера. Для нашей нагрузки (~5 workers) это OK защита
    # от brute-force, но НЕ открываем 100+ DB connections на бот-атаку.
    # Главный профит: избегаем "remaining connection slots reserved for
    # superuser" при scan-атаках (100+ запросов в секунду).
    'ratelimit': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'iesa-ratelimit',
        'TIMEOUT': 3600,
        'OPTIONS': {'MAX_ENTRIES': 10000},
    },
}

# Используем отдельный кэш для django_ratelimit (см. CACHES['ratelimit'] выше)
RATELIMIT_USE_CACHE = 'ratelimit'

# Session Configuration - Support multiple devices/sessions per user
# cached_db checks the in-process cache (LocMemCache) first and only
# falls back to the DB on a cache miss.  This nearly eliminates the extra
# connection opened per-request by pure 'db' sessions when the pool is tight.
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

# Session timeout (in seconds): 30 days
SESSION_COOKIE_AGE = 30 * 24 * 60 * 60

# Allow multiple concurrent sessions from different devices
# By default, Django allows this - each device gets its own session ID
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Additional CSRF settings for mobile compatibility
CSRF_COOKIE_AGE = 31449600  # 1 year
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'

# Allow CSRF from same site
CSRF_USE_SESSIONS = False

# Настройки авторизации/перенаправления
LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'users:profile'
LOGOUT_REDIRECT_URL = 'home'

# Ключи API (Stripe)
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')

# Note: WebSocket/Channels removed - using HTMX polling for notifications
# This reduces database connection pressure significantly

# Import additional settings (logging, email, CleverReach, etc.)
from .settings_addon import *  # noqa: F401,F403
