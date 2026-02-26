"""
Management command: cr_test_send
==================================
Send a test email via CleverReach to verify the integration works.

Usage (DigitalOcean App Platform — Console tab):
    python manage.py cr_test_send
    python manage.py cr_test_send --to someone@example.com
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test email via CleverReach to verify the integration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            default="makssmart29@gmail.com",
            help="Recipient email address (default: makssmart29@gmail.com)",
        )

    def handle(self, *args, **options):
        from users.cleverreach_client import is_configured, get_account_info
        from users.email_service import send_test_email

        if not is_configured():
            self.stderr.write(self.style.ERROR(
                "CleverReach is not configured. "
                "Set CLEVERREACH_CLIENT_ID and CLEVERREACH_ACCESS_TOKEN env vars."
            ))
            return

        # Show who we're authenticated as
        try:
            info = get_account_info()
            self.stdout.write(f"Authenticated as: {info.get('login', '?')} "
                              f"(client_id={info.get('client_id', '?')})")
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not fetch account info: {exc}"))

        recipient = options["to"]
        self.stdout.write(f"Sending test email to {recipient}...")

        # Use the unified email service path:
        # CleverReach (if configured) -> SMTP fallback on any CR failure.
        ok = bool(send_test_email(recipient=recipient))

        if ok:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Test email sent successfully to {recipient}"
            ))
        else:
            self.stderr.write(self.style.ERROR(
                f"❌ Email sending returned False for {recipient}. "
                "Check logs for CleverReach errors and SMTP fallback status."
            ))
