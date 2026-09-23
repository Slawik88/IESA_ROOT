#!/usr/bin/env python3
"""Read-only production HTTP boundary check for a known Predvestnik release."""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


DEFAULT_BASE = "https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik"


def fetch(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Predvestnik-release-audit/1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument(
        "--profile",
        choices=("current", "rollback-f8da5d43"),
        default="current",
        help="Release-specific static markers to require.",
    )
    args = parser.parse_args()
    base = args.base.rstrip("/")

    expected = {
        "/": 200,
        "/api/health": 200,
        "/api/ready": 200,
        "/legal/tos": 200,
        "/legal/privacy": 200,
        "/static/app.js": 200,
        "/static/app.css": 200,
        "/updates.json": 200,
        "/profile/me": 401,
        "/payments/zarniki/packages": 401,
        "/hub/me": 401,
        "/rhythm-v2/leaderboard/normal": 401,
        "/minesweeper-v2/leaderboard/easy": 401,
        "/mafia-v1/me": 401,
        "/profile/1": 404,
        "/gacha/info": 404,
        "/auction/": 404,
        "/exchange/crypto": 404,
        "/battle_pass/status": 404,
        "/games2/retire-active": 404,
    }
    bodies: dict[str, str] = {}
    failures: list[str] = []
    for path, wanted in expected.items():
        status, body = fetch(base + path)
        bodies[path] = body
        if status != wanted:
            failures.append(f"{path}: expected {wanted}, got {status}")

    marker_profiles = {
        "current": {
            "/": ("Обновление ещё не вышло",),
            "/updates.json": ("2026-09-23-mobile-controls-and-payments-check",),
            "/static/app.css": ("flex: 1 1 auto; overflow: hidden", "width: 44px; height: 44px"),
            "/static/app.js": ("В продакшене пополнение работает", "openZarnikiTopup"),
        },
        "rollback-f8da5d43": {
            "/": ("Предвестник в активной разработке",),
            "/updates.json": ("2026-09-23-legacy-route-cleanup",),
        },
    }
    markers = marker_profiles[args.profile]
    forbidden_markers = {
        "current": {},
        "rollback-f8da5d43": {
            "/": ("Обновление ещё не вышло",),
            "/updates.json": ("2026-09-23-mobile-controls-and-payments-check",),
        },
    }[args.profile]
    for path, required in markers.items():
        for marker in required:
            if marker not in bodies.get(path, ""):
                failures.append(f"{path}: missing release marker {marker!r}")
    for path, forbidden in forbidden_markers.items():
        for marker in forbidden:
            if marker in bodies.get(path, ""):
                failures.append(f"{path}: contains marker from a newer release {marker!r}")

    result = {
        "base": base,
        "profile": args.profile,
        "checks": (
            len(expected)
            + sum(len(values) for values in markers.values())
            + sum(len(values) for values in forbidden_markers.values())
        ),
        "failures": failures,
        "status": "pass" if not failures else "fail",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
