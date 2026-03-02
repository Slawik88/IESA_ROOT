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

        # On every startup: register bot commands AND re-register the webhook
        # (ensures allowed_updates is always up-to-date, no manual step needed).
        # Runs in a daemon thread so it never blocks startup or fails the deploy.
        import threading

        def _setup_bot():
            import asyncio, os, logging
            log = logging.getLogger('users.telegram')
            try:
                from .telegram import init_bot_commands
                asyncio.run(init_bot_commands())
            except Exception as e:
                log.warning('init_bot_commands failed: %s', e)

            # Auto-register webhook so allowed_updates is always current.
            # Requires SITE_URL env var (e.g. https://iesasport.ch).
            try:
                from .telegram.client import set_webhook
                from .telegram.config import webhook_secret, is_configured
                # SITE_URL env var overrides the default; hardcoded fallback
                # means this works even if the env var is not set in DO dashboard.
                site_url = os.environ.get('SITE_URL', 'https://iesasport.ch').rstrip('/')
                if is_configured():
                    secret = webhook_secret()
                    webhook_url = f"{site_url}/auth/telegram/webhook/{secret}/"
                    ok, msg = set_webhook(webhook_url)
                    if ok:
                        log.info('Webhook auto-registered: %s', webhook_url)
                    else:
                        log.warning('Webhook auto-register failed: %s', msg)
            except Exception as e:
                log.warning('set_webhook at startup failed: %s', e)

        threading.Thread(target=_setup_bot, daemon=True).start()
