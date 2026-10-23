"""Isolated website tests: no development database, uploads, SMTP or Spaces.

Run: python manage.py test --settings=IESA_ROOT.settings_test --noinput
The fast password hasher is deliberately confined to this settings module.
"""
import atexit
import os
import tempfile

from .settings import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = 'iesa-tests-only-key-0123456789abcdef0123456789abcdef'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'sslserver']
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
if os.environ.get('IESA_TEST_DATABASE_URL'):
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(os.environ['IESA_TEST_DATABASE_URL'], conn_max_age=0)}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
_test_files = tempfile.TemporaryDirectory(prefix='iesa-tests-')
atexit.register(_test_files.cleanup)
MEDIA_ROOT = _test_files.name
MEDIA_URL = '/media/'
STATIC_ROOT = _test_files.name + '/staticfiles'
SOCIALACCOUNT_PROVIDERS = {}
TURNSTILE_SITE_KEY = ''
TURNSTILE_SECRET_KEY = ''
