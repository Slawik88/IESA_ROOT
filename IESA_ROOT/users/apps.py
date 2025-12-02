from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    
    def ready(self):
        # Import signals to ensure QR generation on save
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
