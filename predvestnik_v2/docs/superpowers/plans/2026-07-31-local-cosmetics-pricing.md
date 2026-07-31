# Local Cosmetics Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the localhost cosmetics catalog into a reviewable proposal where price reflects both collection tier and the visual weight of a cosmetic slot.

**Architecture:** Keep `core/cosmetics.py` and `services/cosmetics.py` unchanged: their current uniform prices remain the production baseline until the owner explicitly approves a migration. Expand only `tools/preview_server.mjs` with a representative, complete Frost collection using the proposed per-slot prices. Make the client derive a collection's displayed price range and buy-all quote from actual item prices rather than assuming one fixed lineup price.

**Tech Stack:** Node.js local preview fixture, classic browser JavaScript, Puppeteer regression scripts.

## Global Constraints

- Localhost proposal only; no production catalog, database, balance, or purchase service changes.
- All prices use whole tens of `✨`; buying remains permitted without VIP.
- Preserve the current total cost of a full collection approximately; rebalance value between slots instead of inflating the economy.
- Write a failing automated test before every production behavior change.

## Proposed Price Model

Every lineup keeps its existing tier base: Forest `250`, Threshold/Frost `440`, Inferno `630`, Celestial `820`, Void `1000`, Artifact `1500` `✨`.

| Slot | Multiplier | 440✨ Frost review price | Reason |
|---|---:|---:|---|
| Title | 0.70 | 310 | A compact textual signature, important but smallest visual surface. |
| Avatar halo | 0.85 | 370 | Decorative support for the avatar, not the profile’s main surface. |
| Avatar frame | 0.95 | 420 | Persistent recognisable border around the avatar. |
| Name glow | 1.00 | 440 | Baseline social identity effect in chats and cards. |
| Profile background | 1.25 | 550 | Changes the entire profile-card surface. |
| Card effect | 1.35 | 590 | Full-card VFX with the largest visual and technical footprint. |

This keeps full-set totals close to the current uniform model while making `title < … < background < card effect` explicit. At Frost tier, a six-slot review set totals `2680✨` instead of a flat six-times-`440✨` presentation.

### Task 1: Make the client quote non-uniform collection prices

**Files:**
- Modify: `FastAPI/static/app.10.js`
- Test: `tools/verify_local_cosmetics_pricing.mjs`

- [x] Write a failing browser test for the Frost detail page, asserting the displayed range `310–590✨` and buy-all quote `2680✨`.
- [x] Run `node tools/verify_local_cosmetics_pricing.mjs` and observe that the uniform-price interface fails.
- [x] Add a small item-price/range helper in `app.10.js`; use it for overview, lineup info, detail caption, balance check and buy-all quote.
- [x] Re-run the price test and `node --check FastAPI/static/app.10.js` until both pass.

### Task 2: Provide an honest localhost catalog for review

**Files:**
- Modify: `tools/preview_server.mjs`
- Test: `tools/verify_local_cosmetics_pricing.mjs`

- [x] Expand the Frost fixture to one real Frost cosmetic per each of the six slots, with prices from the table above.
- [x] Update the local success message so it cannot report an obsolete fake total.
- [x] Re-run the pricing test and the fitting-room regression.

### Task 3: Verify and record the proposal

**Files:**
- Modify: `docs/superpowers/plans/2026-07-31-local-cosmetics-pricing.md`
- Test: `tools/verify_fitting_room.mjs`, `tools/verify_looks_no_jump.mjs`, `tools/verify_live_swatch.mjs`

- [x] Inspect Frost at 390px width: all six slots, price hierarchy, range copy, disabled buy-all state and fixed fitting-room dock.
- [x] Run syntax, price, fitting-room, navigation, motion and server-side purchase regressions.
- [x] Check off the completed steps and keep the production migration explicitly pending owner approval.
