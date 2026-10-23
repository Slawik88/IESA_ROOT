"""django-allauth adapters: how "Continue with Google/Microsoft/Facebook/Apple" maps onto IESA accounts.

allauth is used only for the OAuth handshake. Everything about *who gets an
account* is decided here:

* A social sign-in whose provider-verified e-mail matches an existing member
  logs that member in (and links the provider) instead of creating a duplicate.
* If the e-mail exists but the provider does NOT vouch for it, nothing is linked
  and nobody is logged in — otherwise anyone could take over an account by
  registering the victim's address at a lax provider.
* New members get the same state as a normal registration: active membership,
  generated unique username, e-mail marked as confirmed (the provider confirmed it).
"""
import re
import unicodedata

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import User


def _ascii_slug(value):
    value = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9_.-]+', '', value)


def generate_username(*hints):
    """Pick a free username (case-insensitive) from the first usable hint."""
    base = ''
    for hint in hints:
        base = _ascii_slug((hint or '').split('@')[0])[:24]
        if len(base) >= 3:
            break
    if len(base) < 3:
        base = 'member'
    candidate, n = base, 0
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f'{base}{n}'
    return candidate


class IESAAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # allauth's own sign-up form is never exposed; accounts are created by
        # RegisterView (with anti-bot checks) or by the social adapter below.
        return False


class IESASocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return True

    # -- link or refuse before allauth decides to create anything -------------
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return
        email = (sociallogin.user.email or '').strip().lower()
        if not email:
            for address in sociallogin.email_addresses:
                email = (address.email or '').strip().lower()
                if email:
                    break
        if not email:
            return                                   # allauth will ask for an e-mail

        provider_verified = any(
            address.verified and address.email.strip().lower() == email
            for address in sociallogin.email_addresses
        )
        matches = list(User.objects.filter(email__iexact=email)[:2])
        if not matches:
            return
        if len(matches) == 1 and provider_verified and matches[0].is_active:
            sociallogin.connect(request, matches[0])
            if not matches[0].email_verified_at:
                matches[0].email_verified_at = timezone.now()
                matches[0].save(update_fields=['email_verified_at'])
            return

        messages.error(request, _(
            'An account with this e-mail address already exists. '
            'Sign in with your password (or reset it) — we could not safely link it to this provider.'
        ))
        raise ImmediateHttpResponse(redirect('users:login'))

    # -- brand-new member ------------------------------------------------------
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.email = (user.email or '').strip().lower()
        user.username = generate_username(
            data.get('username'), data.get('email'), f"{data.get('first_name', '')}{data.get('last_name', '')}",
        )
        user.membership_status = 'active'
        if any(a.verified and a.email.strip().lower() == user.email for a in sociallogin.email_addresses):
            user.email_verified_at = timezone.now()
        return user

    def get_signup_form_initial_data(self, sociallogin):
        initial = super().get_signup_form_initial_data(sociallogin)
        initial['username'] = generate_username(initial.get('username'), initial.get('email'))
        return initial
