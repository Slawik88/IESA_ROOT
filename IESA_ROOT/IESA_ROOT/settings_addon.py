# Additional settings for logging and email
# This file is imported at the end of settings.py

import os

# Logging configuration
# In production (DEBUG=False), use only console logging (ephemeral filesystem)
# In development (DEBUG=True), use both console and file logging
DEBUG_MODE = os.getenv('DEBUG', 'False') == 'True'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose' if not DEBUG_MODE else 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'blog': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'users': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}

# Add file handler only in development
if DEBUG_MODE:
    import os
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    LOGGING['handlers']['file'] = {
        'level': 'WARNING',
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': os.path.join(log_dir, 'django.log'),
        'maxBytes': 1024 * 1024 * 10,  # 10 MB
        'backupCount': 5,
        'formatter': 'verbose',
    }
    # Add file handler to loggers
    for logger in LOGGING['loggers'].values():
        logger['handlers'].append('file')

# Email Configuration — Resend SMTP
# Use RESEND_API_KEY env var on Heroku. Falls back to console for local dev.
import os as _os  # noqa (may already be imported at top of settings.py)

_RESEND_API_KEY = _os.environ.get('RESEND_API_KEY', '')

if _RESEND_API_KEY:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.resend.com'
    EMAIL_PORT = 465
    EMAIL_USE_SSL = True
    EMAIL_USE_TLS = False
    EMAIL_HOST_USER = 'resend'
    EMAIL_HOST_PASSWORD = _RESEND_API_KEY
    DEFAULT_FROM_EMAIL = 'IESA Sport <noreply@iesasport.ch>'
else:
    # Local development — print emails to console
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'IESA Sport <noreply@iesasport.ch>'
