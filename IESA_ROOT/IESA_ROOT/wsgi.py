"""
WSGI config for IESA_ROOT project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

application = get_wsgi_application()

# Initialize data on first deployment
try:
    from .init_data import init_data
    init_data()
except Exception as e:
    print(f"Warning: Could not initialize data: {e}")
