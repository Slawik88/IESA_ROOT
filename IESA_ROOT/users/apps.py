from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    
    def ready(self):
        # Import signals to ensure QR generation on save
        try:
            from . import signals  # noqa: F401
            from . import signals_partner  # noqa: F401
        except Exception:
            pass

        # Register bot command list in Telegram (powers the "/" menu).
        # Runs in a daemon thread so it never blocks startup or fails the deploy.
        import threading

        def _register_commands():
            import asyncio
            try:
                from .telegram import init_bot_commands
                asyncio.run(init_bot_commands())
            except Exception:
                pass

        threading.Thread(target=_register_commands, daemon=True).start()
