#!/usr/bin/env python3
"""Block a release when user-facing code changed but «Что нового» did not.

The report deliberately combines two sources: a Git diff from the declared
production revision and the currently served production updates feed. It does
not decide release copy for the owner; it makes missing analysis visible.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
)
PROJECT_PATH = PROJECT_ROOT.relative_to(REPO_ROOT).as_posix()
DEFAULT_PRODUCTION_URL = (
    "https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik/updates.json"
)
REQUIRED_TEXT = ("id", "date", "tag", "title", "summary")
RELEASE_RELEVANT_PREFIXES = (
    "FastAPI/",
    "bot/",
    "core/",
    "infrastructure/",
    "scripts/",
    "services/",
)
RELEASE_RELEVANT_EXCLUSIONS = (
    "FastAPI/static/updates.json",
    "tests/",
    "tools/",
    "docs/",
)


class FeedError(ValueError):
    """The updates feed violates its release contract."""


@dataclass(frozen=True)
class ReleaseAnalysis:
    issues: tuple[str, ...]
    warnings: tuple[str, ...]
    new_ids: tuple[str, ...]
    changed_historical_ids: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.issues


def validate_feed(payload: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("updates"), list):
        raise FeedError(f"{label}: root must contain an updates list")
    updates = payload["updates"]
    seen: set[str] = set()
    previous: date | None = None
    for index, item in enumerate(updates):
        where = f"{label}: updates[{index}]"
        if not isinstance(item, dict):
            raise FeedError(f"{where} must be an object")
        for field in REQUIRED_TEXT:
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise FeedError(f"{where}.{field} must be a non-empty string")
        if item["id"] in seen:
            raise FeedError(f"{label}: duplicate id {item['id']!r}")
        seen.add(item["id"])
        try:
            current = date.fromisoformat(item["date"])
        except ValueError as exc:
            raise FeedError(f"{where}.date is not YYYY-MM-DD") from exc
        if previous is not None and current > previous:
            raise FeedError(f"{label}: updates are not newest-first at {item['id']!r}")
        previous = current
        details = item.get("details")
        if not isinstance(details, list) or not details or not all(
            isinstance(value, str) and value.strip() for value in details
        ):
            raise FeedError(f"{where}.details must be a non-empty string list")
        if "terms" in item and not isinstance(item["terms"], list):
            raise FeedError(f"{where}.terms must be a list")
    return updates


def is_release_relevant(project_relative_path: str) -> bool:
    if project_relative_path in RELEASE_RELEVANT_EXCLUSIONS:
        return False
    if project_relative_path.startswith(RELEASE_RELEVANT_EXCLUSIONS[1:]):
        return False
    return project_relative_path.startswith(RELEASE_RELEVANT_PREFIXES)


def analyze_release(
    local_updates: list[dict[str, Any]],
    production_updates: list[dict[str, Any]],
    changed_paths: list[str],
) -> ReleaseAnalysis:
    local_by_id = {item["id"]: item for item in local_updates}
    production_by_id = {item["id"]: item for item in production_updates}
    new_ids = tuple(item["id"] for item in local_updates if item["id"] not in production_by_id)
    missing_ids = tuple(item["id"] for item in production_updates if item["id"] not in local_by_id)
    changed_history = tuple(
        item_id
        for item_id, production_item in production_by_id.items()
        if item_id in local_by_id and local_by_id[item_id] != production_item
    )
    release_paths = [path for path in changed_paths if is_release_relevant(path)]
    issues: list[str] = []
    warnings: list[str] = []

    if missing_ids:
        issues.append("local feed removed production ids: " + ", ".join(missing_ids))
    if release_paths and not new_ids:
        issues.append(
            f"{len(release_paths)} release-relevant runtime files changed, but local/live feeds have no new ids"
        )
    if new_ids and production_updates:
        boundary = next(
            (index for index, item in enumerate(local_updates) if item["id"] in production_by_id),
            len(local_updates),
        )
        misplaced = [
            item["id"]
            for item in local_updates[boundary:]
            if item["id"] not in production_by_id
        ]
        if misplaced:
            issues.append("new ids must be above the production boundary: " + ", ".join(misplaced))
    if changed_history:
        warnings.append(
            "historical production entries changed and require explicit review: "
            + ", ".join(changed_history)
        )
    return ReleaseAnalysis(
        issues=tuple(issues),
        warnings=tuple(warnings),
        new_ids=new_ids,
        changed_historical_ids=changed_history,
    )


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def changed_files(base: str) -> list[tuple[str, str]]:
    git_output("rev-parse", "--verify", f"{base}^{{commit}}")
    raw = git_output("diff", "--name-status", f"{base}..HEAD", "--", PROJECT_PATH)
    rows: list[tuple[str, str]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, repo_path = parts[0], parts[-1]
        prefix = PROJECT_PATH + "/"
        rows.append((status, repo_path[len(prefix) :] if repo_path.startswith(prefix) else repo_path))
    return rows


def load_remote_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "predvestnik-release-audit/1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise FeedError(f"production feed returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def render_report(
    *,
    base: str,
    head: str,
    production_url: str,
    rows: list[tuple[str, str]],
    commits: list[str],
    analysis: ReleaseAnalysis,
) -> str:
    status = "READY" if analysis.ready else "BLOCKED"
    release_paths = [path for _, path in rows if is_release_relevant(path)]
    lines = [
        "# Predvestnik release / «Что нового» audit",
        "",
        f"**Status: {status}**",
        "",
        f"- Candidate: `{head}`",
        f"- Declared production base: `{base}`",
        f"- Live feed: `{production_url}`",
        f"- Commits in candidate: {len(commits)}",
        f"- Changed files: {len(rows)} ({len(release_paths)} classified as release-relevant runtime)",
        f"- New update IDs: {', '.join(analysis.new_ids) if analysis.new_ids else 'none'}",
        "",
        "## Blocking findings",
        "",
    ]
    lines.extend(f"- {issue}" for issue in analysis.issues)
    if not analysis.issues:
        lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in analysis.warnings)
    if not analysis.warnings:
        lines.append("- None.")
    lines.extend(["", "## Commits", ""])
    lines.extend(f"- `{commit}`" for commit in commits)
    if not commits:
        lines.append("- None.")
    lines.extend(["", "## Changed files", ""])
    lines.extend(
        f"- `{status_code}` `{path}`{' — release-relevant runtime' if is_release_relevant(path) else ''}"
        for status_code, path in rows
    )
    if not rows:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Required human pass",
            "",
            "- Read the diff by subsystem; do not turn commit messages into player copy mechanically.",
            "- Exclude dev-only/feature-flagged work and describe only behavior shipped in this release.",
            "- Re-run this audit after updating `FastAPI/static/updates.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/master")
    parser.add_argument("--production-url", default=DEFAULT_PRODUCTION_URL)
    parser.add_argument("--production-file", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    local_payload = json.loads((PROJECT_ROOT / "FastAPI/static/updates.json").read_text(encoding="utf-8"))
    production_payload = (
        json.loads(args.production_file.read_text(encoding="utf-8"))
        if args.production_file
        else load_remote_json(args.production_url)
    )
    local_updates = validate_feed(local_payload, "local")
    production_updates = validate_feed(production_payload, "production")
    rows = changed_files(args.base)
    commits_raw = git_output(
        "log", "--format=%h %s", f"{args.base}..HEAD", "--", PROJECT_PATH
    )
    commits = commits_raw.splitlines() if commits_raw else []
    analysis = analyze_release(
        local_updates,
        production_updates,
        [path for _, path in rows],
    )
    report = render_report(
        base=args.base,
        head=git_output("rev-parse", "HEAD"),
        production_url=str(args.production_file or args.production_url),
        rows=rows,
        commits=commits,
        analysis=analysis,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0 if analysis.ready else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FeedError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"RELEASE AUDIT ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
