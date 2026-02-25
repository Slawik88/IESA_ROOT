"""
Management command: cr_token_refresh
=====================================
Force-refreshes the CleverReach OAuth2 access token using the stored
refresh token and prints the new tokens.

Run on Heroku after first deploy to seed the cache:

    heroku run -a <app-name> python manage.py cr_token_refresh

Run periodically (e.g. monthly) to keep tokens fresh if the Heroku
dyno restarts clear the cache and no user-triggered email auto-refreshed
the token yet.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.cache import cache

import requests
import time


CR_TOKEN_URL = "https://rest.cleverreach.com/oauth/token.php"


class Command(BaseCommand):
    help = "Refresh the CleverReach OAuth2 access token and store it in the cache."

    def handle(self, *args, **options):
        client_id = getattr(settings, "CLEVERREACH_CLIENT_ID", "")
        client_secret = getattr(settings, "CLEVERREACH_CLIENT_SECRET", "")
        refresh_token = getattr(settings, "CLEVERREACH_REFRESH_TOKEN", "")

        if not (client_id and client_secret and refresh_token):
            self.stderr.write(self.style.ERROR(
                "Missing CleverReach credentials in env vars.\n"
                "Make sure CLEVERREACH_CLIENT_ID, CLEVERREACH_CLIENT_SECRET, "
                "and CLEVERREACH_REFRESH_TOKEN are set."
            ))
            return

        self.stdout.write("Refreshing CleverReach access token...")

        try:
            resp = requests.post(
                CR_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
                timeout=15,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            self.stderr.write(self.style.ERROR(
                f"HTTP error from CleverReach token endpoint: {exc}\n{exc.response.text}"
            ))
            return
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Request failed: {exc}"))
            return

        data = resp.json()
        new_access_token = data.get("access_token", "")
        new_refresh_token = data.get("refresh_token", "")
        expires_in = int(data.get("expires_in", 2592000))
        expire_ts = time.time() + expires_in

        if not new_access_token:
            self.stderr.write(self.style.ERROR(f"Unexpected response: {data}"))
            return

        # Store in cache
        cache.set("cleverreach_access_token", new_access_token, timeout=expires_in - 300)
        cache.set("cleverreach_token_expiry", expire_ts, timeout=expires_in)

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Token refreshed successfully!\n"
            f"   Expires in: {expires_in}s ({expires_in // 86400} days)\n"
        ))

        self.stdout.write(self.style.WARNING(
            "⚠️  Update these Heroku config vars with the NEW values:\n"
        ))
        self.stdout.write(
            f"   heroku config:set CLEVERREACH_ACCESS_TOKEN={new_access_token}\n"
        )
        if new_refresh_token and new_refresh_token != refresh_token:
            self.stdout.write(
                f"   heroku config:set CLEVERREACH_REFRESH_TOKEN={new_refresh_token}\n"
            )
            self.stdout.write(self.style.WARNING(
                "   ^ NEW refresh token returned! Update immediately or future refresh will fail.\n"
            ))
        else:
            self.stdout.write(
                f"   CLEVERREACH_REFRESH_TOKEN unchanged: {refresh_token[:10]}...\n"
            )

        # Verify by fetching account info
        try:
            verify_resp = requests.get(
                "https://rest.cleverreach.com/v3/debug/whoami.json",
                headers={"Authorization": f"Bearer {new_access_token}"},
                timeout=10,
            )
            if verify_resp.ok:
                who = verify_resp.json()
                self.stdout.write(self.style.SUCCESS(
                    f"\n✅ Token verified — logged in as: {who.get('login', '?')} "
                    f"(client_id={who.get('client_id', '?')})"
                ))
            else:
                self.stderr.write(self.style.WARNING(
                    f"Token verification returned {verify_resp.status_code}: {verify_resp.text}"
                ))
        except Exception as exc:
            self.stderr.write(self.style.WARNING(f"Token verification skipped: {exc}"))
