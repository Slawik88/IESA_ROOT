#!/usr/bin/env python3
"""Verify the externally configured Mini App shell before Telegram exposes it."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.test", override=True)
url = os.environ["PREPROD_MINIAPP_URL"].rstrip("/") + "/"
parts = urlsplit(url)
if parts.scheme != "https" or not parts.netloc or not parts.path.startswith("/predvestnik"):
    raise SystemExit("PREPROD_MINIAPP_URL must be an external HTTPS /predvestnik URL")
request = Request(url, headers={"User-Agent": "Predvestnik-preprod-url-check/1"})
with urlopen(request, timeout=20) as response:
    body = response.read(512_000).decode("utf-8", errors="replace")
    if response.status != 200 or "Предвестник" not in body:
        raise SystemExit("Configured Mini App URL did not serve the expected shell")
print(f"PREPROD_MINIAPP_URL_OK {url}")
