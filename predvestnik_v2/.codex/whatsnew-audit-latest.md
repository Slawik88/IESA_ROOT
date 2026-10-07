# Predvestnik release / «Что нового» audit

**Status: READY**

- Candidate: `54dd21dc9989e7652c66a59333d3e9392389001d`
- Declared production base: `origin/master`
- Live feed: `https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik/updates.json`
- Commits in candidate: 0
- Changed files: 14 (2 classified as release-relevant runtime)
- New update IDs: 2026-09-20-rhythm-ranking-repair

## Blocking findings

- None.

## Warnings

- None.

## Commits

- None.

## Changed files

- `??` `.codex/CURRENT_STATE.md`
- `??` `.codex/MEMORY_INDEX.md`
- `??` `.codex/design-audit-2026-09-02/01-profile.png`
- `??` `.codex/design-audit-2026-09-02/02-more.png`
- `??` `.codex/design-audit-2026-09-02/03-more-after.png`
- `??` `.codex/design-audit-2026-09-02/04-more-live.png`
- `??` `.codex/release-whatsnew.md`
- `??` `.codex/whatsnew-audit-latest.md`
- `??` `AGENTS.md`
- `M` `FastAPI/static/updates.json`
- `M` `infrastructure/repositories/rhythm_v2.py` — release-relevant runtime
- `M` `services/rhythm_v2.py` — release-relevant runtime
- `M` `tools/test_rhythm_v2_pg.py`
- `M` `tools/test_rhythm_v2_transport_client.py`

## Required human pass

- Read the diff by subsystem; do not turn commit messages into player copy mechanically.
- Exclude dev-only/feature-flagged work and describe only behavior shipped in this release.
- Re-run this audit after updating `FastAPI/static/updates.json`.
