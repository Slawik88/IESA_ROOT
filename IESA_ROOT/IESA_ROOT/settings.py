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

    # Наши приложения
    'core',
    'users.apps.UsersConfig',
    'blog',
    'gallery',
    'products',
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
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Static files for production
    'django.contrib.sessions.middleware.SessionMiddleware',
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
    DATABASES['default'] = dj_database_url.config(
        conn_max_age=600,
        ssl_require=True
    )

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

print("=" * 80)
print(f"[SPACES CONFIG] DEBUG = {DEBUG}")
print(f"[SPACES CONFIG] SPACES_KEY = {'SET' if spaces_key else 'NOT SET'}")
print(f"[SPACES CONFIG] SPACES_SECRET = {'SET' if spaces_secret else 'NOT SET'}")
print(f"[SPACES CONFIG] SPACES_BUCKET = {spaces_bucket}")
print("=" * 80)

if spaces_key and spaces_secret and spaces_bucket and not DEBUG:
    # AWS S3 settings (DigitalOcean Spaces совместим с S3 API)
    AWS_ACCESS_KEY_ID = spaces_key
    AWS_SECRET_ACCESS_KEY = spaces_secret
    AWS_STORAGE_BUCKET_NAME = spaces_bucket
    AWS_S3_ENDPOINT_URL = os.getenv('SPACES_ENDPOINT', 'https://fra1.digitaloceanspaces.com')
    AWS_S3_REGION_NAME = 'fra1'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    AWS_DEFAULT_ACL = 'public-read'  # Make all uploaded files public by default
    AWS_QUERYSTRING_AUTH = False  # Don't use query string auth for public files
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.fra1.digitaloceanspaces.com'
    # IMPORTANT: Do NOT use AWS_LOCATION - models use upload_to='media/...'
    # AWS_LOCATION would add extra prefix and break URLs
    
    # Enable boto3 debug logging
    import logging
    logging.basicConfig(level=logging.DEBUG)
    boto3_logger = logging.getLogger('boto3')
    boto3_logger.setLevel(logging.DEBUG)
    botocore_logger = logging.getLogger('botocore')
    botocore_logger.setLevel(logging.DEBUG)
    s3transfer_logger = logging.getLogger('s3transfer')
    s3transfer_logger.setLevel(logging.DEBUG)
    storages_logger = logging.getLogger('storages')
    storages_logger.setLevel(logging.DEBUG)
    
    # STORAGES dict (Django 5.x format) - заменяет DEFAULT_FILE_STORAGE
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "file_overwrite": True,  # Overwrite files with same name
                "default_acl": "public-read",  # Make all files public by default
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    
    # MEDIA_URL points to CDN without extra 'media/' prefix (models use upload_to='...')
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    
    print(f"✅ SPACES ACTIVATED")
    print(f"✅ Bucket: {AWS_STORAGE_BUCKET_NAME}")
    print(f"✅ MEDIA_URL: {MEDIA_URL}")
    print(f"✅ Endpoint: {AWS_S3_ENDPOINT_URL}")
    print(f"✅ All files will be stored at: https://{AWS_S3_CUSTOM_DOMAIN}/<model_upload_to>/<filename>")
    
    print("=" * 80)
else:
    print("❌ SPACES NOT ACTIVATED - Using local storage")
    print("=" * 80)
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
        'code','subscript', 'superscript', 'highlight', '|', 'codeBlock', 'sourceEditing', 'insertImage',
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

# Кастомная модель пользователя
AUTH_USER_MODEL = 'users.User'

# Redis Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache' if not DEBUG else 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'iesa',
        'TIMEOUT': 3600,  # 1 hour default
    }
}

# Настройки авторизации/перенаправления
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'profile'
LOGOUT_REDIRECT_URL = 'home'

# Ключи API (Stripe)
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')

# Import additional settings (logging, email, etc.)
from .settings_addon import *
