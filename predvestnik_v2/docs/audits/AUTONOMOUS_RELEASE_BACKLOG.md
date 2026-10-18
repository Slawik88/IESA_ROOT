## Owner revision 2026-10-18 — admin mark review queues (item 8 complete)

People search now has a staff-without-badge queue, filters with/without each
manual regalia, with/without any manual regalia, bounded 30-row pages and totals.
Bulk selection spans pages and stops at 50; existing per-recipient permission,
reason and audit checks remain the mutation boundary. Deleted accounts are
excluded, tester rank is not mistaken for helper, creator override is respected.

Evidence: PostgreSQL proof exercises 37 synthetic players, non-overlapping pages,
role matching, deleted accounts, assigned/missing marks and literal wildcard
search. Browser proofs at 320/390 verify real staff authentication, dropdown,
pagination, no JS errors and no horizontal overflow; screenshots inspected.
Admin UI contract, JS syntax and whitespace pass. The broader existing people
test stops at unchanged Cyrillic ILIKE matching under this C-locale test cluster
(same result on a fresh separate test DB); not counted as a passing full gate.
Read-only critique covered permissions, bulk guards and pagination requirements.

## Owner revision 2026-10-18 — dock density (item 4 complete)

Dock targets now have a consistent 56px pitch and 48px minimum height, without
growing to 68px on wider devices. The dock fits its contents up to the viewport
width, avoiding empty trailing space when destinations are disabled. Labels,
focus outlines, safe-area clearance and horizontal navigation remain intact.
Three real-browser scenarios at 320/390/430 pass without warnings; the 390px
screenshot was inspected. Existing shell tap-target contract passes.

## Owner revision 2026-10-18 — cosmetic boundaries (item 3 complete)

Replaced narrow fixed-pixel edge masks with proportional multi-stop fades on the
shared decorative scene layer. Large silhouettes and particles dissolve across
roughly one third of each edge; avatar, nickname, titles and controls remain
unmasked. No blur, new animation or runtime work was introduced.

Evidence: six real-browser profile/Looks scenarios at 320/390/430 pass with no
warnings; before/after screenshots in .local/ui-before and .local/ui-after-edges
were inspected. Skins visual contract and whitespace checks pass. A first second-
port smoke attempt timed out during app startup; a sequential rerun on the usual
stand completed all six scenarios.

## Owner revision 2026-10-18 — exchange dock entry (item 5 complete)

The existing flag-controlled exchange destination now follows Games, rather than
being near the end of the horizontal dock. It remains hidden when the server
disables the exchange. Existing shell and exchange UI contracts pass.

## Owner revision 2026-10-18 — regalia logic (item 2 complete)

Unified tenure with the existing season-reward account-age lookup (earliest chat
join, membership or daily-message evidence). Own/public profiles and marks sheet
now use the same history. Marks without a supplied join date look it up rather
than treating an established account as new. Held earned marks no longer appear
in the upcoming goals; future message rows cannot qualify dynamic marks. Staff
hints use current bot_rank 0–6 instead of the retired global_rank 0–3.

Evidence: all 16 mark rules and PostgreSQL grant/revoke/sticky/history/window
tests pass, including old-message tenure with recent joined_at, membership-only
evidence, retention cleanup and future messages. Season age rules pass; the full
season-pass PostgreSQL test currently fails in unrelated quest sampling with
QuestConflict (not claimed as passing). Independent read-only critique approved
the tenure/sticky/window fix. No historical production data was fabricated.

## Owner revision 2026-10-18 — avatar recovery (item 1 complete)

Fixed six-hour negative avatar caching, stale-photo loss, one-attempt client
loading, recovered-photo loss on rerender and missing public-card hydration.
Public hydration uses opaque references, authenticates viewer and target, checks
VIP and releases the database connection before Telegram I/O. Retries are bounded;
late responses cannot update a different public card. Existing successful photos
survive a Telegram outage, and a failed first lookup is retried after 15 seconds.

Evidence: Python cache/timeout recovery test, Node transport/DOM recovery test,
real PostgreSQL pool isolation and public-reference/VIP/deleted-account proof,
ASGI static delivery, JS syntax and diff whitespace checks all pass. Read-only
subagent critique confirmed the causes and recovery boundaries.

Remaining owner scope: 2 regalia audit; 3 cosmetic edges; 4 dock spacing; 5 exchange
in dock; 6 activity chart references/performance; 7 new regalia proposals; 8 admin
mark QoL; 9 exchange visuals; 10 wallet/conversion consistency; 11 VIP stops;
12 chat administration; 13 achievements; 14 multi-item chest loot/food;
15 tap-to-reveal chest stars; 16 balanced Rhythm augments; 17 pets UX;
18 admin-chat broadcast filter; 19 complete season pass. Several have earlier
implementations on master: verify behavior before marking them complete.

## Activity chart mobile pass + one-message card (photo caption), 2026-10-18

Owner follow-up in the same worktree/branch: the chart text was hard to read from a
phone, and the chart and the card arrived as two separate messages.

Renderer, phone-first (`bot/chat/activity_graph.py`): the canvas is now 1120×960
(figsize 5.6×4.8 at DPI 200 — still a 2× render of the ~560 dp photo Telegram shows
on a phone), with every font stepped up relative to width: title 19 bold; date
window 12.5; KPI labels 12 with 17-medium values; legend 12; axis ticks 11;
footnote 11/13. The header became stacked rows — title, date window, two KPI lines
(«сегодня · динамика» / «в среднем · лучший день»), a dedicated legend row — with
the plot below and the footnote row at the bottom. All KPI, peak and y-axis numbers
use the thousands-space format; the left margin fits five-digit y labels. On the
x axis a tick closer than 5 days to the appended last tick is dropped («14.10…» and
«сегодня» no longer collide) and the last label is right-aligned so «сегодня» is
not clipped. Grid lines thinned and the bar corner radius re-measured for the
smaller canvas; the cosmos/gold/light token sets are unchanged.

Message shape (`bot/chat/profile.py`): «бот я» / «бот кто» now answer with ONE
message — the card travels as the photo caption (`answer_photo(caption=…)`, HTML)
when its visible length fits Telegram's 1024 limit (tags stripped, UTF-16 units,
emoji counted as two). A longer card, or one Telegram rejects as a caption, keeps
the old order: photo without caption, then the text card. No chart — text only,
as before.

Evidence: `tools/test_activity_graph.py` PASS — three themes, both header branches
(with and without «динамика»), cache hit issues no second SQL, three concurrent
renders, plus new caption checks: caption fits → single photo message with
parse_mode=HTML; over-limit caption → photo + separate text; caption rejected →
same fallback; no chart → text only; the length helper strips tags and counts
UTF-16. `py_compile` PASS for all four touched files. The design reference now
renders the production module itself, so the PNG cannot drift:
`docs/design-refs/render_activity_polish_final_preview.py` →
`docs/design-refs/img/activity-polish-final.png` (1120×960). The widened test also
caught a regression during this wave: `_row` had lost its width return, crashing
every header that has «динамика»; fixed before commit.

Gate: not re-run in full (renderer + a single send path, same as the wave above).
`tools/test_chat_bot_pg.py` (pre-existing red) drives the profile flow with a fake
bot that has no `answer_photo`; both photo attempts sit inside the existing
try/except, so that harness still ends in the same `reply(text)` and its red is
unchanged. Live Telegram smoke remains on the owner's side (no bot token here):
verify the single chart+card message, a long-card fallback, and phone readability.

## Activity chart polish and info layer («бот я / бот кто»), 2026-10-18

Follow-up cosmetics + content wave on the chart from the entry below (owner tasks 6/18),
same worktree and branch. The renderer `bot/chat/activity_graph.py` keeps the same data
source and one-query discipline: `get_graph` now pulls a double window with a single
`daily_counts` call — the fresh 30 days for the chart, the previous 30 for the «динамика»
figure, compared by daily averages so partial history cannot lie.

Visual polish (existing elements; cosmos default, gold/light carry the same token set):
brand font Onest — three static weights plus the OFL license bundled in
`bot/chat/assets/fonts`, registered once per process, silent fallback to the default font
when files are missing; rounded gradient bars with a top light; y-ceiling that hugs the
data (660 → 700 instead of 800, no empty headroom, grid steps unchanged); fine dotted
grid without the duplicate zero line; edge-fading baseline; full-figure background
gradient with dithering (keeps Telegram's JPEG step from banding on the gradient);
two-tone subtitle; whisper weekend bands, measured +4/255 on dark themes and −5/255 on
light, explained by a legend item; legend rework — mini-bar swatch plus a dashed
«среднее» sample.

Info layer, all computed from the already fetched counts (zero extra queries): top row
«сегодня · динамика · в среднем · лучший день»; dashed average line and a peak-value
label above the tallest bar; «сегодня» as the last x label; bottom footnote
«всего · активных дней · серия». Renders are 2× (2000×1120, ~150 KB PNG) so phone
screens get crisp text; the render still runs in a worker thread behind the per-day
cache, ~0.5 s warm once per player and day.

Evidence: `tools/test_activity_graph.py` PASS (unchanged contract — three themes, day
series math, cache hit issues no second SQL, three concurrent renders); `py_compile`
PASS; smoke renders of all three themes are valid PNGs. Design reference (script + PNG,
verified to run against the bundled fonts):
`docs/design-refs/render_activity_polish_final_preview.py`,
`docs/design-refs/img/activity-polish-final.png`.

Gate: not re-run in full for this renderer-only wave — the chart suite is green and no
other suite depends on the renderer's styling; pre-existing gate reds are unchanged
(list and root causes in the entry below). Live Telegram smoke was not possible on this
machine (no bot token) — post-deploy check on the owner's side.

## Player activity chart above the card and broadcast filter for admin chats, 2026-10-18

Owner tasks 6 and 18 implemented in worktree `predvestnik-activity-broadcast`
(branch `codex/predvestnik-activity-broadcast`, committed and pushed to master).

«Бот я» / «бот кто» now answer with a real chart image above the text card: 30-day daily
activity from `daily_user_stats` (current chat in groups, all chats in DM). Rendering is
`bot/chat/activity_graph.py` (matplotlib, already a pinned dependency): cosmos site theme
by default, all styling kept in one `THEMES` dict for the later cosmetics pass. No
per-request matplotlib import cost: `prewarm()` at bot startup, render in a worker thread,
per-(player · chat · day) cache; the card arrives alone when there is no activity or the
chart fails — the chart never blocks it. Pyplot-free rendering
(`Figure` + `FigureCanvasAgg`) keeps parallel cache-fill renders thread-safe.

Broadcast segment «chats» gained a `chat_kind` filter — all chats / 🏠 main chats without
admin chats / 🛡 admin chats only — derived from `chat_links` (unique index gives
one-row-per-chat joins), validated with a 400, shown in the audience line, and marked 🛡
in the admin chat picker; recipients, preview count and scheduled/resumed sends share the
same filter.

Evidence: `tools/test_activity_graph.py` PASS (three themes render valid PNGs, day series
math, cache hit issues no second SQL, three concurrent renders); `py_compile` and
`node --check` PASS. Read-only critic audit of the whole wave: no production blockers or
majors; it found and we fixed one release-gate regression
(`tools/test_bot_admin_promo_pg.py` expected the exact `/chats` dict without the new
`admin` key) plus the renderer hardening above. To run on a scratch PostgreSQL:
`tools/test_bot_admin_review_pg.py` (new chat_kind block), `tools/test_bot_admin_promo_pg.py`,
`tools/test_chat_bot_pg.py`.

Release gate (`tools/run_preprod_tests.ps1`, scratch cluster, project `.venv`): total=194
passed=164 failed=30 — clean master dab61401 fails the identical 30 under the same
conditions, so this wave adds no reds (its own `test_activity_graph.py` is green in the
gate; promo and review behave as documented above when run per-suite on a fresh DB).
Still red on base and untouched here: test_account_recovery_bot.py,
test_bot_admin_chats_reports_pg.py, test_bot_admin_entry_pg.py, test_bot_admin_matrix_pg.py,
test_bot_admin_metrics_pg.py, test_bot_admin_owner_pg.py, test_bot_admin_people_pg.py,
test_bot_admin_player_tools_pg.py, test_bot_admin_promo_pg.py, test_bot_admin_reports_pg.py,
test_bot_admin_review_pg.py, test_bot_admin_security_pg.py, test_bot_feature_switches_pg.py,
test_bot_health_pg.py, test_chat_bot_pg.py, test_chat_bots_pg.py, test_chests_v1_mixed_pg.py,
test_current_game_docs.py, test_game_seasons_pg.py, test_inventory_v3_contract.py,
test_mafia_v1_pg.py, test_mafia_v1_sim_pg.py, test_mechanics_community_pg.py,
test_member_tags_pg.py, test_pets_v1_pg.py, test_presence_v1_pg.py,
test_profile_query_budget_pg.py, test_profile_release_experience.py, test_skin_scenes.py,
test_player_exchange_recovery_ui.js. Dominant cause: the gate runs every suite against one
shared database while the newer suites are documented as «пустая тестовая БД» — fixed ids
collide (`users(1001)` → `users_pkey`, `(user_tg_id, chat_tg_id)=(2001,-100)`, relation
`purge_start_receipt`), and leaked chat_settings/chat_links state changes endpoint payloads
(`KeyError: 'settings'/'players'/'sections'`). Independently: the review suite's journal
page check is TZ-dependent (PGAdapter coerces aware datetimes to naive UTC; asyncpg binds
them as Europe/Berlin local, so the `before` cursor lands two hours in the past — a UTC
server is unaffected); test_chat_bot_pg/test_chat_bots_pg mock the bot as member/False
before the new live Telegram bot-rights check of purge (message_id / callback id /
`send_message` return drift too — with those locally repaired the suite reaches
`profile_flow`, the «бот я» chart path); the preprod allowlist (101, 202) blocks suites that
talk as other ids («Тестовый стенд закрыт для этого аккаунта»); Windows path length breaks
test_skin_scenes.py; the two long-known UI reds stay. A dedicated gate/shared-DB repair
wave is needed before the suite can go green.

## Lazy schema installation can no longer race itself; Rune Rhythm settlements survive, 2026-10-18

Production 2026-10-18 11:34 logged DuplicateObjectError: trigger
"quest_v1_reward_receipts_append_only" for relation "quest_v1_reward_receipts" already exists, and
/quests-v1/me answered 500: after a dyno restart the first requests run ensure_tables in parallel,
and the DROP TRIGGER + CREATE TRIGGER pair cannot survive that. The new
tools/test_ensure_tables_race_pg.py reproduces the incident and its siblings — "tuple concurrently
updated" from CREATE OR REPLACE FUNCTION and a deadlock on AccessExclusiveLock — by dropping each
append-only trigger and running three parallel installs: the old code fails, the new code leaves
exactly one trigger per table. A finished Rune Rhythm run settles through
quests.record_metric -> chests_v1.ensure_tables, so this collision could roll a settlement back and
cut a player's game short; that is why the fix is on master (81cb09b8).

Eight repositories (achievements, chests, echo_shards, gifts, pets, quests, rhythm, shop) now create
their append-only triggers through a guarded DO block that swallows a create/create race, and they
follow the vip_v2 installer idiom: a catalog-only _schema_ready lookup answers an installed database
without any DDL, otherwise one advisory lock (hashtextextended('ensure_tables:<repo>',0)) wraps the
whole install. chests_v1 no longer runs the reveal-delivery seal migration on every game finish — it
used to drop the append-only trigger, scan the reveal history and take ACCESS EXCLUSIVE locks; the
fail-closed contract stays (a removed NOT NULL / index / FK re-runs the migration and still refuses
an unbackfillable row). Verified on PostgreSQL 17 (127.0.0.1:5437) against the disposable preprod
DSN: test_quests_v1_pg, test_chests_v1_pg, test_chests_v1_mixed_pg, test_chest_keys_multi_pg,
test_chest_key_tiers_pg, test_rhythm_v2_pg, test_achievements_v1_pg, test_pets_v1_pg,
test_pets_v1_rollout_guard_pg, test_pet_routes_v1_pg, test_shop_v1_pg, test_gifts_v2_pg,
test_echo_shards_v1_pg, test_season_pass_pg, test_vip_v2_pg, test_readiness_pg and
test_ensure_tables_race_pg all pass. Follow-up: the remaining lazy-DDL repositories that are not on
the game path (balance_events, divorce_v1, marks_v1, chat_module_audit) still create functions and
tables per request without an installer lock — give them the same _schema_ready + advisory-lock
treatment when they are next touched.

## Owner UI wave: dock density, Exchange in the dock, seamless skin edges, 2026-10-18

Three owner reports from the live release fixed on origin/master (54bbbef3). The dock now carries
eleven destinations: item pitch clamp(55px,(100vw-24px)/6.6,68px) with 10px labels — 6.7 visible on
390px instead of 5.5, the longest label «Инвентарь» (52.5px in the bundled Onest) never ellipsizes
at 320/360/390/430, and the 68px cap fills the 760px dock exactly on wide screens (measured 0px
slack at 900px; the previous ten-tab spec was 74px/11px). «Биржа» moved out of the «Ещё»→«Рынок»
row into the dock between «Кошелёк» and «Ещё»; the same element id keeps syncPlayerExchangeEntry()
and the CM2 path intact. With the flag off the tab is display:none (ten slots) and a deep link to
exchange-v1 opens the page while «Ещё» carries the highlight; a deeplink that lands before
/profile/me now hands the highlight to the tab as soon as it appears (shared _dockActive, verified
live: hidden→visible handoff and the restored state). Skin stage: .ap-scene-clip dissolves on all
four sides (vertical 30/44px, horizontal 34px, mask-composite intersect) so the scene no longer ends
in the straight frame the owner reported; the VIP store preview card keeps its previous short
gradient explicitly. Evidence: shell / navigation-dots / whatsnew / ui-smoke / skins-visual /
appearance / curated-looks contracts PASS; headless Chromium screenshots of the dock at
320/360/390/430 and 900px, the exchange tab gated on and off, the pumpkin and chrono scenes and the
VIP preview card; read-only critic pass over the diff — no blocker or major, its two findings (the
highlight race above and the wide-screen underfill) fixed in this wave. Still red on base and
untouched here: tools/test_inventory_v3_contract.py (eight-tab era) and
tools/test_player_exchange_recovery_ui.js (its vm context lacks window).

## Exchange v2 — live release and final design, 2026-10-17

Production activation completed: six system coins; v2 and shorts enabled, v1 disabled.
Owner-authorised one-time issuance120000Mora recorded once; independent read-only
reconciliation: issuances1, gap_micro0. Autonomous tick advancement observed live.
Public HTTP41 checks +8 exchange asset/auth boundaries PASS. No player funds used
for verification. No additional issuance or automatic reserve refill.

Final UI wave uses existing Predvestnik skin tokens and UI UX Pro Max:
compact wallet/market search and groups; separate holdings/shorts with exit values
and position results; existing short visible and closable from coin page even when
new entry is disabled; explicit creator-cost exclusion. One primary confirmation,
loading/recheck states, actual six-place server amounts and pending-request recovery.
Creation tariffs explain starting valuation and show selected icon/tariff correctly.
Chart uses consistent local timezone, unique time labels, native keyboard cursor,
nearest published time and preserved focus across live updates. No economic rules
changed. Read-only critic review found no blocking regressions; two focus/time
selection polish findings fixed. Node chart/preview/recovery, ASGI delivery/public
routes and shell contracts PASS; real browser320/390/430 verification recorded in
local visual evidence folder. Final design deploy is verified after master push.

Second design wave: segmented market/positions tabs, token-based wallet surface,
explicit market direction counts, outlined SVG favourites, two-row coin actions,
portfolio exit valuation computed with BigInt and shown as approximate2decimals.
Short valuation includes returned collateral and is labelled accordingly; total
is not profit. Exact6place confirmation is unchanged. Context-preserving refresh
retains search/caret and ignores stale navigation responses. Browser320 measured
axis labels12CSSpx, no horizontal overflow. UI UX Pro Max recommendations applied
to heading scale, single primary CTA, async feedback, native controls and tokens.
Owner clarification: wallet caption changed to «Ваш баланс · Мора».
Node3suites, ASGI/static/shell and read-only critic PASS.

Wallet transparency follow-up: exchange previously displayed spendable Mora as
if it were the full wallet. The read-only payload now returns total/reserved/free
from one snapshot; the UI shows «В кошельке · Мора» and a conditional split.
Trading still spends only the free amount. Regression1094total/200hold/894free
passes on real PostgreSQL without mutating the hold. A reported historical
processing duel exposed the old retirement gap. Narrow offline recovery tool
requires reviewed identities/stake, age>30days, unambiguous one-sided reserve,
no other liabilities/settlement, locked rechecks, audit and unchanged wallets.
Default is read-only; no automatic cleanup. PG proofs include refusal, rollback,
concurrent exact replay and no currency issuance.

Historical checkpoints below predate this live release.

## Exchange v2 recovery checkpoint — 2026-10-17

Catalogue cap concurrency/read truncation, explicit owner-approved zero-Mora dust
exit, stale quote/create-preview race and duplicate HTTP Content-Type are resolved
locally. Evidence:15core tests, real PostgreSQL race/rollback/replay/dust/overflow
suite and Node deferred-preview/header tests PASS; independent read-only review
PASS. Actual browser quote now renders explicit zero outcome and confirmation.
Public activation remains closed. Before release: fund the120000Mora bootstrap
from an authorised real source, prove HTTP isolation/flags and unknown-POST recovery,
reconcile latestmaster UI. This is a recovery checkpoint, not a release.

# Predvestnik V2 — Release Backlog (fresh start)

**Created:** 2026-08-29
**Scope:** current code only. Historical specifications, plans, audits and visual evidence were intentionally removed at the owner's request.

## EXCHANGE-V2-20261017 — Codex takeover; pure kernel verified, integration pending

Owner delegated implementation choices to Codex in this side conversation.
The old R/U-linked price proposal is superseded by `docs/COIN_MARKET_V2_MODEL.md`;
source spec now records delegation without granting public activation.
Implemented isolated `core/coin_market_v2.py`: server-only HMAC price path,
fixed supply, funded maximum long claims, prefunded worst-case short gaps,
explicit cash-conservation witnesses and creation valuation (no wallet writes).
14 boundary/adversarial tests, Ruff and core MyPy pass. Simulation seed 20261017
passes 100000 two-hour paths (2400000 ticks), 555309 exits and 1000 restarts;
256 seven-day paths add 516096 ticks. Final genesis formula is covered separately
by all nine contribution/tariff boundary cases after its adjustment.

Real counterexample: ten perfectly timed 1000-Mora floor-to-ceiling round trips
exhaust new-entry headroom of a 20000-Mora reserve; accepted claims still close.
Release must calibrate funding/demand; finite capital is not self-replenishing.
No SQL/API/browser/concurrency proof yet; no independent agent review in this side
conversation. No flags, production data, v1 writers or UI changed. Next: durable
PostgreSQL receipts, transaction/ownership/replay tests and scheduler contracts;
then API/UI. Check production v1 obligations read-only before any transition.

## UIUX-20261017-nav10 — compact owner-approved direction

Owner increased scope from7 to10 destinations, rejected a two-row prototype,
then requested less height and a restrained design. Final: one swipeable row,
54px tall,10 controls (9 pages + wallet dialog). Order: Profile/Games/Pets/
Quests/Looks/Chests/Inventory/Top/Wallet/More. Buttons >=64x48; labels11px,
icons20px. Current destination has only ink/accent and a short top line.
No nested selected pill or identity backdrop. More unread aggregation excludes
primary pages. _dockReveal scrolls only the navigation track and respects reduced
motion. Keyboard Tab/ShiftTab reach both ends without moving the page vertically.
Body/scoped-screen/banner/toast clearance uses --v3-dock-clear to match height.
Two-row and62px snapshots are intermediate diagnostics, not final design.
Tests: navigation/unread/reveal, shell, screen openers, static ASGI direct/prefix.
Read-only critic: no blockers; browser review covers320/390/430 and wallet closure.
Evidence: nav10-slim-final-{320,390,430}.png under the existing evidence folder.

## UIUX-20261017-nav7 — owner correction

Owner requested removal of the dark identity patch and 6–7 dock destinations.
Removed the blurred identity pseudo-background; text has only a tight glyph
shadow. Seven directions: Profile/Games/Pets/Quests/Looks/Chests/More. Top stays
in More. Primary work/play routes first; cosmetic/reward routes next. More unread
aggregation excludes direct primary tabs. At320 dock uses308px: 7x44px hit areas,
54px high. All labels visible, no inactive-label hiding; narrow labels10px.
At390/430 labels11px. Mobile screen review passed all3widths; real direct Chests
navigation and active state verified without buying/opening a chest.
Read-only critic: no blockers; label concern addressed and screenshot-verified.
Node navigation, shell and screen contracts passed. No economy/API changes.
Evidence: nav7-final-{320,390,430}.png in existing local evidence directory.
The prior five-tab hierarchy below describes the previous released wave.

## UIUX-20261017 — audit fixes, waves 1–2 (reviewed; master integration)

Branch `codex/ui-ux-fixes`, base `origin/master` fcecff0d. Owner approved fixes
after the global audit (68 captured states, 44 destinations). UI UX Pro Max
used for recovery, accessible controls and visual hierarchy.

- Inventory uses `pet_v2_state` while `pets_v2` is enabled, keeps the v1 read
  model while disabled, and never creates/migrates progress. V2 talismans are
  included; old active-pet selection is not presented as current. Cards/jokers
  retained from v1 are identified as unused in the Trail.
- Root cause of the VIP dead end: current VIP router was absent from `main.py`.
  Register the single-product contract at `/vip-v2` and update the client and
  store shutdown map. Retired `/vip/*` remains unreachable. Existing prices,
  user lock, action IDs, ledger debits and receipts are unchanged. Insufficient
  balance maps to 409. Separate read failures preserve a labelled last-known
  status with retry/help, hide writes until refreshed, reject stale responses.
  The daily mission displays the server-provided number of keys.
- Admin switches show the current state, scope and accessible name. Native
  keyboard focus is visible; hit areas are 46x44. Confirmation, POST payload,
  inheritance and failed-write rollback are unchanged and behaviour-tested.
- Wallet amount/currency have visible associated labels. Hint sheets use one
  primary action. Track/trial recommendations do not claim a unique best pet
  on tied scores, or any best trial pet at zero matches. Trial copy explains
  the instant check and retained pet/energy without changing the mechanics.
- Quest rewards use words and wrap as whole values. Follow-up DOM inspection
  did NOT confirm horizontal overflow in audit F09: the small key glyph was
  hard to recognise. This is a clarity fix, not a proven numeric truncation.

Checks passed: inventory PostgreSQL (v1/v2 divergence, absent state, no writes,
flags, talismans), VIP PostgreSQL (replay/concurrency/insufficient funds/daily
serialization), release routes/auth/retired URLs/store scope, inventory/Trail/
quests/shell/admin/UI-screen contracts, static ASGI delivery, Node behaviour
tests for VIP recovery, switch cancellation/rollback and tied recommendations,
JS parsing and `git diff --check`.

Browser evidence: local real server for VIP, inventory, wallet, quests and
guides; 320/390 px examples. Switch rendering/focus/hit areas checked at
320/390/430 in an isolated component fixture using the real function and CSS.
Full authenticated admin navigation is not proven: the synthetic main-app
cookie login is not accepted by the separate Telegram admin login. No live
flags, permissions, payments, player balances or moderation were changed.

Wave 2 completes the bounded UI fixes:
- Five primary destinations (Profile, Games, Quests, Pets, More), each 58x54
  at 320px. Looks/Chests/Top remain explicit rows near the top of More, with
  deep links and independent aggregated unread markers preserved.
- Cosmetic scene effects are clipped in a separate decorative layer; content,
  controls and focus are not clipped. Identity text has a soft quiet backdrop.
  Looks has compact phone previews and an expandable tier preview after its CTA.
- Pet send footer states selected pet, duration, route, energy and companion.
  Trek copy promises reward after return. Workshop level 0/1 wording explicitly
  reflects the unchanged tier-I ceiling; no economic benefit was invented.
- Mines cells >=44x44 in a locally scrollable field, coordinate labels, grid
  rows, one Tab stop, arrows/Home/End, restored focus and cancelled pan/hold.
  Opening failure survives rendering; start button is guarded while pending.
  Difficulty says “мин: 10”, not the ambiguous “10 мин”.
- Wallet header, profile and open currency sheet use one flat-over-nested read
  model; partial WebSocket events merge both shapes. Modal number patches do
  not rebuild the exchange form. Original audit did not prove financial loss
  or identify every source of stale reads; no such claim is made here.
- Admin chat-attention list is collapsed with count visible. Today is labelled
  incomplete UTC and does not show misleading percentages against a full day.
  Destructive admin mutation handlers remain hash-contract checked.
- A confirmed VIP purchase stays successful if subsequent status/profile reads
  fail. Stale VIP writes are disabled until retry; unknown POST result retains
  its action ID. No prices, rewards or ledger rules were changed.

Independent read-only critic reviewed commit 773b4889 and the wave-2 working
changes: no blocking regressions. Its missing More-row visual marker was fixed
and verified at 320/390. Critic separately reran Node and Python contracts.
Checks: six Node behaviour suites (store/admin/recommendations/Mines/wallet/nav),
shell/Trail/quest/admin/screen contracts, inventory PostgreSQL, current and
retired release routes/auth, direct and prefixed ASGI static delivery, parsing,
and diff check. Earlier VIP PostgreSQL replay/concurrency checks still apply
unchanged to this release's backend. No schema migration in this wave.

Browser: real isolated local FastAPI + synthetic account with SSS sakura_storm;
profile/More/looks/trip/Mines snapshots, 320/390/430 coverage. At 320, dock targets
58x54 and Mines cells 44.88px; arrows/End reached column9 with opened=0/71.
Evidence: C:/Users/makss/.codex/visualizations/2026/10/17/predvestnik-ui-ux-fixes/.

Remaining follow-up scope, not claimed done: native Telegram touch/screen-reader
hardware validation; full authenticated admin broadcast/cleaning final-step
journeys; player feedback on the five-tab hierarchy; economic redesign of a
workshop level that does not raise its ceiling. No real payments, broadcasts,
cleaning, moderation, flags or player balances were changed during QA.
Owner explicitly authorised master integration. Production deployment must be
verified separately from the Git push. Exchange v2 remains a separate worktree.

## QUEST-VARIETY-20261016 — additive pet quests

Implemented separately on `codex/quest-variety`, stacked on mechanics-community
6bc11bae. Seven pool entries: daily any adventure/trek/expedition/watch; weekly
three treks/two expeditions/three watches. All share `pet_journey`, so a set gets
at most one adventure task. Existing four daily/five weekly slots, reward tables,
VIP rules, reroll quotas and policy version are unchanged. Existing progress is
preserved; normal new assignments/rerolls draw from the expanded pool.

Daily eligibility is conservative and UTC-based: an owned valid pet can finish
an already-running job before reset minus five minutes, or there is an idle pet,
free slot and enough stored energy to start the shortest suitable job. Do not
predict rest or require food/purchases. A new watch needs twelve hours, so late
daily watch assignments are excluded unless the watch can already finish in time.
V2-specific tasks require the V2 flag; legacy generic activity support remains.

Terminal collection emits generic and matching type metrics under the same
claim timestamp and savepoint. The just-completed activity stays eligible during
that event even though it has left `open_runs`; otherwise normal availability
refresh could replace the goal before it increments. No progress for preview,
start, failed early collection, replay or a second companion. The ordinary
achievement still records one activity. Both web routing helpers lead to pets.

Read-only plan/final critique accepted. Seven relevant checks pass, including
existing quests rules/PG/bot and pets-v2 PG, new real terminal claims/paired run,
UTC Sunday/Monday boundary, late availability, unchanged reward receipts,
historical assignments and secondary-progress rollback. Static/public HTTP
checks pass. Evidence: `.local/quest-variety-checks.log`. No production changes.

## OWNER-DESIGN-20261016 — discussion only, no new game/exchange/style code

Owner selected **solo activities first**, then **link solo outings to pets**.
This agrees a direction, not implementation or reward parameters. Prepare a
concrete outing flow for joint approval: a short session with several meaningful
route/risk choices, a saved intermediate state and a clear outcome. Avoid adding
another timer or repeated tapping. Resolve whether a pet already in a passive
job may participate: blocking all such pets could recreate the original lack
of playable activities. Keep session resources separate from long-job timers;
numbers, loot budgets, limits and species advantages remain proposals until agreed.

Exchange discussion: current rules are a 2000-Zarniki creation fee, initial Mora
capital, launch auction, vesting, emission and liquidity operations. Replacing
only the fee would not satisfy the requested simpler system. The owner requested
system-defined tradable coins, buy/sell/shorts, and personal creation for 5000
Zarniki. Before replacement, agree price formation, whether personal coins are
tradable or just collectible, short collateral/liquidation/fees, and treatment of
existing balances/orders/positions. Prepare market → coin → trade → confirmation
flow. No wallets, exchange flags, existing positions or fees changed in this work.

Chat cosmetics discussion: use the existing owned/equipped skin and tier, with
one shared style registry rather than a second shop or duplicate ownership.
Agree whose skin applies to shared results, which commands receive cards, fallback
for absent/seasonal skins, and a compact text form for frequent commands. Current
`bot/chat/style.py` emits regular Telegram HTML. Structured rich messages are an
additional API option, not arbitrary CSS in existing replies; test SDK/client
compatibility before selecting that route. Source: https://core.telegram.org/bots/api#formatting-options.
Custom visuals must keep names, numbers, sanctions and action buttons readable.
No rendering/ownership changes are implemented before owner agreement.

Notion sources inspected read-only: project
https://app.notion.com/p/3e4d5683af45814a842bff53fdf3a0d6 and roadmap
https://app.notion.com/p/3e4d5683af4581658282d9d3867bc3e8. Their September/October6
milestones are historical context; current explicit owner directions take
precedence. No duplicate task pages or unsupported Done statuses were created.

## MECHANICS-COMMUNITY-20261015 — owner-selected development wave

Owner scope: pet departure forecast and saved builds; deep Rhythm feedback and
effective Rune Gift choice; finished Mafia analysis; existing family tree in the
Mini App; shared Telegram/web purge; important release posts to the official
group topic https://t.me/predvestnik_official/4 and a considered community setup.
Explicitly excluded: weekly pet trial changes, quest redesign, Minesweeper changes
and an extra purge pre-start preview. Source baseline: 8efee388.

Before each slice: inspect current reader/writer paths, compare alternatives,
obtain mandatory read-only critique, document edge cases, then implement and
verify. All development uses an isolated worktree; no unrelated root/frontend edits.

1. Pets — read-only, current-state base forecast (claim-time/day/random finds
   can change the result), shared daily cap including companion; three named
   saved drafts, explicit existing priced apply, busy donor/companion guards.
2. Rhythm — authoritative bounded per-signal analysis, honest integrity state,
   personal comparison, effective perk preview without future-rune leakage.
3. Mafia — completed-match rounds with a deliberate disclosure policy, current
   membership/participant authorization, no live-role leaks, readable timeline.
4. Family — existing relationship graph with consent/membership boundaries,
   bounded paging and clear empty/stale states; no new family economy.
5. Purge — one shared durable session for chat and site, current rights on every
   write, concurrent moderator protection, real Telegram outcome and retry states.
6. Community — verified destination/rights, important shipped changes only,
   concise screenshot-led posts, bounded annotations, durable publication state,
   no blind resend after uncertain delivery; prepare group text/topics concretely
   before any public configuration change.

Status: implementation and scoped verification complete in managed branch
`codex/predvestnik-mechanics-community`, based on production 8efee388. Mandatory
read-only final critique found no remaining confirmed blockers. Production
deployment and public group changes/posts have not been performed for this wave.

Validation: 12 focused checks pass (pure rules, real PostgreSQL, existing Rhythm
transport/Trail contracts, admin access/UI guards, public routes, static HTTP
delivery, release-feed history and terms). Changed Python files compile and JS
files parse; `git diff --check` passes. Actual mobile views of family, Mafia,
purge, pet forecast and saved builds have no document/container horizontal
overflow at 320/390/430 px. An actual local WebSocket Rhythm run records eight
correct taps and five timeouts accurately; its result is used in the explicitly
labelled example image. The creator composer saves a draft, loads the exact PNG,
and rejects publication from preprod without changing its draft state.

Counterexamples covered: preview does not create pet progression state; owned,
priced and busy-pet build guards; secret-role/history privacy and former-member
denial; child-only family; concurrent start retries and decisions; a delayed
start after completion or during a later session cannot reopen the old session;
uncertain sanctions/publications cannot be repeated blindly. Mafia pause and
chat closure commit atomically. Existing independent chat closure survives
purge completion. A Telegram start/status message links to the same web session.

Full gate: 180 Python scripts, initially 153 passed / 27 failed, plus three JS
behavior scripts passed. One newly stale static test assumed every POST was a
mutation; it now explicitly permits the read-only forecast while retaining the
action-ID contract for all writes, and passes. The remaining 26 failures exactly
match the previously proven immutable-baseline failure list. No unrelated test
fixture repair was included. Evidence: worktree `.local/full-gate-results.log`,
`.local/scoped-final.log`, `.local/gate-comparison.json`; synthetic preview only
at 127.0.0.1:8407. The five reviewed PNGs are tracked release assets.

### Community material prepared for review

Verified by read-only Telegram calls: working bot is **@IIIPredvestnikIIIBot**,
ID 8485867534, administrator with topic-management rights in official forum
group -1003939897421. The local @predvestnik_v2_bot token is a different test
bot: its `left` status says nothing about the production bot's permissions.
No additional bot invitation is needed. The owner designated `/4` for updates;
the production observer must see an incoming topic message there before the
publisher permits delivery. No polling/stealing updates and no public test post.

Proposed group description (under Telegram's 255-character limit):

> Официальная группа Предвестника. Игры, питомцы и жизнь сообщества.
> Бот: @IIIPredvestnikIIIBot. Важные обновления — в теме «Обновления».
> Вопросы, идеи и сообщения об ошибках обсуждаем в соответствующих темах.

Proposed pinned navigation:

> Добро пожаловать в Predvestnik Official!
>
> Играть: https://t.me/IIIPredvestnikIIIBot
> Важные обновления: https://t.me/predvestnik_official/4
>
> Вопросы — в помощи; предложения — в идеях; ошибки — в сообщениях об ошибках.
> Для ошибки укажите действие, ожидаемый результат и то, что произошло.
> Скриншот и примерное время помогут разобраться быстрее.
>
> В обновлениях показываем только то, что уже доступно игрокам: короткое
> объяснение, изображение и кнопку перехода. Обсуждение — в общении.

Suggested topic roles, **after inspecting existing topics to avoid duplicates**:
existing «Обновления» `/4`; «Общение»; «Помощь»; «Идеи»; «Ошибки».
Do not create empty topics for every game or split a quiet community further.
Update the navigation with real topic links before pinning. These texts and
topic roles are drafts; no description, pin, topic or group permission changed.

Editorial policy: one important shipped release per post, no commit-by-commit
notifications, at least 24 hours between posts, one useful action button.
Normal minor fixes stay in the in-app changelog; don't send five separate posts
for this wave. Use 1–2 numbered marks only when the caption explains them.
Use real interface captures with clearly labelled synthetic data, never private
players' IDs, balances or moderation dossiers. Captures are prepared assets in
`FastAPI/static/announcements/`; the creator previews the exact image, text,
destination and version before sending. A lost send response requires manual
verification; it never triggers an automatic resend.

Owner UI feedback 2026-10-16: the first Rhythm result was rejected as a wall of
text. Replaced with score/accuracy ring, three compact metrics, one short hint
and a collapsed detailed review; explicit rating status remains visible. Server
response/caveat, heart losses, rounds and gifts remain available inside details.
Updated the real UI capture; 320/390/430 overflow checks and all 12 scoped checks
pass. Continue with the queued quests and joint design topics after this repair.

First publication draft, after deployment and availability verification
(`rhythm-analysis.png`, kind `rhythm`, button «Открыть игры»):

> Результат Ритма — с одного взгляда.
>
> Точность, лучшая серия и ошибки — на коротком итоговом экране.
> ① Пропуски считаются отдельно от неверных рун.
>
> Этапы, сердца и сборка — внутри «Разбора забега».
> Завершите забег и посмотрите свой результат.

Other image-caption pairs are material for later important releases, not a send
queue: `family-tree.png` — «Нажмите на родственника ①, чтобы перейти к его
связям»; `mafia-review.png` — finished rounds and day-vote totals, without
private night actions; `pets-forecast.png` — forecast before departure,
explicit daily-cap/random-find caveat; `purge-web.png` — shared chat/site
moderation decisions, with access restricted by actual chat permissions.

Owner follow-up progressed after the completed wave/UI repair: additive quests
are implemented on a separate branch; Notion sources were inspected read-only.
The owner selected solo outings linked to pets as the next design direction.
Joint owner agreement is still required BEFORE implementing the outing rules,
replacement exchange (system coins, buy/sell/shorts, personal coin creation for
5000 Zarniki), or chat command styling tied to existing cosmetics. Design notes
and unresolved decisions are recorded above; their economics are unchanged.

## PROD-UI-20261015 — production UI delivery and Pets v2 rollout

Validated release patch: replace buildpack-normalized mtime asset versions with
an ordered content digest covering all shipped JS/CSS and source HTML; main,
game HTML and static responses revalidate. The same version remains in asset
URLs and the WebSocket update event. Equal-size edits at the same 1980 mtime,
unchanged content at new mtimes and cross-host newlines have regression proof.

When `pets_v2` is enabled, cached V1 clients can no longer start a second reward
loop. Exact retries and settlement of existing V1 runs remain available; turning
the flag off restores V1 starts. No pet inventory/progression migration or reward
rewrite is part of this release. New environments keep the flag default off.

Validation: nine focused delivery, shell, WS, route, navigation and rules gates;
V1, V2 and rollout-boundary PostgreSQL proofs (including production-like game
flags); independent read-only reviews accepted both changes. The V2 key test
reconciles only its own run receipts, allowing legitimate separate quest keys.
Production rollout requires the patched commit Healthy, then enabling only
`pets_v2` and verifying authenticated Trail UI/API plus health/readiness.

## Stop-ship

> **Scope correction — 2026-09-06.** GAME-004 records the retirement of the
> *legacy* pet/zoo and quest systems. It does not prohibit the later approved
> `pets-v1` and `quests-v1` surfaces: those are separate server-authoritative
> contracts, available through the current Mini App/chat, with no legacy
> rewards or old routes restored. Their verified limits remain: pet expedition
> route completion grants no value, and quest variety is constrained until new
> authoritative activity writers exist.

> **QUALITY-2026-09-07 — owner-requested whole-product audit is active.**
> This is not a cosmetic pass. The current authenticated loopback run captured
> the profile, quest log, fitting room, activity hub and Rhythm leaderboard.
> The findings below are therefore evidence-based current-state work, not a
> promise that an older test or a green static check represents release quality.
> No production URL/menu has been changed: the workspace contains only the
> stale DigitalOcean endpoint and disposable preprod tunnel configuration, not
> the owner-mentioned current production domain.

| ID | Priority | Player-facing gap / confirmed cause | Completion bar and order |
| --- | --- | --- | --- |
| **SHORT-001** | **In implementation · public enable blocked** | The approved exchange specification permits Shorts only after a separate 100,000-scenario simulation and real Spot observation. The dedicated model now proves lender claims, margin, conservative marks, interest, liquidation, caps, halts and insurance depletion. The owner-approved backstop never mints Mora, never makes the reserve negative and never writes off lender principal: catastrophic gaps create immutable per-loan frozen-claims until a segregated per-coin reserve can buy them back. | Hidden implementation order: exact pool/loan allocation, isolated per-coin reserve and append-only claims; atomic borrow+full protected sale; margin/interest/reduce-only paths; player-triggered liquidation; bounded automatic claim buyback; Mini App disclosure/recovery. Independent architecture review accepted the direction after these contract amendments. **Public enable stays NO-GO** until real Spot observation. |
| **VIP-003** | **Ready for release · not deployed** | The approved single VIP product replaces the retired tier shop: 7/30/90/365 days cost exactly 140/600/1800/7300 Zarniki. Purchase has one user lock, canonical ledger debit, append-only receipt, stable client action ID and atomic extension from the later of current expiry or now. Existing legacy tier rows remain readable. Active VIP receives five quest replacements, a 10-question assistant limit, an exact +10% Mora boost on ordinary daily/weekly rewards and a persisted choice among 20 nickname badges at left/right/both/hidden. The UTC daily mission completes from one trusted finished game, grants 20 Mora, adds 100 Mora plus one typed key every seventh completion, and never resets for missed days. Shared Telegram and profile name rendering consume the badge. After 18:00 UTC a private reminder is sent at most once daily and stops after two successfully delivered but ignored reminders; completion resets it. The profile has a functional purchase/settings entry; redesign is deliberately later. | Independent review caught and corrected ledger-schema ordering and the quest-claim expiry race. The real PostgreSQL contract then caught and corrected concurrent schema installation plus date binding/progress persistence defects. It now proves same-action replay, distinct concurrent extension, insufficient-funds rollback, one daily reward under concurrency, reminder stopping and append-only receipts. Full isolated preprod gate: **109/109**. Player patch notes are written. This wave is locally release-ready but intentionally not deployed from the current `backup/no-deploy-2026-08-25-195138` branch. |
| **SOCIAL-001** | **Resolved locally** | Public profiles use a durable opaque `profile_ref`; the API exposes an explicit player projection rather than Telegram/database identifiers. Rhythm and Minesweeper leaderboard clients render the projected display name as a tappable public-profile link. The unauthenticated legacy `GET /profile/{user_id}` bypass discovered during QA was removed rather than wrapped. | 2026-09-13 live loopback proof now returns 404 for a real, small and maximum numeric ID while the opaque profile opens without rendering the raw Telegram ID. The route contract locks all three negative cases. Remaining external evidence belongs to QA-001: populated ranking order, 320/390/430 screenshots and a real Telegram tap test. |
| **SOCIAL-002** | **P1 · core tracker resolved locally** | The private **Chat Tracker** now has a compact summary, literal-title search, recent/week/all-time/rank sorting, stable paging and per-chat cards for the current player's level, rank, message counters, activity streak and current/recent moderation actions. Left chats and every other player's rows are excluded; chat/admin IDs, membership lists and moderator notes are never projected. | PostgreSQL proof covers isolation, left-chat exclusion, stable ties/pages, literal wildcard search, streaks and stripped moderation history. Live 320/390/430 and 1280 px proof covers zero overflow, 44–46 px controls, 12→14 paging/focus return, an 88-character title, expanded moderation history, empty/search states and zero console errors. Remaining source gap: the current achievement model has no chat-scoped receipt, so the UI does not fabricate “achievement progress”; define that durable source before adding it. |
| **UI-001** | **Resolved locally** | The shared renderer now has one identity/avatar anchor, a 168 px fitting/store stage, readable data rail and five-resource rail. Background, surface tone, edge, name/title typography and restrained card effect are composed from the saved look. The fitting room renders one card with a public/saved switch instead of duplicating the full layout. | 2026-09-09 visible loopback proof covered profile, fitting and the storefront at 320/390/430 widths. Exact whole-product screenshot evidence remains in QA-001, not a blocker to further local art refinement. |
| **UI-002** | **Resolved locally** | The owner screenshot was reproduced and measured: `.profile-showcase-main` had been reduced to 220 px, while the older 270 px `min-height` still forced its direct `.character-showcase-area` child beyond the stage. The bottom-anchored «Личный профиль» plate therefore overlapped the following resource rail by 39 px. | Direct stage children now inherit the 220 px stage height and reset the stale minimum without hiding or moving the caption. Live 320/390/430 px measurements show stage = character area = 220 px, caption/resource overlap = 0, an 11 px gap and no horizontal overflow; all five resource cells remain visible. The later, more specific store-preview rule still preserves its 168 px compact stage. Static delivery locks the cascade and the exact isolated preprod gate is **89/89**. |
| **COS-002** | **Resolved locally** | The delivered **Образы** page is now a mobile-first Zarniki storefront: collection/catalog/owned navigation, stable collection totals, item and whole-set checkout, live collection-context preview, durable whole-app skins and a server-backed Zarniki top-up route. The supplied Atlas art is a 1600✨ item in the Void collection and one shared skin applicator carries it through the shell, Rhythm and Minesweeper. Paid cosmetics are permanent entitlements and never hide behind a second VIP gate. | 2026-09-09 PostgreSQL negatives cover atomic item/set/skin debit, retry, insufficient balance rollback and grant provenance. Runtime invariant proves zero priced `vip_required` SKUs. Live 320/390/430 checks cover no horizontal overflow, 168 px stage, 44 px actions, dialog focus/Escape/return, Back hierarchy, single preview skin and the fail-closed Stars top-up message. Independent review drove three correction rounds. Exact final isolated gate: **89/89**. Production Stars invoice confirmation remains part of REL-001 and was not triggered in QA. |
| **QUEST-002** | **Resolved locally** | The old random set could fill four/five slots with only two/three metrics. It is now source-aware and lane-balanced: flexible play, Rhythm mode/verified-score goals, Minesweeper completion/win/difficulty goals and experienced-player-only Mafia completion/win. Reroll explicitly excludes the target and occupied metrics/lanes; pristine historical sets migrate collision-safely while any started period remains byte-for-byte intact. The mobile screen removes duplicate summaries and the overlapping floating Back, connects each set to its exact Mora reward, exposes paths from Rewards, and adds headings, named progressbars, retry and dialog focus return. No quest/page background asset exists; backgrounds remain cosmetics-only. | PostgreSQL proofs cover exact terminal receipt sets for normal/augments/500-score Rhythm, Minesweeper loss/easy/hard win, Mafia participants/winning faction, replay, unavailable-source empty state and both pristine/started migration paths. Visible isolated preprod shows 4 varied daily and 5 round-robin weekly goals, compact reward context, accessible dialog and focus return. Independent review found and then accepted fixes for the hard-win rollback, target-equivalent reroll, partial-period migration and missing augments E2E. Final isolated gate: **90/90**. |
| **CONTENT-001** | **Resolved locally · compensation deferred** | The chest store now uses one versioned mixed catalogue for free and paid keys: 12 stable pet species, five food items, pet-card packs, Mora, Diamonds, Jokers, Zarniki and the pinned VIP reward pool. A key costs 10 Zarniki, with two purchases per UTC day and exactly the same odds as free keys. Purchase, entitlement, prepare, typed delivery, reveal and unused-paid-key refund are idempotent and transaction-bound. The UI discloses star odds, every conditional reward weight, exact amounts/ranges, rarity tables, species/VIP pools and owned-pool fallback before purchase; a confirmation sheet repeats price/quota/refund terms. Daily/weekly set completion and completed pet activities mint typed keys, but a chest quest is eligible only when a key already exists and random card drops never gate set completion. Pet activities atomically spend 25/40/55 endurance, respect the chest flag/readiness guard and preserve completed runs for later settlement when disabled. Existing canonical pet ownership is reconciled instead of creating a duplicate. | One-million seeded simulation gives conservative EV 9.52 per 10-Zarniki key; transactional tests cover purchase races, replay, stale catalogue, every delivery type, unused-key refund, legacy pet ownership, disabled feature settlement, exhausted pets and no duplicate compensation call. Live isolated preprod at 320/390/430 px covered confirmation/cancel, exact 10★ disclosure, sealed prepare/reveal, quest progress and 38→13 endurance debit. Final isolated preprod gate: **96/96**. Duplicate/max-level compensation remains intentionally last before production, per owner instruction. |
| **ACH-002** | **Resolved locally** | The durable 1–40 model now has five server-terminal families: Rhythm, Minesweeper, Mafia, chests and pet activities. The mobile collection is browsable by **All / Games / Adventures**, shows two independent meters to the exact next level, explains which condition still blocks progress, and exposes levels 1/5/10/20/30/40 without turning the page into a reward wall. Rewards remain Mora-only. | Immutable terminal and reward receipts reject replay or altered facts; the received-Mora summary uses the amount actually stored in historical receipts rather than recalculating history through the current policy. Level 40 still requires the family event cap and 156 active weeks, and excess lifetime events do not rewrite the displayed cap. Live 320/390/430 px evidence shows zero horizontal overflow, one Back, 44 px actions, focus-preserving filters and readable partial progress. Independent review accepted all corrections. Final isolated gate: **97/97**. |
| **GAME-001** | **Resolved locally** | The shipped client now uses a one-use REST ticket and server-timed WebSocket with stable tap IDs and reconnect continuity; it no longer requests the exposed offline packet. Every terminal live run becomes `review_required`, so script-echoed runes cannot directly write the leaderboard, quests or achievements. | A developer-only review API records one append-only clear/quarantine decision. Transaction-scoped locking linearizes concurrent reuse of the global review ID; only `clear` writes trusted ranking/progression, idempotently. PostgreSQL counterexamples cover pre-review zero writes, clear, quarantine, replay and altered decision; live 390 px shows the pending-review result and a populated opaque-profile leaderboard. Independent re-review found a concurrency race, then returned ACCEPT after the lock fix. Real Telegram transport/reconnect remains in QA-001. |
| **REL-001** | **P0 · one live monetary gate** | The owner supplied the stable production domain and confirmed that `master` deploys automatically. DigitalOcean now preserves the full `/predvestnik` path; the bot menu targets the same HTTPS Mini App. | Production `health`/`ready`, legal/static/update delivery, protected-auth boundaries and retired-route 404s pass the repeatable `tools/verify_production_http.py` gate (**26/26**). The deployed bundle contains commit `436f90fe` markers. Real test-chat transport verifies administrator rights, send/edit, callback/URL keyboards and cleanup. Before a formal public launch, perform one owner-authorized minimum Stars purchase, verify exactly one credit and history receipt, then confirm cancellation produces no credit. Automation cannot spend the owner's Stars. |
| **QA-001** | **Resolved for current release scope** | The adversarial matrix found and removed the raw-ID profile leak, overlapping Back controls, uncertain-response action-ID changes, undersized touch targets and a long-name header overflow risk. | Full isolated preprod passes **108/108**. Authenticated browser checks at 320 px cover profile, store, games, More, settings, pets, quests, chests, achievements and chat tracker with zero horizontal overflow; primary controls are at least 44 px. Independent review returned ACCEPT after the long-name correction. Production route/static markers and real Telegram transport are green. |
| **LCB-002** | **Applied and reconciled** | Value-preserving v4 carries current Zarniki once, refunds 13,852 Zarniki proven spent by six users in the retired exchange, converts retired paid rights to Zarniki, caps liquid progression and converts every remaining score point continuously into diminishing VIP time. Existing VIP is preserved; no universal 21-day grant or randomized-key settlement. | Production contains 253 immutable matching receipts. Aggregate credits match the frozen v4 inventory; converted legacy inventory is absent. A deployment recovery bug replayed six historical Stars purchases, and six canonical correction operations removed the duplicate 29,060 Zarniki; registered charge history prevents another replay. |
| **CHAT-001** | **Resolved for release scope** | Telegram now has one home/help concept, local/global player message tops and chat tops across today/week/month/all time, separated ranks/activity, sectional settings, audited module controls and complete divorce settlement. | Module writes are audited and authority-checked; placement/trends/privacy and deterministic family-property split are implemented. Retired event/economy handlers and dependency-proven legacy files are removed. Real test-chat transport and the **108/108** preprod gate pass. New game content remains a separate owner-approved post-release track. |

**Execution order:** `SOCIAL-001`, `UI-001`, `UI-002`, `COS-002`, `QUEST-002`,
`CONTENT-001`, `ACH-002`, `GAME-001`, `QA-001`, `LCB-002` and the current
`CHAT-001` release scope are complete. `REL-001` is reduced to one explicit
owner-authorized monetary acceptance check. `SOCIAL-002` retains only its
chat-scoped achievement source decision. New gameplay, VIP benefits, chest
presentation and the monolithic visual redesign require separate concept
approval before implementation.

### QA-001 current release evidence matrix — 2026-09-13

| Surface | Automated / authoritative evidence | Fresh browser evidence | Negative or counterexample | Residual gate |
| --- | --- | --- | --- | --- |
| Profile | PostgreSQL projection/privacy tests; static showcase/wrap contracts | 390 px: five resources, settings grid, no overlap or horizontal overflow | Green suite coexisted with anonymous raw-ID disclosure; legacy route now absent and live 404 | 320/430/desktop, long data, keyboard; Telegram tap |
| Fitting and cosmetics | Ownership, atomic item/set debit, replay, insufficient funds and skin application | 390 px: collection/catalog/owned navigation, 168 px preview, 44 px controls, Escape returns focus | Stars top-up is visibly fail-closed before the production payment gate | Real Stars paid/cancelled/lost-response recovery |
| Quests | Assignment variety, terminal receipts, reroll/reward replay and ARIA contract | 390 px: three tabs, four varied daily goals, one Back, no overflow | Lost reroll response formerly created a new action ID; client now retains it until success | Live failed-response replay; 320/430; Telegram entry |
| Pets | Ownership, endurance/activity/reward/replay PostgreSQL tests | 390 px: 11/100 state, disabled unaffordable activities, one local Back, no overflow | Feed, active slot, activity start and route choice retain one ID after an uncertain response; failures refetch the authoritative timer/state | Empty/many pets, live lost-response mock, timers, 320/430 |
| Chests | Mixed-catalogue, odds, typed delivery, replay and unused-key refund tests | 390 px: 1 key, disclosure, 54 px main action, one Back | Prepare/purchase now retain one action ID until success; reveal is recovered by immutable `open_id`; compensation remains deliberately deferred | Pending reload, 0-key/quota/error, 320/430 |
| Achievements | Immutable event/reward receipts and five-family projection | 390 px: filters, exact dual progress, milestones, 44 px actions, one Back | Static contract alone did not detect unrelated page navigation regressions | 320/430 re-run in final whole-product pass |
| Activities hub | Pure server view plus navigation contract | 390 px: three approved cards, CTA 44 px, no floating Back or overflow | A passing gate allowed Back to overlap the Sapper CTA before this audit | 320/430; reconcile UI with `/hub/me` |
| Rhythm | Ticket/WS/reconnect/stable-replay tests; pending-review/clear/quarantine/progression PG proofs; developer gate | 390 px: HTTP→ticket→WS, pending-review finish, populated trusted leaderboard and opaque profile link | Independent critic found concurrent review-ID race; transaction advisory lock fixed it and re-review returned ACCEPT | Real Telegram disconnect/reconnect and developer review smoke; 320/430 |
| Minesweeper | Server-owned state, revision, ownership, replay, ranking and terminal GET-loss proof | 390 px: all difficulties, readable 9×9 grid, no overflow | Uncertain action now keeps one ID, disables conflicting input and refetches authority; terminal GET reveals the same mines | Live forced lost-response replay; 320/430 |
| Mafia history | Full fake-Telegram match plus history projection | 390 px: empty modal, focus on Close, clear group instruction | Fake delivery does not prove Telegram DM/edit/callback behaviour | Controlled real group test and `/mafia-v1/me` adapter test |
| Public profile | Opaque reference resolver and safe DTO projection | 390 px: full card, five resources, no raw ID or overflow | Real numeric `/profile/990000001` returned private raw DTO while 97/97 passed; now 404 | Unknown ref and populated leaderboard click at 320/430/desktop |
| Chat Tracker | PostgreSQL isolation/search/sort/paging/streak/moderation projection proof | 320/390/430 and 1280 px: sticky tools, 44–46 px targets, long populated cards, expanded history, stable paging/focus, no overflow or console errors | Wildcards are escaped literally; left/foreign chat rows and raw chat/admin IDs are excluded | Chat-scoped achievement source decision only |
| Payment/support | Invoice/delivery/recovery and reconciliation/refund-review tests | 390 px store top-up boundary is fail-closed; dialog focus/Escape verified | Local success cannot prove Telegram Stars delivery or support routing | Production-like paid/cancelled/pending/lost-webhook and support smoke |
| Bot routes | Handler allowlist and focused middleware/callback contracts | Not representable by browser evidence | Imports/names do not prove Dispatcher ordering or Telegram delivery | Real private/group command, stale callback and permission smoke |

| ID | User path | Confirmed root cause | Safe resolution | Evidence / residual risk |
| --- | --- | --- | --- | --- |
| BOT-001 | Moderator creates `бот привязать админ чат`; reports should reach the trusted admin group. | The former bearer token could be redeemed by anyone in any group; it had no TTL and was consumed by non-atomic SELECT then DELETE. | Implemented: creator-bound 10-minute request; live rights check for the same user in both groups; destination bot-admin check; PostgreSQL one-to-one destination constraint; atomic consume → route → append-only bind audit. A rebind is rejected during an active purge because dossiers preserve their destination. | 2026-08-30 isolated-preprod test rejects foreign owner, replay, expired token, duplicate destination and active-purge rebind; concurrent delivery yields exactly one route. Schema startup, compile, diff check and external authenticated HTTPS smoke passed on the restarted test bot. Residual stop-ship gate: manually test source→destination bind and non-owner rejection in two real Telegram test groups before production. |
| FAM-001 | Player creates/accepts a marriage, views a family wallet, attempts a transfer or divorce. | Legacy `marriages` had no global membership constraint; the old direct-column writer accepted a supplied marriage id, had no idempotency and stored `FLOAT8`; hard deletion also conflicted with immutable family history. | Only the new server-resolved membership transfer may move value: personal + family append-only legs share one transaction, Zarники are whole-number, and client data never chooses a family. HTTP requires an idempotency key; Telegram uses a persisted owner-bound 10-minute one-shot intent. Divorce is a soft close after all family property is zero. The approved Stars policy has no automatic/user-facing refund; `/paysupport` is manually reviewed and a return is normally considered only before linked Zarники leave buyer personal custody. | 2026-08-30 isolated-preprod proof: schema migration; four-currency transfer retry/foreign-member/fractional/insufficient cases; HTTP rejects supplied marriage id and a missing idempotency key; Telegram rejects a foreign or expired intent and concurrent delivery yields exactly one operation. The former scheduler family-column mutation was removed; the obsolete direct writer remains fail-closed. Updated test bot and external authenticated HTTPS smoke passed. Residual production gate: owner-approved read-only migration audit plus a manual end-to-end transfer in a disposable married test account before any production migration. Payer-origin lots stay deferred unless a future policy permits refunds after transfer. |
| GAME-SCOPE | Development is directed at legacy Reconstruction campaign mechanics. | The old release backlog treated Chapters, Memories, Scar Map and other retired surfaces as active game bugs, conflicting with the owner-approved 2026-08-30 scope. | Retire those rows from the active queue. Do not extend legacy game code. New work begins only from the approved Rune Rhythm, Mini App Minesweeper and chat Mafia contracts; their detailed economies remain deferred. | Authority: `docs/PROJECT_RECONSTRUCTION_MASTER_PLAN.md`, priority blocks dated 2026-08-30. |
| GAME-001 | Player starts an endless Rune Rhythm run, chooses augmentations, taps runes and later reads a per-mode leaderboard. | The legacy Rhythm is coupled to retired Reconstruction campaign state and trusts a client-facing combat flow. The first live-WebSocket version also put transport latency between every tap and its feedback. | The approved play path is local-first: an authenticated start receives a server-derived buffered rune packet, then the Mini App resolves runes, health, timer, chunks and feedback locally. An offline terminal journal is deterministically replayed server-side for the player's own result, but it is not proof of human timing. Issuing that packet marks the run `offline_exposed`; terminal offline runs become `quarantined` and systemically cannot write leaderboard, quest metrics, achievement receipts or their downstream Mora. Only a server-timed transport run can be a future `clear` candidate; old pre-boundary rows are `legacy_unverified` and excluded. | 2026-09-07 independent review found that the former implementation allowed a forged perfect offline journal into the global table and terminal quest/achievement writers — a P0, so the prior statement that Rhythm had no progression effect was wrong. The new PostgreSQL negative proof submits a positive-score forged local journal and verifies `quarantined`, no leaderboard row, no quest receipt and no achievement receipt; it also rejects switching an offline-exposed run into trusted transport. Leaderboard DTO no longer returns raw user IDs. Integrity-review evidence is append-only, but no admin/public approval writer exists yet. JS/Python/ASGI and full isolated preprod **86/86** pass. Remaining release gate: migrate the Mini App to the existing server-timed transport and design/manual-test the separate reviewer workflow before presenting a non-empty public leaderboard as trusted. |
| GAME-002 | Player opens Mini App Minesweeper, chooses a difficulty, opens/flags cells and reads a difficulty-specific global table. | The retired wager Sapper exposed a different product contract: stake, cashout and a server session that cannot be reused. A wholly local replacement would make a leaderboard trivially forgeable. | Implemented a separate server-owned `/minesweeper` surface: Easy 6×6/6, Normal 9×9/10, Hard 9×9/18; safe first open + halo; touch-to-open, hold-to-flag plus explicit flag mode; every action is revisioned and server-resolved. Only confirmed wins rank by server elapsed time then open actions; no reward/economy/quest writer is attached. | 2026-08-31: pure rules and isolated PostgreSQL proof cover layout counts, safe first cell, flags, owner isolation, idempotent retry, payload conflict, terminal state and ranking. Live 390px test covered first-open cascade, flag, difficulty switch and loss revealing mines without console errors; 320px has no horizontal overflow. Residual release gate: owner must enable `game_minesweeper_v2` intentionally in production after the controlled test rollout. |
| GAME-003 | A group starts chat-native Mafia: lobby, private roles, night, discussion, voting and a persistent phase card. | There was no approved chat-game lifecycle; reusing global chat locks would block bystanders and could overwrite moderator settings. | Implemented a feature-gated (`game_mafia_v1`, production off) server-owned match state with row-locked deadlines, phase-aware deletion gate, explicit DM readiness, private roles/actions, one active game per chat/topic and a 5-second editable card. Discussion allows only living players; night/voting allow only nonplayers. The lobby reappears after ten human messages, settings stay server-side, and purge/delete-right failures pause instead of silently changing group permissions. All primary player actions are visible buttons; settings are host-only compact controls, choice buttons use player numbers, completed night/vote phases state their outcome, and open voting displays live selections while secret voting does not. The host can resume a safety-paused match with its stored phase/time once purge is inactive. The Mini App has read-only personal history/statistics. No rewards or economy writer is attached. | 2026-09-01 isolated PostgreSQL/fake-Telegram integration simulates four players through lobby, roles, card delivery/edit, phase gate, stale start, vote change, cancellation, settings/topic rejection, pause/resume, purge rejection and open/secret vote visibility. A live loopback Mini App test reached the history modal and exposed/fixed a broken post-onboarding route to the game hub. Rules, static delivery and compile/diff checks are green. Residual release gate: conduct a controlled real Telegram group check for bot deletion rights, callback rendering and private-message delivery before enabling the flag in production. |
| GAME-004 | Player opens the profile, help or the default Mini App and reads a retired game promise. | The active product surface still contained a Reconstruction client, a `/reconstruction/*` router, a pet tab and bot writers for old care/expeditions. | Resolved for the public runtime: removed the Reconstruction router/client, the old `/zoo` router and their tests; `/game` is a compatibility redirect to the activities hub; former routes are absent; the pet tab and old chat writers are closed. The scheduler module itself now contains only operational maintenance and Mafia phase advancement, so bot import no longer loads retired expedition, shop, auction/duel, Battle Pass, crypto-alert, Smart Pulse, chest-event or shadow-merchant jobs. The obsolete no-op streak middleware is physically absent. Chat settings and the Mini App expose only the approved surfaces; archival database rows remain for the future compensation audit. | Route, navigation and surface-parity contracts pass. The corrected full isolated-preprod gate is **103/103**. Remaining gates are external production evidence and the owner-approved archival compensation audit, not another runtime writer cleanup. |
| GAME-005 | A group of seven inside a chat of forty plays Mafia and nobody is blocked: the first real attempt could not even start ("not everybody has an active chat with the bot" although they did), the host could not stop a stuck night, bystanders were deleted all day. | Start required a stored "I am ready" flag set only by a hidden DM button (and expiring after 30 days) instead of asking Telegram; the quiet-phase gate deleted every command and every non-player message in discussion; transient Telegram errors (flood) created duplicate phase cards and one failing match aborted the whole scheduler pass; quest assignment errors rolled back the end of a game and looped the scheduler; lobby reposts piled up copies; an abstention never counted against a lone accusation; a mafia tie killed nobody; there was no lobby TTL, no abandoned-game exit and nobody but the host could stop a game. | Reachability is probed live (join, start); one-tap join with a deep link; onlookers are never silenced (living players only at night, eliminated only by day); control commands pass the gate; phase results and the game start are stored events delivered in resumable steps (exactly-once, retried, per-match isolation); rewards are issued after the phase commits; auto roles, tempo presets, early phase end, Don/earliest-pick tie-break, mafia team board, ballots in DM, host/admin stop with confirmation, skip discussion, role popup, rate-limited card bump, rematch, rules in four short pages and a Mini App "how to play" block. Design hand-off: `docs/MAFIA_DESIGN_HANDOFF.md`. | `tools/test_mafia_v1_sim_pg.py` drives the real routers and middlewares against an in-memory Telegram (`tools/mafia_sim`) with virtual players: 41 scenarios on a loopback PostgreSQL (lobby, deep link, start checks, full games, random 4-12 player games with quiet-rule oracle, flood, races, closed DMs, quest outage, abandoned games, busy-chat bump, copy lint); mutation runs re-introducing each original bug fail the matching scenario. Rules/service/neighbour suites green. Residual gate: one controlled check in a real Telegram group for `answerCallbackQuery(url=…)` deep links, delete rights and DM delivery before enabling `game_mafia_v1` in production. |

## P1

| ID | User path | Confirmed root cause | Safe resolution | Evidence / residual risk |
| --- | --- | --- | --- | --- |
| BOT-003 | Globally banned user sends an update. | The database middleware used to refresh profile/activity before the later sanction gate suppressed the handler. | Implemented: one shared-connection sanction evaluation now runs before every automatic writer and records its result for the later middleware. An allowed appeal/help command reaches its handler without refreshing profile, chat settings, counters or hint state; any sanction-check failure stops the update. | 2026-08-30 contract proof covers blocked text, allowed appeal, one-shot evaluation and zero automatic writer calls; compile, preprod gate and external HTTPS smoke passed after test-bot restart. Residual: a message whose evaluation began before a concurrently committed new ban can still finish its automatic writes; absolute cross-transaction ordering needs a separate shared lock/change to sanction issuance. |
| BOT-004 | Former moderator taps a retained chat-settings button. | Callbacks previously validated only the historical menu owner; rank, destination context and live Telegram authority were not re-checked (except one special toggle). | Implemented one shared callback gate for menu, rank picker and every toggle: same owner, group context, current local rank ≥5 and live Telegram creator/manage-chat authority are required; settings keys remain allowlisted. | 2026-08-30 contract proof rejects local-rank demotion and lost Telegram authority before any database writer, while accepting a current authorized moderator. Compile, test-bot restart and external HTTPS smoke passed. Residual: a callback already inside the helper can race a later demotion; Telegram has no transactional role lock, so each new callback is revalidated immediately before it writes. |
| BOT-005 | Telegram `successful_payment` update is lost during a long outage/backlog. | A capped, stateless recovery could overlap between bot processes and silently treat an offset scan as complete even while new history rows shift its head. | Implemented: one durable lease coordinates scanners; every scan starts from Telegram history head, reaches a terminal short page, then re-reads that head. A changed head, page cap, invalid/failed relevant row or API failure creates a durable critical alert and resets the run; failed/invalid rows receive an immutable per-charge journal record. Ledger credits remain idempotent by Telegram charge id. | 2026-08-31 isolated PostgreSQL proof covers competing workers, lease release, failed Telegram-history call, critical alert, and immutable observation conflict; existing invoice/delivery/replay contract stays green. Residual release gate: execute one real production-like Telegram history recovery only after owner-approved production migration/audit; Stars remain disabled on preprod. |
| BOT-006 | Smart Pulse cannot DM a player due to a transient Telegram error. | The task marked every queued notice sent before attempting delivery, so a network error silently lost the notification. | Implemented: atomically lease one event for 10 minutes; mark it delivered and close the remainder only after Telegram accepts its DM. Transient errors release the lease for the next run; forbidden/bad-request DM routes are permanently classified with retained reason. Opted-out/expired events close without consuming the DM cooldown. | 2026-08-31 real isolated PostgreSQL proof covers concurrent lease rejection, transient release/retry, post-success batch close and permanent failure classification. Residual: Telegram can accept a DM then lose its HTTP response, so at-least-once retry can duplicate a non-economic notice; it never loses it silently. |
| BOT-007 | Moderator double-clicks or later uses an old rank-confirmation button. | Rank confirmation trusted target/rank/initiator embedded in callback data and had no expiry or one-time consume. | Implemented: callback contains only an opaque server token. The persisted request binds chat, initiator, target's source rank and desired rank for 10 minutes; the approver is checked before atomic consume, then initiator authority and target state are revalidated before the writer. | 2026-08-31 real isolated PostgreSQL proof rejects wrong-chat use and replay after first consume. Residual: a request whose source rank changes after atomic consume is safely rejected but must be recreated. |
| A02 | Account restore window expires and the daily tick finalizes it. | Cleanup ran statement by statement in autocommit, swallowed each error and still wrote `finalized`, so partial cleanup became permanent and was never retried. | Implemented (draft PR, not released): one transaction under the per-user advisory lock and `users` row lock; status written last; failures roll back and retry next tick; restore serializes on the same lock. Record: `pipeline/tasks/A02-atomic-account-finalization/task.md`. | Real PostgreSQL failure-injection and race proof `tools/test_account_deletion_atomic_pg.py`. Residual: late credits after finalize, no ledger rows for zeroing, no attempts counter. |

## P2

| ID | User path | Confirmed root cause | Safe resolution | Evidence / residual risk |
| --- | --- | --- | --- | --- |
| BOT-008 | FastAPI co-host or a detached scheduler task crashes. | Startup used untracked `create_task`/`ensure_future`, so polling could remain alive after Mini App or a scheduler silently died. | Implemented a shared supervisor: every co-host/scheduler task has a named handle, completion/crash log and shutdown cancellation. Any unexpected exit signals the polling owner to terminate fail-fast, letting the process supervisor restart a coherent instance. | 2026-08-31 injected failing coroutine proves critical log + fail-fast signal; compile/diff checks pass. Residual: deployment must retain a process restart policy; the bot intentionally does not hot-restart individual stateful tasks in-process. |
| DOC-001 | CI runs the retained document-contract tests. | Removed historical documents were still read by `tools/test_current_game_docs.py` and `tools/test_currency_exchange_retirement.py`. | Resolved: the current-game test now reads only `docs/PROJECT_RECONSTRUCTION_MASTER_PLAN.md`; the unapproved legacy-economy test is excluded from the approved-scope runner. Historical documents were not restored. | 2026-09-01 approved-scope isolated preprod suite passes 78/78. Deferred economy design remains outside this test gate. |
| TEST-001 | Developer runs the isolated preprod suite before a release. | The runner did not set its own module `PYTHONPATH` or pass the owned isolated DSN to tests that require it; it also mixed retired Reconstruction/Chronicle and unapproved-economy contracts with the approved game surface. | Implemented: the runner supplies its disposable DSN, discovers imports from the module root, and explicitly excludes only tests whose assumptions contradict the owner-approved master-plan scope. The current game-document check reads that one plan and verifies that deleted historical game documents are not restored. | 2026-09-01 full isolated preprod run: 78/78 passed. This is not evidence that deferred economy/pet design is approved or ready; those decisions remain owner-led. |
| TEST-URL-001 | Test player opens the Mini App through the actual Telegram test bot after a Quick Tunnel expires. | `.env.test` still referenced a dead account-less Cloudflare hostname. The prescribed automation did not overwrite that stale menu while its replacement URL lacked a confirmed external 200, but Quick Tunnel edge publication can occur after its initial probe window. | A new Quick Tunnel was externally checked at `/predvestnik/` before changing `.env.test` or the test bot menu. The restarted isolated preprod bot reads the same URL and its Telegram API call confirms the menu button update. | 2026-09-07 external HTTP returned 200; startup log confirms `Кнопка меню → <new tunnel>`, loopback auth and bot ready state. It is intentionally a disposable testing URL; it dies with the local cloudflared process and is not a production deployment. |
| ECON-001 | Player converts already-delivered Zarinki to Mora or Diamonds without buying a direct Stars progression product or bypassing a cap by mixing targets. | Legacy exchange was deliberately closed and its obsolete 150 Mora/✨ quote had no quota, payment-review gate or shared HTTP/chat authority. | Added `zarniki_exchange_v1`: 1✨→10🪙 or 0.01💎, whole inputs only and one shared 50✨ UTC-day cap. The one service locks the player, replays before cap checks, freezes payment-review accounts, appends `-✨/+target` through the canonical ledger and records quota in the same outer transaction. Mini App and bot are adapters only. | 2026-09-05 pure simulation proves the 2,200✨ 200-Star package cannot convert in fewer than 44 days; real PostgreSQL proof covers atomic legs, replay, altered action key, cap/split-route bypass and review hold. Full isolated preprod gate: 83/83 green. Residual production gate: use a named tunnel/custom domain or deployment; Quick Tunnel availability ends with its local process. |
| ECON-002 | A capped pet/cosmetic duplicate must compensate the owner without becoming Stars, a generic wallet loophole or an accidental public product. | The approved currency had no name or durable receipt boundary; expanding the four-currency ledger would also widen every existing wallet writer and payment/history projection. | Named **Осколки Эха** (`echo_shards`). A separate internal account, immutable compensation receipt and append-only positive ledger remain isolated from API, chat, shop, exchange, transfer, invoice and payment paths. The internal pet terminal writer progresses 1→16, then emits exactly one shard at level 16 in the same transaction as append-only source and progression receipts; it refuses an arbitrary source string. | 2026-09-07 independent read-only economy review selected this isolated architecture. PostgreSQL proofs cover all fifteen level-ups, the terminal one-shard compensation, exact replay, changed source/pet conflict, snapshot tampering, numeric-coercion rejection, missing-source rejection and all receipt/ledger append-only triggers. There is still no public writer or client-supplied award. Residual: connect it only to a future verified chest/loot source; cosmetic duplicate writer, shard catalogue and spending remain intentionally absent. |

## Next safe wave

### LEGACY-DELETE-001 — dependency-proven removal (2026-09-23)

The unreachable FastAPI routers for barracks, clans v2, craft, daily deal,
events, legacy quests/streak/top and the superseded Telegram identity/profile/VIP
handlers are physically removed. Account recovery remains in its dedicated
router. Release contracts, repository import search, `compileall`,
`git diff --check` and the full isolated preprod gate pass **108/108**.
Independent review returned ACCEPT; commit `f8da5d43` is deployed.

The only remaining release gate that automation cannot complete is the live
Stars acceptance check in `REL-001`; it must not spend the owner's Stars without
explicit approval. For gameplay, use only the current owner scope in
`PROJECT_RECONSTRUCTION_MASTER_PLAN.md`: Rune Rhythm, Minesweeper and Mafia. Do
not restore or extend retired campaign mechanics while new game contracts and
economy remain owner-approved work.

### Rollback compatibility rehearsal and runbook — 2026-09-24

The currently deployed change from `f8da5d43` to `436f90fe` is application-only:
its diff contains payment/rollout copy, Mini App layout/styles, patch notes and
tests, with no schema or migration changes. A detached checkout of `f8da5d43`
was run against the current post-release preprod PostgreSQL schema. All **107
application tests passed**; the sole excluded failure among the runner's 108
entries was `test_current_game_docs.py`, which asserts the presence/content of
the newer workspace-only `AGENTS.md` router and does not import or exercise the
application.

This proves application/schema backward compatibility; it is not a claim that a
DigitalOcean rollback was performed. If this release must be rolled back, revert `436f90fe` with a normal Git revert
commit on `master` and let DigitalOcean deploy that new commit. Never reset or
force-push `master`, and never restore the database: compensation receipts,
ledger rows and Stars reconciliation history must remain intact. After the
deployment, run `tools/verify_production_http.py --profile rollback-f8da5d43`
and the real test-chat
send/edit/callback/URL-keyboard/cleanup probe. Forward-fix and redeploy if either
gate fails. This proof is valid for the schema-neutral `436f90fe` release only;
every future schema-changing release requires its own forward/backward
compatibility and backup plan.

## Owner decisions — activity and pet direction (2026-09-05)

- Games are approved as activities, not as the sole or central product loop.
  Rune Rhythm, Minesweeper and Mafia remain isolated from pet power, currency,
  keys and paid advantages. Their tested preprod implementations require only
  their stated real-Telegram and production-flag gates.
- Pet progression is approved as a separate long-term activity: a level 1–16
  pet grows in expedition-only statistics and effects, and has visual milestones.
  It must not alter competitive results in Rhythm, Minesweeper or Mafia.
- The approved care direction is a 0–100 endurance model whose active pet loses
  endurance gradually (target: 10 per 24 hours); food restores it. Slot swaps
  must be server-authoritative and consume endurance to prevent temporary-slot
  abuse. Exact costs, thresholds, food sources and stat numbers remain pending
  the economy/balance wave.
- A trek is timer-only. An expedition has a 3/6/9-hour server timer followed by
  an interactive route, shared safely between Mini App and Telegram with one
  authoritative state/revision. The requested single shared active-slot rule
  still needs explicit confirmation because "one timer" may mean one total slot
  or one slot of each type.
- The owner permits two Zarniki-bought keys per account per day and limited
  paid expedition help that provides information or risk mitigation but never a
  guaranteed win. No exact SKU, price, reward table, odds, reset boundary or
  paid-item effect is approved yet; these are Wave 3 decisions.
- Refunds remain a manual owner review through `/paysupport`; no automatic
  refund button. The public policy must nevertheless preserve timely handling
  of legitimate non-delivery, payment-error and other valid disputes under
  Telegram rules. It must not promise unconditional denial or unbounded owner
  discretion. Direct Stars commerce remains disabled until the payment/review
  contract and real Telegram test gate are complete.
- Owner policy clarification: a manual Stars refund is normally denied when the
  precisely described digital service was delivered and used; a confirmed
  project-side payment or delivery failure is refunded to the original payer.
  Product descriptions, receipts and delivery evidence must be specific enough
  to make that distinction auditable.
- Zarniki are approved for one-way conversion to Mora and Diamonds, subject to
  a conservative rate, server-side limits and a balance simulation that prevents
  a small Stars purchase from creating disproportionate pet power. No rate or
  limit is approved yet. Conversion to Dark Mora remains undecided.
- A future cross-surface overflow/compensation currency is approved in
  principle: it is minted when a player receives an already-maxed collectible
  (including a level-16 pet duplicate). Its name, supported overflow sources,
  catalogue and any power limits are not yet approved; it must be append-only
  and cannot be exchanged back into Stars.
- Resource sources will include quests and achievements in addition to treks,
  expeditions, training and chests. Quest/achievement writers must be designed
  as versioned server definitions plus immutable event and reward receipts; no
  memory-only completion counter is allowed.
- Quest design is delegated: definitions must be concrete, non-grindy and
  understandable without guessing. Do not create objectives requiring a
  particular augmentation combination or vague conditions such as "find a rare
  reward". Each quest may expose a concise explanation of where and how it can
  be completed. Players receive two server-authoritative rerolls per week; a
  reroll replaces an unfinished eligible quest with a random eligible quest.
  VIP receives five server-authoritative rerolls per week instead of the
  standard two. The implementation must still prevent rerolling completed or
  ineligible quests and must remain auditable.
- Quests and achievement rewards must not grant cosmetics. Economy/catalogue,
  rates and balance simulations are delegated to the agent, subject to explicit
  owner decisions only for real-money boundaries, paid advantage and refund
  policy.

## Implemented release slice — cosmetics visibility and fitting room (2026-09-05)

- Public profile and cross-surface cosmetic projections now fail closed when
  VIP is inactive. Ownership and the selected loadout remain durable; renewing
  VIP restores the same look without a new equip action.
- The Mini App has a separate owner-only `/appearance` wardrobe route and a
  fitting room. It contains no checkout, direct-Stars invoice, gifting or
  transfer writer. It displays the same profile-card structure used by the
  player profile and explicitly tells a non-VIP owner that the saved look is
  visible only in the fitting room. Transfer is labelled "in development".
- Verified with unit projection tests, Python/JS compilation and an isolated
  preprod browser smoke as `@codex_test`. Visual item-by-item art revision,
  the shared Zarniki shop, and the full public-profile renderer unification
  are still open; do not describe this slice as a complete cosmetic release.

Continuation (2026-09-07): the public-profile renderer and the fitting-room
renderer are now one shared Mini App structure rather than two approximations.
The fitting room deliberately renders the actual public projection alongside
the owner-only saved look, so inactive VIP cannot leak cosmetics to the public
card. Independent review found stale-after-equip preview state and missing
release-wardrobe CSS; both were corrected, with refresh-after-write and a
single-client-operation guard. A catalogue audit confirms 134 cosmetics across
six slots and ten lineups: every item has one unique CSS token, with no absent
token. The 2026-09-09 production DOM audit additionally found no actual card,
swatch or name overflow across all 134 entries. A second independent review
found and closed mixed frame+halo loss and five pseudo-element reduced-motion
escapes; visible saved-look DOM contains both `frame-artifact` and `halo-dust`.

Continuation (2026-09-09): **Образы** is now the shared Zarniki store,
not an owner-only wardrobe. A paid SKU can no longer carry an effective VIP
display gate; non-purchasable service entitlements retain that capability.
Item/set/whole-app-skin purchases use authoritative prices and idempotent ledger
mutations. Insufficient balance opens the existing server package/invoice flow;
preprod correctly presents its fail-closed payment state and no invoice was
confirmed during QA. The preview is a modal, focus-managed collection look and
Back/Escape close the nearest layer before leaving the collection or store.
Browser smoke used visible loopback `@codex_test`; exact-code full preprod
regression completed **89/89 passed**. Manual art-direction review across the
narrow-screen/motion matrix remains open. The catalogue has ten lineups, but only
Hanami, Moon Lotus and Ryujin Tide currently have server-curated six-slot
looks; define the other seven together with the separate shared Zarniki shop
rather than exposing a partial store through the fitting room. Stable external
hosting and real Telegram release verification remain open.

## PET-001 — replacement pet foundation (2026-09-05, in progress)

| Field | Evidence |
|---|---|
| User path | Choose an active pet → its endurance drains slowly; switch it out without a free temporary buff exploit. |
| Root cause | The archived companion implementation still uses lore, 2/6/12-hour routes and retired game/economy effects, so it cannot be re-enabled for the approved product. |
| Implemented | `core/pets_v1.py` defines level 1–16, 0–100 endurance, 10 points/day drain, server-side five-point active-slot switch cost, and only 3/6/9-hour trek/expedition duration validation. Effects are explicitly expedition-only. |
| Negative proof | `tools/test_pets_v1_rules.py` rejects levels outside 1–16, old durations, clock rollback, underfunded slot switches and verifies same-slot idempotence. |
| Remaining stop-ship work | Add durable PostgreSQL state/action receipts and Mini App/chat adapters; design the duplicate-to-level-up and overflow-compensation writer; do not enable a route or economic reward until those contracts and tests exist. |

Continuation: durable `pet_v1_*` state and action receipts plus the authenticated
`/pets-v1/active` adapter are implemented. `tools/test_pets_v1_pg.py` proves
owner isolation, exact slot debit, replay and conflicting idempotency payloads
against isolated PostgreSQL. The Mini App and the read-only `бот питомцы` /
`бот питомец` renderer share one projection; its `startapp=pets` route is
visible-tested. One shared 3/6/9-hour `pet_v1_runs` timer now accepts either a
timer-only trek or an expedition and fail-closes a second active/ready run; it
can only become `ready`, never credit loot. A ready expedition accepts one
server-authoritative, idempotent `careful` / `steady` / `bold` route choice;
it does not resolve an outcome, award a reward or allow a second choice.
PostgreSQL proof covers no-active rejection, replay, cross-kind double-start
rejection and one-choice-only. The internal duplicate writer now raises a
specific owned pet from level 1 through 16 and turns further duplicates into
exactly one Echo Shard with an immutable progression receipt; it is not exposed
to clients and awaits a future verified loot source. Care/food and expedition
outcome/rewards remain unimplemented.

The same timer is also available in chat through `бот поход, 3|6|9` and
`бот экспедиция, 3|6|9`; its ready-expedition choice is likewise shared through
`бот маршрут, осторожный|ровный|рискованный`. Strict parsing rejects legacy or
ambiguous durations and routes.

## QUEST-001 / QUEST-002 — quest foundation and varied mobile log (resolved locally 2026-09-10)

| Field | Evidence |
|---|---|
| User path | Player opens clear daily/weekly tasks, replaces an unfinished task, then finishes an eligible activity. |
| Root cause | The historical quest surface was retired and its implicit assignments/rewards cannot safely be reopened. |
| Implemented | `quest_v1_*` keeps immutable definition snapshots, action and terminal-metric receipts. `/quests-v1` assigns 4 daily/5 weekly objectives from unique lanes and round-robin available sources; 2 weekly rerolls are enforced server-side (5 only after server VIP check) and cannot return an occupied metric/lane. Rhythm records completion, mode and verified 500-score events; Minesweeper records completion plus win/difficulty only after a win; Mafia records completion for each participant and a win only for the winning faction. Mafia assignments additionally require prior player participation. The Mini App can claim transparent free-Mora rewards of 20/100/75; no cosmetic, Stars, Zarniki or random drop is minted. |
| Negative proof | `tools/test_quests_v1_pg.py` proves unique lanes/metrics, source balancing, reroll/replay/conflict/limits, collision-safe zero-progress policy migration and atomic 195-Mora claims. Rhythm/Minesweeper/Mafia PostgreSQL proofs assert the exact metric set for each terminal outcome and no duplicate on retry. Visible preprod confirms 4 varied daily plus 5 balanced weekly goals, explicit 20/100/75 reward progress, accessible modal naming/focus return and no overlapping floating Back. |
| Remaining stop-ship work | Pet-care and chest objectives are intentionally absent from the active rotation until their terminal receipts exist. The read-only chat renderer (`бот квесты` / `бот задания`) opens the same Mini App `questlog` and deliberately has no writer. The current quest expansion passed an independent read-only implementation review; the next financial/content expansion still requires its own economic review before release. |
