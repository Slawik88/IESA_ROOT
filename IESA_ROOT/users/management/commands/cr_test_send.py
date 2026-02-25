"""
Management command: cr_test_send
==================================
Send a test email via CleverReach to verify the integration works.

Usage:
    heroku run python manage.py cr_test_send
    heroku run python manage.py cr_test_send --to someone@example.com
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test email via CleverReach to verify the integration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            default="makssamrt29@gmail.com",
            help="Recipient email address (default: makssamrt29@gmail.com)",
        )

    def handle(self, *args, **options):
        from users.cleverreach_client import is_configured, get_account_info, send_cleverreach_email

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

        ok = send_cleverreach_email(
            to_email=recipient,
            to_name=recipient,
            subject="✅ IESA Sport — CleverReach Test Email",
            html="""
<html>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: linear-gradient(135deg,#667eea,#764ba2); padding:30px; border-radius:10px; text-align:center;">
    <h1 style="color:#fff; margin:0;">✅ CleverReach Integration Working</h1>
    <p style="color:#ddd; margin:15px 0 0;">
      IESA Sport transactional emails are now delivered via CleverReach.
    </p>
  </div>
  <div style="padding:20px; background:#f8f9fa; border-radius:0 0 10px 10px;">
    <p>This is a test email sent from the Django management command
    <code>cr_test_send</code>.</p>
    <p>If you received this, CleverReach is correctly configured ✅</p>
  </div>
</body>
</html>
""",
            text="IESA Sport CleverReach integration test — if you received this, it works!",
        )

        if ok:
            self.stdout.write(self.style.SUCCESS(f"✅ Test email sent successfully to {recipient}"))
        else:
            self.stderr.write(self.style.ERROR(
                f"❌ CleverReach send returned False for {recipient}. "
                "Check logs for details."
            ))
