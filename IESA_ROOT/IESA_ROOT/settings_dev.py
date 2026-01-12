"""
Django settings for IESA_ROOT project - DEVELOPMENT configuration.

Use this for local development only.
Set DJANGO_SETTINGS_MODULE=IESA_ROOT.settings_dev
"""

from .settings_base import *

# Development settings override
DEBUG = True

# Allow localhost and 127.0.0.1
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*.local']

# Use local file storage in development
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

# Static files (development - served by Django)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Local database or existing database
# Keep existing DATABASE_URL setup from base

# Disable HTTPS requirement in development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

print("=" * 80)
print("⚙️  DEVELOPMENT SETTINGS LOADED")
print(f"DEBUG = {DEBUG}")
print(f"MEDIA_ROOT = {MEDIA_ROOT}")
print(f"MEDIA_URL = {MEDIA_URL}")
print("=" * 80)
