#!/usr/bin/env python3
"""Authenticated smoke against the externally reachable isolated preprod app.

It deliberately checks the released surface, not historical routes which were
retired from the Mini App.  The session is generated locally and accepted only
by isolated-preprod configuration; no browser test cookie is public.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env.test', override=True)
from FastAPI.auth import create_session_token  # noqa: E402

base = os.environ['PREPROD_SMOKE_URL'] if os.getenv('PREPROD_SMOKE_URL') else os.environ['PREPROD_MINIAPP_URL']
base = base.rstrip('/')
parts = urlsplit(base)
if parts.scheme != 'https' or not parts.netloc:
    raise SystemExit('PREPROD_MINIAPP_URL must be an external HTTPS URL')
user_id = int(os.environ['PREPROD_ALLOWED_TG_IDS'].split(',', 1)[0])
session_token = create_session_token(user_id)


def call(path: str) -> tuple[int, dict]:
    request = Request(base + path, headers={'X-Session-Token': session_token})
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read() or b'{}')
    except HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


approved = {}
for path in ('/api/health', '/profile/me', '/hub/me', '/pets-v1/me', '/quests-v1/me', '/appearance/me'):
    approved[path] = call(path)
assert all(status == 200 for status, _ in approved.values()), {path: status for path, (status, _) in approved.items()}

health = approved['/api/health'][1]
hub = approved['/hub/me'][1]
pets = approved['/pets-v1/me'][1]
quests = approved['/quests-v1/me'][1]
assert health is not None
assert hub.get('version') == 'hub-v1'
assert hub.get('identity', {}).get('user_id') == user_id
assert pets.get('policy_version') == 'pets-v1-2026-09-13'
assert pets.get('durations') == [3, 6, 9]
assert len(quests.get('daily', {}).get('quests', [])) == 4
assert len(quests.get('weekly', {}).get('quests', [])) == 5
assert quests.get('rewards', {}).get('currency') == 'mora'

retired = {}
for path in ('/reconstruction/rhythm', '/reconstruction/weekly-case', '/vip/status', '/games2/state', '/streak/calendar'):
    retired[path] = call(path)[0]
assert all(status == 404 for status in retired.values()), retired

print('preprod smoke: external released Mini App, pets/quests and retired-route boundary OK')
