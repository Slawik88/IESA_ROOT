#!/usr/bin/env python3
"""Regression checks for the release / «Что нового» contract."""

from audit_release_whatsnew import FeedError, analyze_release, validate_feed


def entry(entry_id: str, entry_date: str = "2026-08-12", title: str = "Title"):
    return {
        "id": entry_id,
        "date": entry_date,
        "tag": "Фича",
        "title": title,
        "summary": "Summary",
        "details": ["Details"],
        "terms": [],
    }


production = [entry("old", "2026-08-01")]
local = [entry("new"), *production]
validate_feed({"updates": local}, "valid")

ready = analyze_release(local, production, ["FastAPI/static/app.css"])
assert ready.ready and ready.new_ids == ("new",), ready

missing_copy = analyze_release(production, production, ["FastAPI/static/app.css"])
assert not missing_copy.ready and "no new ids" in missing_copy.issues[0], missing_copy

backend_only = analyze_release(production, production, ["infrastructure/repositories/economy.py"])
assert not backend_only.ready and "release-relevant runtime" in backend_only.issues[0], backend_only

misplaced = analyze_release([*production, entry("new")], production, ["services/game.py"])
assert not misplaced.ready and any("production boundary" in issue for issue in misplaced.issues), misplaced

removed = analyze_release([entry("new")], production, ["FastAPI/routers/game.py"])
assert not removed.ready and any("removed production ids" in issue for issue in removed.issues), removed

try:
    validate_feed({"updates": [entry("same"), entry("same")]}, "duplicate")
except FeedError:
    pass
else:
    raise AssertionError("duplicate update id was accepted")

print("OK: release / whats-new contract blocks missing, misplaced and destructive feeds")
