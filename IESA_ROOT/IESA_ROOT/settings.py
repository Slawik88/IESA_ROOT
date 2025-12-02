import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Установка BASE_DIR
BASE_DIR = Path(__file__).resolve().parent.parent

# Секретный ключ берется из .env
SECRET_KEY = os.getenv('SECRET_KEY_DJANGO')

# DEBUG установлен в False в продакшене, но для разработки оставим True
DEBUG = True

ALLOWED_HOSTS = []

# Регистрация всех приложений и HTMX
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.messages',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',

    # Наши приложения
    'core',
    'users.apps.UsersConfig',
    'blog',
    'gallery',
    'products',

    # Сторонние библиотеки
    'django_htmx',
    'django_cleanup.apps.CleanupConfig', # Для удаления старых файлов при замене
]

# Optional WYSIWYG editor
# We'll use django-ckeditor when installed. It's safe to add here; installation step will follow.
INSTALLED_APPS += [
    'ckeditor',
]

# Наше кастомное Middleware для обновления статуса пользователя
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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

# Парольная валидация (оставляем стандарт)
AUTH_PASSWORD_VALIDATORS = [
    # ...
]

LANGUAGE_CODE = 'en'
TIME_ZONE = 'Europe/Zurich'
USE_I18N = True
USE_TZ = True


# Настройки статических и медиа-файлов




STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# CKEditor settings (uploads go into MEDIA_ROOT/ckeditor/ by default)
CKEDITOR_UPLOAD_PATH = 'ckeditor/uploads/'
CKEDITOR_ALLOW_NONIMAGE_FILES = False
CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'full',
        'height': 300,
        'width': '100%',
    },
}

# Кастомная модель пользователя
AUTH_USER_MODEL = 'users.User'

# Настройки авторизации/перенаправления
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'profile'
LOGOUT_REDIRECT_URL = 'home'

# Ключи API (Stripe)
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')