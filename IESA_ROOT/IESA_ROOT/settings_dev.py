"""Local development settings for the IESA site (never used in production).

Run from the IESA_ROOT/ folder (where manage.py is), e.g.:

    set DJANGO_SETTINGS_MODULE=IESA_ROOT.settings_dev     (PowerShell: $env:DJANGO_SETTINGS_MODULE=...)
    set PYTHONUTF8=1                                      (Windows console is cp1251; old migrations print arrows)
    python manage.py runserver 127.0.0.1:8000

What it changes compared to settings.py:
  * works without a .env file (dummy SECRET_KEY), any host allowed, no HTTPS redirect
  * drops 'sslserver' (not installed in the venv)
  * uses its own database copy `dev.sqlite3` (cloned from db.sqlite3 on first run), so
    migrations and test data never touch the tracked db.sqlite3
  * e-mails go to the console
"""
import os
import shutil

os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('SECURE_SSL_REDIRECT', 'False')

from .settings import *  # noqa: E402,F401,F403

DEBUG = True
SECRET_KEY = os.getenv('SECRET_KEY_DJANGO') or 'dev-only-insecure-key-do-not-use-in-production-0123456789'
ALLOWED_HOSTS = ['*']
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'sslserver']

_dev_db = BASE_DIR / 'dev.sqlite3'
if not _dev_db.exists() and (BASE_DIR / 'db.sqlite3').exists():
    shutil.copy2(BASE_DIR / 'db.sqlite3', _dev_db)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': _dev_db}}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
