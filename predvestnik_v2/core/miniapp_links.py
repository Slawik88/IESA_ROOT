"""One fail-safe policy for links that open the Predvestnik Mini App."""

from __future__ import annotations

import os
import re
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl


def _section(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:40]


def miniapp_web_url(section: str = "") -> str:
    """Return the HTTPS URL used by private Telegram Web App buttons."""
    base = os.getenv("MINIAPP_URL", "").strip()
    if not base.startswith("https://"):
        return ""
    section = _section(section)
    if not section:
        return base
    parsed = urlsplit(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["startapp"] = section
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def miniapp_url(section: str = "") -> str:
    """Return a Telegram-native launch link for ordinary URL buttons.

    ``?startapp=`` on a bare bot username is rejected as ``BOT_INVALID`` until
    BotFather has a Main Mini App.  A named app uses the documented
    ``t.me/<bot>/<short_name>`` form. Without it, open the bot DM; its /start
    handler sends a private Web App button carrying signed Telegram initData.
    """
    bot = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot").strip().lstrip("@")
    short_name = os.getenv("MINIAPP_SHORT_NAME", "").strip().strip("/")
    section = _section(section)
    if bot and short_name:
        suffix = f"?startapp={section}" if section else ""
        return f"https://t.me/{bot}/{short_name}{suffix}"
    if bot:
        return f"https://t.me/{bot}?start=miniapp_{section or 'home'}"
    return miniapp_web_url(section)
