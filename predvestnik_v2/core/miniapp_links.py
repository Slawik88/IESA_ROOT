"""One fail-safe policy for links that open the Predvestnik Mini App."""

from __future__ import annotations

import os
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl


def miniapp_url(section: str = "") -> str:
    """Return a valid native deep link when configured, otherwise HTTPS.

    ``?startapp=`` on a bare bot username is rejected as ``BOT_INVALID`` until
    BotFather has a Main Mini App.  A named app uses the documented
    ``t.me/<bot>/<short_name>`` form.  Without that explicit short name the
    public HTTPS Mini App is the only truthful fallback.
    """
    bot = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot").strip().lstrip("@")
    short_name = os.getenv("MINIAPP_SHORT_NAME", "").strip().strip("/")
    if bot and short_name:
        suffix = f"?startapp={section}" if section else ""
        return f"https://t.me/{bot}/{short_name}{suffix}"

    base = os.getenv("MINIAPP_URL", "").strip()
    if not base.startswith("https://"):
        return ""
    if not section:
        return base
    parsed = urlsplit(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["startapp"] = section
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
