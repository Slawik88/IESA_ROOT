"""Anti-bot toolkit for the public forms (register, password reset, appeals).

Layers, cheapest first — each one is independent so a bot has to beat all of them:

1. Honeypot: an input real people never see; bots fill every field.
2. Signed form timer: the page issues a signed timestamp. A POST without it
   (bot hitting the URL directly), with a forged one, or submitted faster than
   a human can type is rejected.
3. Cloudflare Turnstile (free, mostly invisible CAPTCHA) — active as soon as
   TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY are set in the environment.
4. Disposable / throw-away e-mail domains are refused.
5. Persistent throttles (database cache, shared by all workers and surviving
   deploys — unlike the per-process rate-limit cache) that cap how many e-mails
   the site will send to one address, from one account, or from one IP. This is
   what stops the site being used to mail-bomb strangers.
"""
import hashlib
import logging
import time

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import caches
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

HONEYPOT_FIELD = 'x_contact_ref'        # name chosen so browser autofill never targets it
TIMER_FIELD = 'form_ts'
TURNSTILE_FIELD = 'cf-turnstile-response'
TIMER_SALT = 'users.antispam.timer.v1'
MIN_FILL_SECONDS = 3
MAX_FORM_AGE = 24 * 60 * 60
TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'

# Throw-away mailbox providers commonly used by bots. Not exhaustive — it removes
# the bulk; Turnstile and the throttles handle the rest.
DISPOSABLE_DOMAINS = frozenset("""
mailinator.com guerrillamail.com guerrillamail.net guerrillamail.org guerrillamail.biz guerrillamail.de
sharklasers.com grr.la 10minutemail.com 10minutemail.net 20minutemail.com tempmail.com temp-mail.org
temp-mail.io tempmail.net tempmailo.com tempr.email throwawaymail.com trashmail.com trashmail.net
trashmail.de yopmail.com yopmail.net yopmail.fr cool.fr.nf jetable.org nospam.ze.tc nomail.xl.cx
mailnesia.com maildrop.cc dispostable.com fakeinbox.com getairmail.com getnada.com nada.email
mohmal.com emailondeck.com mintemail.com mytemp.email spamgourmet.com spambox.us spam4.me
tempinbox.com tmpmail.net tmpmail.org burnermail.io discard.email discardmail.com mailcatch.com
mailforspam.com mailnull.com mailsac.com mytrashmail.com anonbox.net anonymbox.com binkmail.com
bobmail.info chacuo.net deadaddress.com despam.it devnullmail.com dropmail.me emailfake.com
emailtemporanea.com emkei.cz fakemail.fr filzmail.com fixmail.tk getonemail.com gishpuppy.com
harakirimail.com incognitomail.org inboxalias.com inboxbear.com instant-mail.de jourrapide.com
kasmail.com klzlk.com lroid.com mailexpire.com mailmoat.com mailtothis.com mt2015.com mvrht.net
nowmymail.com objectmail.com owlpic.com pjjkp.com rcpt.at rmqkr.net safetymail.info
sendspamhere.com sogetthis.com spamavert.com spamfree24.org spamhereplease.com superrito.com
teleworm.us tempail.com tempemail.net thankyou2010.com trbvm.com trash-mail.com wegwerfmail.de
wegwerfmail.net wegwerfmail.org yepmail.net zetmail.com zoemail.org 1secmail.com 1secmail.net
1secmail.org esiix.com wwjmp.com xojxe.com vjuum.com laafd.com txcct.com rteet.com dcctb.com
vusra.com cuvox.de dayrep.com einrot.com fleckens.hu gustr.com rhyta.com armyspy.com
""".split())


def client_ip(request):
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


# ── 1 + 2: honeypot and form timer ─────────────────────────────────────────

def issue_form_token():
    return signing.dumps(int(time.time()), salt=TIMER_SALT)


def form_token_problem(post):
    """Return a short machine reason if the timer/honeypot say 'bot', else None."""
    if post.get(HONEYPOT_FIELD):
        return 'honeypot'
    token = post.get(TIMER_FIELD, '')
    if not token:
        return 'no-token'
    try:
        issued = signing.loads(token, salt=TIMER_SALT, max_age=MAX_FORM_AGE)
    except signing.SignatureExpired:
        return 'expired'
    except signing.BadSignature:
        return 'forged'
    if time.time() - issued < MIN_FILL_SECONDS:
        return 'too-fast'
    return None


# ── 3: Cloudflare Turnstile ────────────────────────────────────────────────

def turnstile_enabled():
    return bool(getattr(settings, 'TURNSTILE_SITE_KEY', '') and getattr(settings, 'TURNSTILE_SECRET_KEY', ''))


def turnstile_ok(request):
    """True when Turnstile is off, solved, or Cloudflare itself is unreachable (fail-open)."""
    if not turnstile_enabled():
        return True
    token = request.POST.get(TURNSTILE_FIELD, '')
    if not token:
        return False
    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={'secret': settings.TURNSTILE_SECRET_KEY, 'response': token, 'remoteip': client_ip(request)},
            timeout=5,
        )
        return bool(response.json().get('success'))
    except (requests.RequestException, ValueError):
        logger.warning('Turnstile verification unavailable; letting the request through', exc_info=True)
        return True


# ── combined gate used by the views ────────────────────────────────────────

def bot_problem(request):
    """Return None for a human-looking POST, or a short reason string."""
    reason = form_token_problem(request.POST)
    if reason:
        return reason
    if not turnstile_ok(request):
        return 'turnstile'
    return None


def bot_message():
    return _('We could not verify that you are human. Please reload the page and try again.')


# ── 4: e-mail quality ──────────────────────────────────────────────────────

def is_disposable_email(email):
    domain = (email or '').rsplit('@', 1)[-1].strip().lower()
    return domain in DISPOSABLE_DOMAINS or any(domain.endswith('.' + d) for d in DISPOSABLE_DOMAINS)


# ── 5: persistent throttles ────────────────────────────────────────────────

def throttle(bucket, identity, limit, window_seconds):
    """Count one event; True while within `limit` per `window_seconds`.

    Uses the shared database cache so every worker sees the same counter and a
    deploy does not reset it. If the cache itself is down we fail open.
    """
    digest = hashlib.sha1(str(identity).strip().lower().encode()).hexdigest()[:24]
    key = f'throttle:{bucket}:{digest}'
    try:
        cache = caches['default']
        now = time.time()
        count, started = cache.get(key) or (0, now)
        if now - started >= window_seconds:           # window over: start a new one
            count, started = 0, now
        count += 1
        cache.set(key, (count, started), window_seconds)
        return count <= limit
    except Exception:  # noqa: BLE001 - never block real users because the cache hiccuped
        logger.warning('Throttle cache unavailable for %s', bucket, exc_info=True)
        return True
