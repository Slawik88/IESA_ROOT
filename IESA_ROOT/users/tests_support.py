"""Helpers shared by the auth tests."""
import time

from django.core import signing

from users import antispam


def human_fields(age_seconds=30):
    """Hidden anti-bot field(s) a real browser would send after the form sat open for a while."""
    token = signing.dumps(int(time.time()) - age_seconds, salt=antispam.TIMER_SALT)
    return {antispam.TIMER_FIELD: token}
