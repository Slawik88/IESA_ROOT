# Additional settings for logging and email
# This file is imported at the end of settings.py

import os

# Logging configuration
# In production (DEBUG=False), use only console logging (ephemeral filesystem)
# In development (DEBUG=True), use both console and file logging
DEBUG_MODE = os.getenv('DEBUG', 'True') == 'True'

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

# Email Configuration (placeholder - configure in .env when ready)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # For development
# Uncomment and configure when ready for production:
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
# EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
# EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
# DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@iesasport.ch')
