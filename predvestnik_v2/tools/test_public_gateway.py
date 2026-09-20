#!/usr/bin/env python3
"""Deployment contract for the shared public DigitalOcean web process."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
sys.path.insert(0, str(REPOSITORY))

from predvestnik_v2.FastAPI.public_gateway import public_location, upstream_target


assert upstream_target("/predvestnik")[1:] == ("/", "/predvestnik")
assert upstream_target("/predvestnik/")[1:] == ("/", "/predvestnik")
assert upstream_target("/predvestnik/api/health")[1:] == (
    "/api/health", "/predvestnik",
)
assert upstream_target("/")[1:] == ("/", "")
assert upstream_target("/news")[1:] == ("/news", "")

assert public_location("/auth", prefix="/predvestnik") == "/predvestnik/auth"
assert public_location("/predvestnik/auth", prefix="/predvestnik") == "/predvestnik/auth"
assert public_location("https://example.test/auth", prefix="/predvestnik") == "https://example.test/auth"

procfile = (REPOSITORY / "Procfile").read_text(encoding="utf-8")
startup = (ROOT / "tools" / "start_combined_web.sh").read_text(encoding="utf-8")
assert "web: sh predvestnik_v2/tools/start_combined_web.sh" in procfile
assert "worker: cd predvestnik_v2 && python -m bot" in procfile
assert "127.0.0.1 -p 18081" in startup
assert "FastAPI.main:app --host 127.0.0.1 --port 18082" in startup
assert "predvestnik_v2.FastAPI.public_gateway:app" in startup
assert 'export ROOT_PATH="/predvestnik"' in startup

print("public gateway deployment contract: OK")
