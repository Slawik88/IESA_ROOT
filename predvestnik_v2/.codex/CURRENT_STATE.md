# Current state

## DESIGN-004 — monolithic navigation and explicit top-up confirmation (2026-10-07)

The first production design wave is implemented locally. The `More` surface is
now one continuous route list rather than a grid of equal cards; its mobile
routes are 72px tall, the fixed navigation targets are 52px tall, and a live
390x844 preprod measurement has zero horizontal overflow. Zarniki purchase is
now a two-step choice: one package has a filled/checkmarked selected state,
the exact Zarniki credit and Telegram Stars debit are repeated in an order
summary, and only a separate amount-specific CTA opens the invoice. Secondary
text contrast is raised globally and the player-facing update uses direct copy.
Syntax, JSON, static delivery, surface parity, release-profile, whats-new
resilience, navigation, development notice and text-wrap checks are green. The
independent visual critic rejected mixed emoji icons; they were replaced with
one 21px/1.8px outline SVG family, keeping gold only for Zarniki, and the live
390x844 re-review returned ACCEPT. Next: commit/push this wave, then continue
the same monolithic treatment directly on dev for the profile/looks surfaces;
Figma remains a reference rather than a mandatory implementation gate.

## SHORT-002 — frozen-claim recovery boundary (2026-10-06)

Frozen lender principal and unpaid interest are both guarded: their identities
and original amounts cannot change, and remaining balances only decrease through
a reserve-backed settlement. Interest settlement now has a deferred database
invariant requiring one matching immutable reserve-ledger debit for every claim
reduction; raw SQL cannot mark it settled for free or fabricate an unrelated
receipt. A second deferred invariant keeps each original interest claim's frozen
amount exactly equal to its frozen claim. The server worker uses durable circular
cursors for both open positions and frozen-claim coins, so early healthy markets
cannot starve later risk or recovery work. It uses one fixed 5% UTC-hour reserve
snapshot, pays the canonical Mora ledger and never trusts an unexecuted ask as a
cash oracle: principal recovery uses meaningful historical VWAP with a 5% haircut.
The liquidation executor calculates margin from live escrow, includes real book
fees when sizing a partial close, keeps halt/no-mark positions untouched, and
converts a qualified no-depth full default into immutable claims rather than
silently losing lender debt. PostgreSQL proves mutation guards, capped recovery,
full liquidation, shortfall freeze and scheduled worker paths; schema v20 has
been exercised. The full isolated preprod gate is 114/114 and the independent
read-only audit accepted the recovery boundary. Commit `f6e1065a` is on
`origin/master` and Notion records the result. Public flags remain off: the
hidden backend is complete, but a player rollout is intentionally a separate
future task requiring a live rollout plan and explicit owner decision.

## EXCHANGE-002 — pre-Shorts Spot integrity correction (2026-10-05)

Independent release audit found two owner-market defects before Shorts work:
an existing treasury sell was omitted from the delayed-emission guard, and a
treasury buy and sell could cross each other and repeatedly violate the immutable
no-self-trade ledger constraint. The correction treats every owner sell (personal
or treasury) as an emission blocker, rejects a newly crossing treasury order, and
releases the newer side of a legacy treasury self-cross instead of attempting a
trade. Real PostgreSQL now proves all three paths. The focused contract passes;
the full gate was started but its runner output was truncated by the host after
initial passing tests, so rerun it before public enablement. Public Spot and all
Shorts flags remain off. Next: commit/push this protective wave, then create the
hidden per-coin Shorts state/ledger foundation using the fixed hourly frozen-claim
buyback budget in the specification.

## SHORT-001 — segregated hidden foundation (2026-10-05)

The dedicated Shorts flag is explicitly disabled by default. The hidden schema
now gives every coin its own non-negative Shorts reserve, lender position, exact
loan allocation, short position, frozen claim, immutable reserve receipts and a
single fixed UTC-hour buyback budget (5% of its locked reserve snapshot). Composite
foreign keys prevent claims from crossing coins, positions or lenders. Deferred
reconciliation rejects mismatched lender/loan/claim and position/loan totals at
commit; the first frozen claim pauses new Shorts for that coin. New Spot fee
insurance stays in the historic global fund until the separate Shorts flag is
deliberately enabled, after which the 30% share is appended only to that coin's
reserve. PostgreSQL proves default-off, cross-lender rejection, no negative
reserve, frozen debt closure, frozen pause, fixed budget, system receipt replay
denial and fee segregation. Focused model and 100k simulation stay deterministic.
No player writer, API or UI exists yet: public Shorts remain NO-GO. Next: add the
locked lending deposit/withdrawal and atomic allocation service, keeping the flag
off and extending the real PostgreSQL failure matrix.

The first player-safe writer is now complete locally: with both Spot and the
separate Shorts flag explicitly enabled, a lender may deposit owned coin units
into the voluntary pool and withdraw only its free balance. Both operations are
under the shared Spot lock, use global immutable action IDs, reject mismatched
replays, and cannot move a loaned or frozen unit. PostgreSQL proves the default
closed flag, replay, insufficient free withdrawal and exact token conservation.
The public flag remains off and no API or Mini App route exposes this yet. Next:
atomic pro-rata loan allocation and its borrow/open position transaction.

The voluntary lending writer and deterministic pro-rata allocation are now on
production master but still unreachable to players while the explicit Shorts
flag is off. PostgreSQL proves free-only withdrawal, action replay, lender/loan
reconciliation and exact allocation persistence. A server-owned eligibility
snapshot now floors market age and combines age, trades, participants, weekly
volume and ±5% depth into one verdict. Next: implement an atomic open path that
uses the allocation only after verifying full protected sell liquidity, locks
borrower collateral plus sale proceeds, and never leaves a partially sold loan.

The owner has chosen the insolvency boundary: the per-coin Shorts reserve never
goes negative, no Mora is minted and lender principal is never socialized. A
gap therefore creates immutable frozen claims and pauses new Shorts until that
coin's future segregated reserve buys them back. The first atomic-sale migration
is now locally proven: a short order is position-bound, IOC-only and cannot be
created by the ordinary player path; the position has a unique collateral
receipt, and trade history recognizes a short seller without exposing a public
writer. Locked eligible-bid selection excludes the borrower, coin owner,
treasury and dual-signal owner-linked accounts. No matcher/service uses the
new primitives yet; next is one all-or-nothing executor and its PostgreSQL
rollback matrix. Public Spot and Shorts flags remain off.

That executor is now implemented and proven in isolated PostgreSQL. It locks
the global Spot guard, flags, coin, reserve, allowed bid/ask rows and lender
rows before re-reading every gate. It requires both complete eligible sell depth
and a complete eligible buyback depth plus qualified five-minute VWAP; 200%
collateral is debited by an immutable economic receipt, lender units are
allocated, and a position-bound IOC sell fills only inside that one outer
transaction. Net sale proceeds never reach the borrower wallet: they are
credited only to the position. A duplicate action replays the same position;
an injected failure on the second bid rolls back the first fill, collateral,
position, loans and fee writes. The public flag remains off, and no API/UI
route exposes Shorts. Next: add reduce-only closing, interest/margin snapshots
and frozen-claim conversion/buyback before any player interface.

Independent close-side review found that a counter-only position escrow would
permit an underfunded or double-release close. Schema v15 now gives every short
position a non-negative cash escrow balance and append-only receipt ledger.
Opening writes one collateral receipt and one receipt for each sale fill; the
cash balance is proven equal to collateral plus net proceeds and cannot be
mutated directly. The schema also reserves a position-bound IOC buy actor for
the later close executor and adds accrual fields, but no close writer exists
yet. Next: exact loan repayment and interest accrual receipts, then a
position-bound atomic buyback/close path. Public flags remain off.

Exact principal-repayment foundation is now proven: a protected buyback may
return fewer than all borrowed tokens, and the units are split across the live
loans proportionally with deterministic residuals. In one outer transaction it
decreases each loan, returns units only to that lender's available pool and
reconciles the position debt. A final repayment requires an explicit close,
which prevents a zero-debt position staying open. PostgreSQL catches a missing
outer transaction as an invariant breach; the actual contract proves partial
and final repayment under one transaction. Next: wire this primitive to the
position-bound protected buy executor, cash-spend journal and borrower surplus
release; then introduce authoritative interest accrual. Public flags remain off.

Interest foundation is now also present. Opening locks a non-negative APR based
on the pool's post-open utilisation and stores the server accrual checkpoint.
Only whole elapsed server minutes are charged; fractional time carries forward,
and each positive accrual is an immutable row containing the APR, mark and exact
amount. Final principal repayment now fails closed while interest is unsettled.
The isolated PostgreSQL proof covers the checkpoint, no mutable receipt and
the existing open/replay/escrow invariants. Next: settle accrued interest from
position escrow to current lenders and combine it with the protected buyback
executor; public flags remain off.

## EXCHANGE-001 — player-created coin Spot MVP foundation (2026-09-26)

Owner approved the complete player-created coin exchange specification. The
default-off foundation and launch auction are implemented separately from the
retired lore exchange. Creation and bidding use canonical wallet operations;
genesis, treasury Mora, bids and settlements have append-only receipts. The
24-hour auction uses deterministic uniform-price clearing, stable pro-rata
remainders, strong owner-link exclusion, atomic success/refund settlement and a
retry-safe maintenance worker. Loopback PostgreSQL proves concurrent settlement,
success/failure conservation, duplicate protection, immutable history and poison
auction isolation. Independent audit accepted the hidden wave. Commits
`23479649`, `bedc7cf2`, `4a042d24`, `022f036f`, `bbaaec1d` and `762c170e` are on production master.
The hidden GTC Spot foundation now adds atomic Mora/token reservations,
best-price/time matching every 15 seconds, maker/taker fees with 70/30
burn/insurance accounting, self-trade prevention, cancellation, partial fills,
immutable trade receipts and poison-market isolation. PostgreSQL covers normal,
split-fill, cancellation, self-cross and cross-price dust conservation; an
independent audit accepted the default-off wave. Public redacted book/trade/24h
stats and volume-weighted 5m/1h circuit breakers are also implemented. Adjacent
VWAP windows require 100 Mora meaningful volume, preventing cheap outlier DoS;
cancel remains available during a halt. Atomic protected market orders now use
the best opposing quote with owner-selected 1/3/5% slippage, strict BUY-down and
SELL-up tick rounding, and create/match/cancel the residual inside one outer
transaction. PostgreSQL proves exact partial settlement, full reserve release
and idempotent replay; the independent audit accepted the hidden wave. The
feature stays disabled and has no UI. Developer-only manual halt controls now
accept a public reason and 5-minute-to-24-hour duration, are coin-bound and
idempotent, and expose only the redacted player-safe halt state. An active
manual halt cannot be overwritten by an automatic breaker. PostgreSQL and an
independent audit accepted the default-off wave. Successful auctions now create
one deterministic, public five-level treasury ladder on each side at ±2/4/6/8/10%
around the clearing price. The ladder reserves only existing treasury Mora and
market-reserve tokens, participates in the ordinary matcher and fees, updates
circulating supply in both directions, and cannot be silently cancelled through
the owner's player endpoint. PostgreSQL proves settlement replay, owner-cross
prevention, both trade directions, fees and reserve conservation; independent
audit accepted the hidden wave. Public aggregate market data now includes best
bid/ask, midpoint spread percentage, strict inward-rounded ±5% depth,
five-minute VWAP/volume and circulating-supply capitalization. The live
reference prefers five-minute VWAP, then the latest trade, then the successful
auction clearing price. Low-price boundary and no-trade launch cases are
covered; independent audit accepted the default-off wave. The deterministic
Spot stress gate now runs 100,000 independent auction+mutable-order-book markets.
Seed 20260927 executed 146,082 trades across partial fills, IOC residuals,
cancellations, both maker sides, self/owner-treasury prevention, treasury trades
and halt transitions while proving exact terminal Mora, token, reserve, fee and
circulating-supply conservation. Two runs produced digest
`787ced1d12b61668b166d8f975e6fb9d84b9b2df50c3a140492593f61021fdd5`;
independent audit accepted the gate alongside PostgreSQL concurrency tests.
Final readiness: hidden/default-off backend GO; public enablement NO-GO. Full
isolated preprod is 112/112 and production HTTP is 26/26. The matcher now takes
the Spot lock and a shared lock/recheck of the feature row inside every trade
transaction, closing the kill-switch race; PostgreSQL proves a crossed book
cannot trade after disable while both orders remain cancellable. Remaining
public gates are the player creation/trading UI with risk and no-cash-out
disclosures, and one live halt→blocked trade→cancel→expiry/resume exercise.
Authenticated `/player-exchange/v1/me` recovery is complete: it exposes only the
actor's holdings, player orders, auction bids and owned coins, stays available
during the kill switch for participants, keeps empty outsiders hidden, and uses
strict owner-bound cursor pagination for every collection. Open orders and bids
sort first; malformed/wrong-list cursors fail as HTTP 400 before SQL. The real
PostgreSQL contract proves the 101st order is recoverable without duplicates,
foreign IDs do not leak and the payload serializes. Independent review accepted
the wave. The functional Mini App surface is now implemented behind the same
default-off flag: portfolio, owned coins, auction bids, open-order recovery and
cancellation, market statistics, book, trades, coin creation, auction bidding
and limit orders. Protected market orders remain backend-only until their quote
is bound to the user's confirmed absolute limit. Participants retain recovery and
cancellation access while the kill switch is off; outsiders see no entry.
Buy/sell and non-cancellable auction reservations have explicit final
confirmations with bounds, fees and reserve/refund disclosure. The monolithic UI
uses readable secondary text, explicit 44px states and the no-cash-out risk
statement. Full isolated preprod is **113/113**. Public flag remains disabled
pending one live halt→blocked trade→cancel→resume exercise. Owner controls and
shorts remain later non-blocking phases.

Owner-controls wave 1 adds public delayed emission. An owner may request at most
10% of the circulation snapshot, with an immutable reason, projected total
supply and 24-hour execution time visible to everyone. Only one request may be
pending; requests are seven days apart and may be cancelled until the final
hour, including while the exchange kill switch is off. Execution pauses while
disabled and mints only into the public treasury, never the owner's wallet.
Pending dilution blocks both new and pre-existing owner SELL paths under the
global Spot lock while owner BUY remains allowed. PostgreSQL covers replay,
foreign cancellation, disabled cancellation, existing-order bypass, both limit
and protected SELL paths, supply conservation and public redaction. Independent
review: ACCEPT; full isolated preprod: **113/113**. The public flag remains off.

The delayed-emission Mini App surface is complete locally: owners get a final
review before publication, public rows show dilution basis, projected supply,
request time and truthful scheduled/executed/cancelled timestamps. Recovery
exposes pending emissions while the kill switch is off and keeps cancellation
reachable until PostgreSQL's authoritative final-hour boundary. Request and
cancellation action IDs survive ambiguous retries. UI/static/real PostgreSQL
checks and the full **113/113** preprod gate pass; independent review: ACCEPT.
Next: commit/push this hidden wave, verify production markers, then implement
the remaining owner treasury/liquidity/vesting/journal controls before shorts.

Owner-controls wave 2 is complete locally: the 20% owner allocation uses the
actual successful settlement timestamp, a 30-day cliff and linear 180-day
vesting. Claims transfer an exact owner-confirmed unit amount, update
circulation atomically, are replay-safe and cannot grow between review and
execution. The public governance journal is allowlisted/redacted and excludes
ordinary trades so activity cannot hide emissions, halts or vesting. Migration,
stale-quote, concurrency, privacy and UI confirmation regressions pass;
independent review: ACCEPT; full isolated preprod: **113/113**. Next: push the
hidden wave, then implement treasury buy/sell/burn and liquidity controls.

Owner-controls wave 3 is complete locally: public treasury balances and open
orders are visible to all market viewers. The owner may publish a normal
public treasury buy/sell limit order or burn only free treasury tokens, each
behind an explicit confirmation, exact replay key and append-only public
receipt. Treasury sells preserve their source bucket; buy cancellation stays
available through `/me` even with the global flag off, except while a pending
emission protects a treasury buy. Treasury orders obey the same 10-Mora floor
as player orders; dust cannot alter market signals. Focused PostgreSQL/UI and
the full **113/113** preprod gate pass. Next: commit/push this hidden wave,
then add owner-funded liquidity and delayed, capped liquidity withdrawal.

Owner-controls wave 4 is on production master in `ca186ce2`, still protected by
the default-off exchange flag. An owner can add Mora from the canonical wallet
to a public treasury and request a public treasury withdrawal only after 30
days from launch. A withdrawal is capped at 10% of its immutable treasury
snapshot, waits 24 hours, permits only one pending request, and starts a seven
day cooldown only after successful execution. It remains cancellable and
recoverable while the global exchange flag is off; execution itself pauses while
the flag is off. Wallet credit, treasury debit, execution receipt and public
journal event are one transaction under the shared Spot lock. The Mini App has
two-step confirmation and explains permanence, the 24-hour wait and the cap;
the public market shows request/execution/cancellation history. Focused real
PostgreSQL and static UI checks pass; independent read-only audit: ACCEPT.
The first full preprod attempt had one unrelated concurrent legacy DDL trigger
failure in `test_achievements_v1_pg.py`; its sequential rerun and the complete
isolated gate pass **113/113**. Production HTTP boundary verification is
**26/26**. Next: build the Shorts simulation gate and obtain the separate risk
review; actual Shorts remain blocked on that gate and real Spot observation.
Independent Shorts review confirms a simulator-only GO and runtime NO-GO: before
even the simulation contract can become a production rule, the owner must close
the exact margin/mark/partial-liquidation/interest rules and, critically, the
insurance-insolvency backstop. “No socialization” cannot guarantee lender claims
against an unlimited price gap without a specified bounded reserve or hard loss
bound. `SHORT-001` now records that decision boundary in the autonomous backlog.

The distinct pure Shorts model is now implemented in
`core/player_exchange_shorts_v1.py`, with a 100,000-scenario deterministic
simulation in `tools/simulate_player_exchange_shorts_v1.py`. It proves caps,
owner/linked denial, qualified VWAP plus executable-buyback marks, strict
150%/120% boundaries, halt/interest freeze, partial recovery to 200%, and
fail-closed insurance insufficiency without reducing lender token claims. Seed
`20261005` reproduced digest
`29c4b9afecc9525b724f6d22b9a00703651898798ba0a81d63ad0767e78cac18`.
The model purposely reports `MODEL_PASS_NOT_RUNTIME_APPROVAL`: it observes
35,933 of 100,000 gap cases where an arbitrarily chosen insurance balance is
insufficient, so the missing bounded backstop remains a real product decision,
not a test defect. Full isolated preprod is now **114/114**.

The formerly manual Spot release exercise is now a real PostgreSQL contract:
two crossed orders remain open during a manual halt, the buyer can cancel while
paused, the server-owned halt deadline is advanced, and the remaining seller
fills after the resumed matching pass. This closes the halt→blocked trade→cancel
→expiry/resume evidence gap without claiming a public enablement. Full isolated
preprod remains **114/114**.

## DESIGN-REDESIGN-001 — implementation gates and cosmetics migration (2026-09-27)

The owner requires a monolithic, theme-ready redesign rather than nested cards.
Production acceptance now includes readable secondary text, explicit selected
states, 44×44 touch targets, restrained development notices, emotional chest
reveals, stable navigation naming, one primary action per screen and truthful
financial hierarchy. Cosmetics may change semantic atmosphere tokens but never
information order, hit areas or the contrast floor. Figma inspection found
additional risks: accent overuse, capsule-in-capsule bottom navigation, duplicate
wallet selection, decorative exchange data without time/scale context and
singular/plural navigation drift. The Figma Starter MCP quota prevented canvas
writes in this pass; these are recorded in
`docs/DESIGN_IMPLEMENTATION_GATES_2026-09-27.md` and must be applied when the
connector quota is available.

The owner also approved a future controlled cosmetic redesign migration. New
purchases must close server-side, then a frozen ownership/payment snapshot maps
each current item to either its redesigned successor with ownership preserved or
one exact Zarniki refund. Previously retired/compensated items are excluded from
a second refund. Apply must be append-only, replay-safe and rehearsed on a restored
production snapshot; purchases reopen only after catalogue, mobile/theme and
receipt reconciliation gates pass. No production snapshot or mass write has been
run yet. Plan: `docs/COSMETICS_REDESIGN_MIGRATION_PLAN_2026-09-27.md`.

## OPS-DB-001 — production connection exhaustion (2026-09-26)

Owner-provided production logs showed transient Telegram 502s recovering on
their own, followed by the real incident: `TooManyConnectionsError` while the
bot middleware acquired PostgreSQL. FastAPI starts before bot DB initialization,
so a concurrent readiness request could enter `create_pool()` with `_pool=None`
at the same time as main startup. Both calls created a 15-connection pool; one
reference was overwritten without closing its live connections. Commit
`8a0448f4` adds single-flight pool creation and reduces the default per-process
maximum to five (configurable, clamped to 2..10). A 25-caller concurrency test
proves exactly one pool. Full isolated preprod passes **110/110**. The fix is on
production master; HTTP readiness and the 26/26 production boundary gate pass.

## VIP-003 — approved functional implementation (2026-09-26, release-ready locally)

The first non-visual VIP wave is implemented locally. One product exposes the
owner-approved 7/30/90/365-day packages at 140/600/1800/7300 Zarniki. A purchase
uses the canonical economic ledger, an immutable `vip_v2_purchases` receipt, a
stable client action id and one outer transaction that extends from the later of
the stored expiry or now. Historical tier IDs remain readable; new purchases
store canonical tier `vip`. The status API exposes 20 badge choices and persisted
left/right/both/hidden placement plus reminder preference. The current profile
has a functional purchase/settings modal; redesign remains deferred.

Any active VIP now has five quest rerolls and a 10-question assistant cap. Daily
and weekly quest completion awards are 10% higher in Mora; combined rewards are
unchanged. Claim resolves VIP again after the user lock so expiry/purchase races
cannot change the immutable credited amount. Independent review found the schema
ordering and expiry-race risks before release; both are corrected. Python/JS
syntax, quest rules, AI cap, profile release and product-surface checks pass.

The owner approved the daily reward contract: one completed trusted game per UTC
day grants 20 Mora; every seventh completed mission additionally grants 100 Mora
and one typed chest key. Missed days do not reset the completion counter. The
server status projects the current UTC assignment and progress; Rhythm,
Minesweeper and Mafia terminal quest metrics are the only completion writers.

The loopback PostgreSQL contract proves same-action replay, concurrent distinct
extension, insufficient-funds rollback, one daily credit under two terminal
deliveries, reminder stopping and append-only receipts. It exposed and fixed
three real defects before release: concurrent lazy DDL, asyncpg date binding and
a misplaced daily-progress update. Schema checks now take a fast read path and
serialize only first installation.

Follow-up: the shared Telegram profile/name renderer and message-top renderer now
consume persisted badge choice and left/right/both/hidden placement. The daily
maintenance loop receives the Bot adapter and, after 18:00 UTC, sends at most one
private reminder per day. Only successful delivery increments the missed counter;
after two delivered reminders without a completion it stops. A later completion
resets the counter. Reminder delivery failures do not count as ignored days.

Private and public Mini App profiles project the selected badge and position;
generic legacy VIP-name call sites use the neutral current `✦` fallback instead
of a hardcoded crown. Player-facing patch notes are written in plain language.
The complete isolated preprod gate passes **109/109** and focused syntax/import,
JSON, updates-feed and diff checks pass. Current branch is
`backup/no-deploy-2026-08-25-195138`: no commit, push or production deployment
has been performed. Next action is explicit release integration into the
production branch, followed by production HTTP/Telegram smoke; visual redesign
remains the next separate wave.

## REL-001 — final production readiness audit (2026-09-24)

Production HTTP boundaries and release markers pass **26/26**. A detached
checkout of the prior production commit `f8da5d43` passed all **107/107
application tests** against the current post-release preprod PostgreSQL schema;
the separate workspace-document router assertion is not an application test.
The rollback runbook uses a normal revert commit, never a database restore, and
has target-specific HTTP markers via
`tools/verify_production_http.py --profile rollback-f8da5d43`. The compatibility
rehearsal is not represented as an exercised DigitalOcean rollback. The sole
remaining P0 public-launch gate is an owner-authorized minimum Stars purchase
plus cancellation check; automation must not spend the owner's Stars without
explicit approval.

## LEGACY-DELETE-001 — dependency-proven removal (2026-09-23)

Eight unreachable FastAPI routers and three superseded Telegram
profile/identity/VIP handlers were removed after dependency checks. Account
deletion recovery was preserved in the dedicated `account.py` router. The
independent review accepted the corrected wave, the isolated preprod gate was
**108/108**, and commit `f8da5d43` is on production master.

## QA-TELEGRAM-002 — autonomous Mini App UX pass (2026-09-23)

The authenticated isolated-preprod Mini App was exercised at a 320 px Telegram
viewport. Profile, cosmetics, games, More, pets, quests, chests, achievements,
chat tracker and settings opened without visible error or horizontal overflow.
Header actions, back controls, fitting-room entry and profile section actions
now meet a 44 px touch target. The header identity block shrinks and ellipsizes
long names without pushing actions off-screen. Production Stars→Zarniki invoice
issuance remains enabled; isolated preprod still blocks real Stars and now says
so explicitly. The Mini App and `/start` both state that the large update has
not launched and that much of the product remains hidden during development and
testing. Full isolated preprod: **108/108**; independent review: ACCEPT. Commit
`436f90fe` was pushed to `master`; DigitalOcean rollout and production markers
are verified.

## UX-004 — mobile profile, compensation story and pet bestiary (2026-09-20)

The production screenshots proved that the paid Void Atlas wallpaper was
cropped like a wide cover and then hidden by nearly opaque flat panels on a
Telegram phone viewport. The skin now uses portrait-height responsive sizing,
a mobile focal point and translucent blurred surfaces. Profile information
cards use layered surfaces and hierarchy rather than uniform bordered rows.

VIP is a dedicated prominent account-status card with tier, remaining days and
the exact expiry date. The private profile reads the immutable
`retirement_compensation_receipts_v2` row and renders a replayable personal
migration story: retired cosmetics, themes, paid inventory and exchange spend
flow into the actually credited Zarniki, Mora, Diamonds and migrated VIP time.
The animation runs once automatically per snapshot, remains replayable and is
disabled by `prefers-reduced-motion`. No public profile receives compensation
details.

The pet overview now includes the canonical 12-species chest catalogue with
owned state and collection totals. The Mini App has separate owned-pet and
bestiary tabs, a completion hero and locked silhouettes. Help and What's New
were updated to match the shipped behavior. The authenticated isolated-preprod
runtime returned a 12-row bestiary, static/runtime checks pass and the full
preprod gate is **106/106**. Remaining release step: independent read-only
critique returned ACCEPT after the receipt stopped presenting migration targets
as live balances, split preserved/bonus VIP, pinned the Zarniki result on mobile,
and parsed asyncpg JSONB correctly. Display-only source summaries were SHA-256
validated and backfilled for all 253 receipts without touching wallets or
entitlements. Commit `4a4185a9` is deployed on production master; readiness,
new JS/CSS markers, What's New delivery and the unauthenticated 401 boundary are
verified on the production domain.

## LCB-002 — production compensation snapshot (2026-09-19)

Owner supplied the DigitalOcean PostgreSQL DSN after allowlisting the current
workstation. `defaultdb` was empty; the actual `iesaroot-db` database contains
107 `predvestnik` and 152 `public` tables. The production connection was used
only with `default_transaction_read_only=on`. A full custom-format `pg_dump`
was saved locally as `.codex/snapshots/production-pre-compensation-2026-09-19.dump`
(2,573,259 bytes, 1,436 TOC entries, SHA-256
`0CBF07AA4BF4B50529F0558D5AE3F6AA0400D85E856426BD0CF8C62368694FE2`) and
restored into the separate loopback database
`predvestnik_comp_snapshot_20260919`. Snapshot artifacts are git-ignored.

The aggregate retirement audit runs against that local copy after correcting
legacy UTC `timestamp without time zone` handling. It found three unfinished
legacy battles, two legacy expeditions owned by two users with 157 prepaid
Mora, and retained clan assets/progress requiring policy; no pending duel,
raid, shadow-gate or clan-war settlement was found.

`tools/build_compensation_inventory.py` emits a deterministic per-user dry-run
inventory from a repeatable-read local snapshot. Owner policy converts all 84
legacy cosmetic entitlements and 228 themes to Zarniki instead of preserving
their incompatible visuals. Cosmetics use their exact catalogue Zarniki price;
themes use their direct legacy Zarniki price or one fixed rarity table. The
result is 69,700 + 55,570 compensation Zarniki on top of 24,697 carried current
Zarniki. Retired paid inventory adds 670 Zarniki. Immutable wallet history proves
that six users also spent 13,852 Zarniki in the retired exchange for 1,730,250
Mora and 115.85 Diamonds. V4 refunds that spend exactly once and excludes its
proceeds from legacy score, producing 164,489 final Zarniki. Gross historical
Stars credits are never added separately.

`tools/apply_retirement_compensation.py` requires the frozen inventory hash,
creates one immutable per-user receipt, uses the canonical economy ledger,
removes converted legacy assets and is replay-safe. Owner-approved non-paid
progress uses tiered old Mora/Diamond balances plus fixed item, pet, unit and
relic values; component caps and a final 2,000-Mora/user cap prevent a legacy
whale from dominating the new economy; 157 prepaid Mora from two unfinished
expeditions is refunded exactly outside that cap. The universal 21-day VIP grant
is removed. Remaining uncompensated value becomes 25,007,699 immutable score and
continuous VIP time: first 300k at 10k/day, next 700k at 20k/day, remainder at
50k/day. No score is lost to whole-day rounding. Median bonus is 3.32 days, p90
17.11, p99 64.11 and maximum 97.87 days. Existing active VIP remains additive.
The frozen v4 inventory hash is
`3b32eb67929c6acd461e580dc40dcb4a6a502c89d0f7afb4a0fd0f706a154ed9`.
A full apply rehearsal on a fresh restored database produced 253 receipts,
131,449 Mora (maximum 2,067/user including exact refund), 1,139 Diamonds
(maximum 20/user), 164,489
Zarniki, zero retained legacy inventory/pet/unit/relic/cosmetic/theme rows and
246 score-based VIP bonuses plus preserved active subscriptions. The immediate
second run produced 0 applies / 253 replays. Randomized chest keys are excluded:
they would make equal score produce unequal settlement value.
Production compensation completed on 2026-09-20: all 253 frozen users have
matching receipts, aggregate receipt values equal the v4 inventory and no
inventory/pet/unit/relic rows remain for the migrated population. A deployment
reconciliation bug briefly replayed 36 historical Stars purchases to six users;
six canonical correction operations removed the duplicate 29,060 Zarniki and
the registered charge history prevents another replay.

## QA-TELEGRAM-001 — real test-chat transport (2026-09-20)

The owner designated supergroup `-1003723023833` for automated tests. Test bot
`@predvestnik_v2_bot` is an administrator with manage, delete, restrict, invite
and pin rights. Real Bot API probes proved send, edit, callback keyboard, HTTPS
button and cleanup/delete; no test message remains. The repeatable safe probe is
`tools/verify_telegram_chat_transport.py` and is on production master at
`4ccb74b6`.

Production bot `@IIIPredvestnikIIIBot` is also an administrator in the test
chat with all required rights. Its polling logs show a healthy startup and
handled updates. The same real transport smoke passed against production and
removed its test message.

The Mini App 404 was a DigitalOcean routing mismatch, not a missing service:
the existing `/predvestnik -> predvestnik-bot` rule trimmed the prefix while
the bot's `ROOT_PATH=/predvestnik` middleware deliberately required the full
path. The App Platform rule now uses **Preserve Full Path**. Production probes
confirm 200 for `/predvestnik`, `/predvestnik/api/health`,
`/predvestnik/api/ready`, `/predvestnik/static/app.js` and the IESA `/` site.
The temporary repository gateway experiment was removed; final master
`a546bcfb` keeps the original direct component architecture.

## CHAT-001 — Telegram chat product rebuild (2026-09-19)

Owner approved a chat-first rebuild after the Mini App work. Wave 1 replaces
the random bare `бот` response with a structured owner-bound home/help menu and
removes archive/economy/event tabs from discoverable help. Message rankings now
have exactly three scopes (current-chat players, players aggregated across all
chats, and chats) and four periods (today, week, month, all time). Local periods
use chat timezone; global boards use UTC. Aggregate queries were exercised
read-only against the production snapshot.

Chat settings now require both local rank and live Telegram manage-chat rights
at entry, not only on callbacks. The former one-wall settings card is split into
moderation, permissions, functions, activity/timezone and admin-routing sections.
Wave 2 adds one canonical registry for Mafia, Rhythm, Pets, Quests, social
actions and Echo. Both chat settings and the global developer controls consume
that registry. The shared module gate validates keys and covers messages plus
callback buttons; Mafia applies the gate only to new lobby creation so an active
match can still drain safely. Chat ranking has an explicit opt-out that affects
only the chat leaderboard, not players' aggregate totals. The old message-top
command and callback registrations are disabled, and the remaining category
bridge now opens the owner-bound V2 message top.
Message-top placement is now calculated by an uncapped deterministic SQL window,
so an actor outside the first 500 still sees the exact place and population.
Day/week/month cards compare against the immediately preceding period of equal
length. A rollback-only PostgreSQL contract proves stable tie ordering and the
privacy boundary: chat opt-out removes only that chat from the chat board while
player-global totals still include its messages.

Wave 3 completes the operator controls around that registry. Chat and global
switches now write append-only PostgreSQL receipts with actor, before/after
state, source, time and optional global disable reason. First global writes are
serialized, startup installs the immutability trigger without a drop window,
and missing rows use the registry default (including Echo being off). Mini App
chat settings save ordinary and module fields in one transaction. Disabling a
module requires a second confirmation in chat admin, developer console and the
Telegram settings card; Telegram rechecks live authority again on confirmation.

Divorce now starts a persisted 15-minute owner-bound intent with a property
snapshot. Settlement locks both the intent and active marriage, rechecks legacy
and ledger wallet balances plus family pets, archives the union with `ended_at`,
releases only active membership rows and writes one immutable receipt. Replaying
the same callback returns the original receipt without a second mutation, and
the partner receives a best-effort private notification. Non-empty family
property now has a deterministic atomic path: one explicit irreversible
confirmation splits all four currencies 50/50, assigns an indivisible remainder
to the lower Telegram id, alternates pets by stable pet id and closes the
marriage. Immutable summary and per-credit receipts bind initiator, beneficiary,
amount and both ledger operation ids. Both divorce paths use the same lock order;
a two-connection PostgreSQL proof covers the former membership/custody deadlock.
The unregistered broken `events_info.py` and developer writers for retired
exchange/daily-deal events were removed. Runtime scheduler already contains no
merchant/chest-event jobs; current no-reward Chat Echo and current Mini App
chests_v1 are deliberately retained. Remaining waves: dependency-proven legacy
deletion, then real Telegram group UX proof.

## GAME-004 — runtime scheduler cleanup (2026-09-19)

The bot scheduler now imports only the two background contours that the current
product actually starts: operational maintenance and Mafia phase advancement.
The unreachable legacy expedition, daily shop, auction/duel, Battle Pass,
crypto-alert, Smart Pulse, old chest-event and shadow-merchant jobs were removed
from `services/scheduler.py`, so importing the bot can no longer pull those
retired systems back into the runtime dependency graph. The obsolete no-op
streak middleware was also removed from startup and from disk; its contract
test now requires physical absence while retaining the historical read-only UI.

Focused release/navigation/surface checks, Python compilation, scheduler import
and diff validation pass. The corrected full isolated preprod gate passes
**103/103**. Production gates remain the owner-approved read-only migration
audit and real Telegram Stars purchase/refund exercise.

## QA-001 — trusted Rhythm, Minesweeper recovery and Chat Tracker (2026-09-14)

The shipped Rune Rhythm client now uses the ticket-authenticated WebSocket and
keeps one tap action ID across reconnects. A terminal server-timed run is not
trusted automatically: it becomes `review_required` and writes neither the
leaderboard nor quest/achievement progression. A developer-only API applies an
append-only `clear` or `quarantined` review; only `clear` releases the existing
idempotent leaderboard/progression writers. A transaction-scoped advisory lock
on the global review ID makes simultaneous retries linearizable. Independent
review first found that race and returned ACCEPT after the correction. Live
390×844 evidence shows the explicit pending-review result.

Minesweeper uncertain actions retain their action ID, block conflicting input
and refetch server authority. Recovery of a terminal loss now returns the same
revealed mine layout as the completing POST, rather than a stale hidden board.

The private Chat Tracker now provides literal-title search, four sorts, stable
paging, compact per-chat activity, streak and stripped moderation history.
PostgreSQL proof excludes left chats, foreign users and raw chat/admin IDs.
The live 390×844 page has no horizontal overflow, 44 px search/sort targets,
correct pressed states and no console errors. The current achievement system
has no chat-scoped receipt, so the tracker deliberately does not invent one;
that source decision remains in SOCIAL-002. Compensation remains deferred.

The final local Chat Tracker viewport pass is also complete. A 14-chat preprod
persona with an 88-character title and moderation history was exercised at
320×680, 430×932 and 1280×800. The page has zero horizontal overflow,
44–46 px search/sort/paging targets, stable 12→14 paging with focus returned to
the live status, ellipsized long titles, a centered 500 px desktop shell and no
console warnings/errors. Expanded moderation rows fit at 320 px. No code change
was required. Remaining QA-001 evidence is external: real Telegram transport,
Stars/payment recovery, production routing and rollback.

The retry audit then found two more client-side uncertain-response gaps. Chest
prepare/purchase and pet active-slot/activity/route-choice actions now retain
one operation ID until a confirmed success. Every failed pet mutation refetches
server authority, so an accepted activity whose HTTP response was lost renders
the already-running timer instead of inviting a conflicting new operation.
Chest prepare/purchase likewise replay the same operation rather than spending
a second key or another 10 Zarniki. Reveal remains keyed by immutable `open_id`.
The independent read-only critic identified pet activity start as the highest
risk and recommended this narrow recovery pattern. Client syntax, focused retry,
pet/chest PostgreSQL and HTTP contracts pass; full isolated preprod gate is
**103/103**.

## ACH-002 — durable achievement collection (2026-09-13)

The active achievement model now exposes five trusted terminal families:
Rhythm, Minesweeper, Mafia, chest reveals and completed pet activities. All
families keep the approved levels 1–40 curve; level 40 requires the family event
cap and 156 distinct active weeks. Legacy counters are never imported.

The Mini App page is now a mobile-first collection rather than a text dump. It
has **All / Games / Adventures** filters, a compact overall summary, exact
completion and active-week meters for the next level, explicit satisfied-goal
states, direct activity actions and optional milestones 1/5/10/20/30/40.
Milestones state that their Mora amount belongs to that individual level;
there are no cosmetic rewards. Filter replacement restores keyboard focus, a
short separate live status announces the result count, headings are structured,
and every milestone disclosure has a unique accessible name.

The received-Mora total is calculated from immutable stored reward receipts,
not from the current reward curve. PostgreSQL proof includes replay, altered
source conflict, append-only rewards and a historical receipt whose amount
differs from current policy. Live checks at 320/390/430 px show zero horizontal
overflow, one visible Back, 44 px actions, readable partial progress and working
milestone disclosure. Independent read-only review returned ACCEPT after all
P1/P2 findings were corrected. Full isolated preprod gate: **97/97**.

## CONTENT-001 — mixed chest, paid key and pet loop (2026-09-13)

The fail-closed `content_chests_v1` surface now serves one immutable mixed
catalogue to free and paid keys. It contains 12 stable species across five
rarities, five food tiers, pet-card packs, Mora, Diamonds, Jokers, Zarniki and
a three-ID VIP cosmetic pool with a documented four-day VIP fallback. The
catalogue digest pins every weight, range, amount, species and VIP cosmetic ID.
A paid key costs **10 Zarniki**, at most two per UTC day; the million-open seeded
simulation gives conservative EV 9.52 and confirms cashback does not fund an
unbounded loop. Free and paid keys use exactly the same outcome function.

Purchase, entitlement allocation, sealed prepare, typed delivery and reveal are
transactional and idempotent. Unused paid entitlements have an internal atomic
refund writer; the purchase sheet states the exact price, remaining quota,
equal odds and support refund path before debit. The public odds panel exposes
the 1–10★ distribution, conditional reward percentages, amounts/ranges,
rarity tables, complete species/VIP pools and fallback. Existing canonical pet
ownership is reconciled so a card pack cannot create a second pet or consume a
new unlock card. Legacy cosmetic-chest endpoints remain 410.

Daily and weekly quest completion each grants one free key. A chest quest is
eligible only when the player already owns a key, and random `pet_card_found`
goals were removed from mandatory sets. Completed pet treks/expeditions grant
one typed key only while the chest flag and delivery schema are ready. Starting
an activity atomically spends 25/40/55 endurance for 3/6/9 hours; replay cannot
double-debit, an exhausted pet cannot start, and disabling chests preserves the
completed run for later settlement instead of minting value.

Live isolated preprod at 320/390/430 px covered purchase confirmation/cancel,
full 10★ disclosure, sealed prepare/reveal, durable reward rendering, quest
completion and a visible 38→13 endurance debit. The current full gate passed
**97/97**. Duplicate and
max-level compensation is deliberately untouched and remains the owner's last
economy stage immediately before production.

## PROFILE-001 — публичный профиль, пять ресурсов и полный preprod-гардероб (2026-09-08)

Личный профиль, публичный профиль и примерочная используют один renderer
`renderProfileShowcase`. У карточки один аватарный/identity anchor; имя, титул,
фон и эффект карточки применяют реальные CSS-токены выбранного образа. Рамка
и ореол одновременно применяются к identity anchor, сохраняя раздельные
визуальные слои. Высота общего stage
уменьшена до 220 px, а примерочная показывает одну карточку с переключателем
между фактическим публичным видом и сохранённым образом вместо двух тяжёлых
копий подряд.

Профиль показывает все пять ресурсов: Mora, Diamonds, Zarniki, Dark Mora и
Echo Shards. Для Echo Shards добавлено только read-only чтение баланса; новый
writer, обмен или магазин не открывались. Публичный DTO адресуется случайным
`profile_ref`, отдаёт display name и разрешённые игровые данные, но не Telegram,
database, clan или moderation identifiers. Rhythm и Minesweeper используют
этот projection для кликабельных имён в таблицах лидеров.

Loopback-only preprod persona при входе идемпотентно получает весь текущий
каталог. Реальная PostgreSQL-проверка подтвердила **134/134** записей владения и
сохранённый образ из шести слотов. Платная косметика видна в личной и
публичной проекции без дополнительного VIP-барьера; гейт остаётся только у
непродаваемых сервисных прав. В публичном ответе также проверены пять балансов и отсутствие raw
ID. Профильные игровые итоги теперь берутся только из текущих Rhythm,
Minesweeper и Mafia: публичный Rhythm учитывает лишь `finished+clear`, а пять
видов непроверенных завершённых забегов видны только владельцу как
неранжируемые. Публичная карточка не раскрывает Telegram username партнёра,
moderator note, приватную причину санкции или технические ID. Rolling-deploy
guard создаёт projection-таблицы и при старте, и перед первым profile read.
Python/JS syntax, PostgreSQL projection, cosmetic-lineage, static-delivery и
public-route проверки проходят. Остаток профильной волны — художественная
ревизия каждого из 134 предметов.

## COS-002 — mobile-first витрина и whole-app skins (2026-09-09)

Отдельный от retired `themes` контракт хранит durable ownership и saved
selection. Предоставленный владельцем фон сжат в production WebP и добавлен как
`void_atlas` / «Атлас Бездны» за 1600✨ в коллекцию `void`. Покупка сразу
выдаёт и выбирает фон; покупка всей коллекции включает его в ту же
транзакцию. Все платные cosmetics нормализуются как независимые от VIP права.

Один общий клиентский applicator читает активный `css_class` из server DTO и
применяет ограниченный `skin-*` класс в оболочке, Rune Rhythm и Minesweeper.
Один общий CSS меняет фон, токены, панели, контролы и клетки без изменения
layout, доступа, цен, gameplay или motion. Доставляемая примерочная больше не
рендерит и не вызывает legacy `/themes/*`. Финализация аккаунта удаляет и
ownership, и selection; одновременно исправлено старое имя столбца nickname.

Независимая read-only ревизия сначала отклонила три расходящихся ручных темы;
её оба P1 устранены. Следующая независимая проверка 134-item renderer нашла
ещё два P1: ореол терялся при выбранной рамке, а пять псевдоэлементов
продолжали анимацию при `no-fx`/`prefers-reduced-motion`. Оба дефекта закрыты
общей композицией frame+halo и полным motion fallback. Живой DOM сохранённого
образа подтвердил одновременные `frame-artifact` и `halo-dust`.

Автоматический DOM-аудит всех 134 карточек подтвердил распределение
25/23/19/21/23/23 по шести слотам, отсутствие пропущенных CSS-токенов и
фактического overflow. Новый `test_cosmetic_visual_contract.py` фиксирует
точный каталог, slot-prefix, CSS delivery, общий renderer и reduced-motion.
Полный isolated preprod gate **89/89** зелёный. Видимый
loopback-тест подтвердил Lunar Archive в основной оболочке, Rhythm и
Minesweeper, после чего временный VIP удалён и базовый fallback восстановлен.
Вкладка **Образы** теперь самостоятельная mobile-first витрина: коллекции,
каталог, мои предметы, поиск/фильтры, живая примерка в контексте сета,
покупка одного предмета или всего недостающего. При нехватке Зарников открывается
существующий server-backed Stars flow; preprod честно показывает fail-closed состояние.
Примерка и пополнение имеют dialog/focus/Escape/Back semantics, а 320/390/430 checks не нашли
horizontal overflow. Точный финальный isolated preprod gate: **89/89**.

## UI-002 — подпись профиля отделена от ресурсов (2026-09-09)

Скриншот владельца воспроизведён на текущем loopback UI. Причина была не в
тексте или панели ресурсов: общий stage уже имел высоту 220 px, но прежний
`min-height: 270px` у прямого `.character-showcase-area` продолжал растягивать
дочерний слой. Абсолютно позиционированная подпись следовала за нижней границей
этого 270 px слоя и на 39 px заходила на следующую строку ресурсов.

Прямые visual/data children теперь получают `height: 100%` и `min-height: 0`
от общего stage. Подпись осталась внутри карточки и не была скрыта или уменьшена.
Живые измерения на 320/390/430 px одинаковы: stage и character area по 220 px,
пересечение подписи с resource rail — 0 px, зазор — 11 px, горизонтальное
переполнение — 0 px; пять ресурсных ячеек видимы. Более позднее правило
store-preview сохраняет отдельную компактную высоту 168 px. Static-delivery
регрессия фиксирует цельный selector-блок. Независимая read-only ревизия дала
вердикт Accepted без обязательных изменений; её необязательное замечание о
точности CSS assertion также закрыто. Полный isolated preprod gate — **89/89**.

## QUEST-002 — varied mobile-first журнал квестов (2026-09-10)

Случайная выдача нескольких порогов одного `metric` устранена. Текущий пул
содержит разные server-terminal цели: любую завершённую игру, завершение и
конкретный режим Rhythm, подтверждённые 500 очков, завершение и победу в
Minesweeper, победу на конкретной сложности, завершение Mafia и победу своей
стороны. Assignment выбирает уникальные `lane`/`metric` и round-robin
распределяет доступные игровые источники; reroll исключает занятые смысл и
метрику. Источники сверяются с live system flags, а Mafia входит в пул только
после реального участия игрока. Старые zero-progress наборы обновляются через
двухфазную collision-safe миграцию; начатые наборы не переписываются.

Экран оставляет только **Сегодня / Неделя / Награды** без повторяющихся верхних
счётчиков. Первая цель появляется сразу под компактным блоком `0/4 → 20 Моры`;
недельный блок аналогично показывает `0/5 → 100`, а rewards раскрывает
`20 + 100 + 75` и ведёт к незавершённому разделу. Добавлены настоящие headings,
уникальные accessible names progressbar, 44 px верхний Back, видимый reroll,
retry/error и focus return из dialog. Дублирующий floating Back на questlog
скрыт. Фоновый арт отсутствует: фон остаётся только платной косметикой.

PostgreSQL proofs различают loss/win/difficulty, Rhythm mode/score, Mafia
participant/winner, replay и zero-progress migration. Видимый isolated-preprod
проход подтвердил сбалансированные 4 daily и 5 weekly целей, rewards и dialog.
Финальный полный isolated-preprod gate прошёл **90/90**. Независимый критик
нашёл hard-win rollback, неявный reroll contract и риск частичной миграции;
после исправлений и отдельных PG proofs повторно проверил terminal augments
receipt и дал **Accepted** без оставшихся блокеров.

## TEST-URL-001 — восстановлен Telegram test Mini App (2026-09-07)

Устаревший Quick Tunnel из `.env.test` больше не резолвился. Предусмотренный
туннельный скрипт получил новый URL, но его ранняя проверка не дождалась
публикации edge и, корректно, не поменяла меню. После отдельного внешнего
HTTP-200 подтверждения тестовый URL был обновлён в `.env.test`, test bot menu
через Telegram API и перезапущенный `tools/run_preprod.ps1` получили одно
значение. Логи подтверждают кнопку меню, ready-state и loopback auth; внешний
`/predvestnik/` вернул 200. Текущий URL намеренно не записывается здесь: это
временный Quick Tunnel и он пропадёт при остановке его процесса. Для реального
продакшена всё ещё нужен именованный туннель/стабильный HTTPS-домен и отдельный
deployment gate.

## GAME-001 — Rhythm integrity quarantine (2026-09-07, historical boundary)

This section records the fail-closed state introduced on 2026-09-07. It is
superseded operationally by the 2026-09-14 server-transport/reviewer section
above; the offline quarantine itself remains valid for legacy/offline callers.

Независимая read-only ревизия нашла P0 в Rune Rhythm: Mini App использует
локальный пакет из 2048 будущих рун, а сервер мог только воспроизвести
переданные клиентом `elapsed_ms`. Модифицированный клиент поэтому мог набрать
высокий счёт с нулевыми задержками, попасть в глобальную таблицу и записать
терминальные метрики квестов/достижений, из которых игрок затем получает Мору.
Бывшее описание «без наград и прогресса» было неверным.

Теперь выдача offline packet необратимо помечает забег `offline_exposed`.
Его результат сохраняется игроку, но при финализации становится
`quarantined`: системный gate не разрешает ни leaderboard, ни quest metric,
ни achievement receipt. Даже прямой вызов служебного writer не может вставить
в leaderboard результат, пока строка забега не имеет server-approved
`integrity_status='clear'`; старые записи получили `legacy_unverified` и также
не ранжируются. В выдаче таблицы больше нет сырого `user_id`. Попытка после
получения offline packet переключиться на trusted transport отклоняется.

Для будущей ручной проверки добавлена append-only таблица integrity review, но
нет публичной или админской кнопки «доверить результат» — это сознательно
отложено до отдельной админ-волны. Точечный PostgreSQL negative test подделывает
положительный идеальный offline журнал и подтверждает quarantine с нулём
leaderboard/quest/achievement receipts. JS/Python/ASGI проверки и полный
isolated preprod прогон после изменения: **86/86 passed**. Live transport
остался единственным техническим кандидатом на trusted result, но текущий
клиент пока его не использует; поэтому публичный рейтинг честно следует
считать временно пустым/тестовым, а не «античитом готов».

## COS-001 — единый профиль и безопасная примерочная (2026-09-07)

Профиль игрока и примерочная теперь используют один и тот же рендерер
`renderProfileShowcase`: аватар, рамка, ореол, фон, эффект карточки, титул,
уровень и ресурсные панели имеют одинаковую структуру. В примерочной честно
показаны два состояния: фактический публичный профиль и сохранённый личный
образ. При неактивном VIP первый остаётся нейтральным, второй виден только
владельцу в примерочной; владение и выбранные предметы не удаляются.

Независимая read-only ревизия до завершения обнаружила две P1-проблемы:
предпросмотр мог отстать от только что надетого предмета, а новые классы
гардероба не имели CSS. Обе закрыты: после операции заново читаются профиль и
инвентарь, UI блокирует параллельную операцию, а inline-обработчики предметов
заменены на делегированные data-атрибуты. Проверка каталога подтвердила 134
предмета, шесть слотов, 10 линеек, ноль отсутствующих или повторяющихся
CSS-классов. В видимом loopback Mini App `@codex_test` проверены переход в
примерочную, публичное скрытие образа без VIP и сохранение/переодевание
личного набора. Точечные JS/ASGI/cosmetic-lineage проверки и полный isolated
preprod прогон после финальной правки: **86/86 passed**.

Это закрывает структурное требование «примерочная 1:1 с профилем», но не
является обещанием, что каждый арт-предмет уже прошёл художественную ручную
оценку на всех устройствах. Следующая косметическая работа — визуальная
ревизия линеек и точечное улучшение самих эффектов. Каталог уже содержит 10
линеек, но серверные готовые образы пока определены только для трёх из них;
добавлять остальные следует вместе с отдельной витриной, а не тайно открывать
магазин в примерочной. Выпуск в настоящий
Telegram требует отдельного стабильного публичного домена и deployment gate.

## ACH-001 — durable long-horizon achievements (2026-09-07)

The approved 1–40 achievements are now a separate, server-authoritative v1
contract.  The three initial families are **Пульс** (completed Rune Rhythm
runs), **Контур** (completed Minesweeper runs), and **Свидетель** (completed
Mafia matches).  They accept only immutable terminal game identities — never
page views, messages, client scores, quest rows, historic counters or imported
progress.  A level requires both terminal completions and distinct UTC active
weeks; level 40 requires 156 active weeks (three years) and the approved family
event cap.  Every reached level receives only automatic Mora: 515 over one
complete family path, with no cosmetic, Stars, Zarniki, Echo Shard, random-drop,
reroll or paid advantage reward.

Each terminal receipt, week-presence receipt and reward receipt is durable and
append-only.  Replaying the same terminal event returns the original result;
reusing its identity with changed server facts fails.  The reward receipt and
the canonical `achievement-v1:<family>:<level>` economy-ledger operation share
one locked transaction.  The read-only `/achievements-v1/me` route and Mini App
screen expose exact current and next requirements.  The visible loopback
`@codex_test` Mini App has been opened on this screen, showing all three level
0/40 paths.  It intentionally begins fresh: no historic migration/backfill was
performed.

Proof: pure policy test, real PostgreSQL receipt/replay/conflict/append-only
test, existing Rhythm/Minesweeper/Mafia PostgreSQL terminal paths, JavaScript
and Python syntax checks all pass.  The full isolated preprod runner completed
**86/86 passed** after this change.  The preprod bot was restarted through
`tools/run_preprod.ps1`; both loopback ports listen and logs contain
`🟢 БОТ ГОТОВ К ПРИЕМУ СООБЩЕНИЙ`.  Next safe product slice remains the
owner-requested item-by-item cosmetic visual audit; do not add achievement
families until another activity has a verified terminal writer and a clear
non-grindy player description.

## Local browser-test auth repair (2026-09-06)

## ECON-002 — compensation currency naming boundary (2026-09-06)

The owner named the future universal duplicate/max-level compensation currency
**Осколки Эха** (`echo_shards`, intended icon `◈`).  The pure economy policy
now records it as `planned_compensation`, deliberately outside the live
four-currency ledger.  This prevents an accidental Stars purchase, exchange,
or unpriced balance writer before each real duplicate source and compensation
rate has a server-authoritative contract.  Future shop goods are explicitly
not yet implemented; no player balance was created or changed by this naming
slice.

ECON-002 foundation (2026-09-07): an independent read-only economy audit
rejected adding a fifth generic wallet currency.  The new internal
`echo_shard_*_v1` account, immutable compensation receipt and append-only
ledger are instead isolated from Stars, payments, exchanges, shops, transfers,
HTTP and chat.  A source must present an allowlisted terminal duplicate-event
identity and prove `observed_level == observed_cap`; the same source line
replays its original receipt, while changed facts hard-conflict.  No approved
pet-v1/cosmetic-v1 duplicate source exists yet, so this foundation intentionally
does not mint any player value.  Real PostgreSQL proof covers first award,
replay, altered-fact conflict, non-max rejection and ledger rewrite denial.
The restarted preprod bot created all three tables and the visible loopback
Mini App still signs in as `@codex_test`.

ECON-002 duplicate-writer hardening (2026-09-07): the internal Echo receipt
now fingerprints canonical JSON source facts, rejects numeric coercion (for
example `1.9` can never become a reward), and fixes every supported terminal
source at exactly one shard.  The new internal pet duplicate writer creates an
append-only `pet_v1_duplicate_progressions` receipt in the same transaction as
the pet level transition and the level-16 Echo compensation.  It deterministically
applies levels 1→16, then only records `max_compensated` with one shard; exact
replay returns the old receipt, while a reused source id for another pet fails.
The progression receipt has its own database append-only trigger, so neither a
terminal result nor its shard flag can be edited or deleted afterwards.
Independent follow-up review found and closed four P1 edges: the Echo receipt
now has its own append-only trigger; source uniqueness is per user end-to-end;
unapproved cosmetic compensation was removed from the supported policy; and
the pet writer now fail-closes unless an append-only `pet_v1_duplicate_sources`
terminal `chest_v1` receipt already exists for that user/pet/event.  No service,
route or chat command creates that source receipt yet, so this is a deliberate
safe boundary for the future verified chest writer rather than a player-facing
mint path.  PostgreSQL negative proofs cover every receipt rewrite gate and a
missing terminal source.

Regression gate after the independent-review repairs (2026-09-07):
`tools/run_preprod_tests.ps1` completed with **84/84 passed**.  The restarted
isolated preprod bot again reached both local loopback ports and `🟢 БОТ ГОТОВ`;
the external released-surface smoke and configured menu-URL check passed.  This
proves the current isolated/preprod scope only, not a production deployment or
a completed chest economy.

Production-address audit (2026-09-07): the stable-looking DigitalOcean URL
`https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik/` responds, but its
visible application is a stale legacy client (Inventory, Themes, old Quests,
Achievements, Arena and Shop), not this approved release surface.  It must not
be placed on the current bot menu.  The live test bot therefore correctly stays
on the externally verified Quick Tunnel, which remains volatile by Cloudflare
design.  Publishing this local revision to the stable app/domain requires
deployment/domain authority that is not present in the workspace; GitHub push
is explicitly forbidden by the owner.
There is deliberately no HTTP route, bot command, shop, transfer, Stars
purchase, exchange, public balance or client-supplied award.  A future verified
loot/chest writer is the only permitted caller.  Real PostgreSQL proofs cover
all fifteen level-ups, the level-16 compensation, replay, source conflict and
one-ledger-row result; the standalone Echo proof covers altered snapshots,
float rejection, cap enforcement and ledger immutability.  Preprod was restarted
after the schema change; visible `@codex_test` pets and external Mini App smoke
both remain green.

Full-suite note (2026-09-07): the complete isolated
`tools/run_preprod_tests.ps1` runner exited `0`: **84/84 passed**, including
the new Echo Shards PostgreSQL proof.  This is an isolated-preprod regression
fact, not a production-domain or production-data release claim.

Preprod URL repair (2026-09-07): the previously advertised Cloudflare Quick
Tunnel had expired DNS, so its menu-button link was genuinely unreachable.  A
fresh Quick Tunnel was externally confirmed with HTTP 200 before `.env.test`
was switched and the exact preprod bot process restarted.  Bot logs confirm
`Кнопка меню → https://jennifer-texts-morrison-clara.trycloudflare.com/predvestnik`;
`verify_preprod_menu_url.py` and `verify_preprod_smoke.py` both pass against
that external URL.  `tools/run_preprod_tunnel.ps1` had a Windows-codepage parse
failure in its menu text; it now uses the ASCII label `Play`.  The URL remains
volatile by design: this proves live preprod delivery, not production continuity.

Release-boundary proof (2026-09-06): `tools/test_release_public_routes.py` and
`tools/test_static_delivery_asgi.py` pass against the current source.  Retired
public routes do not reopen the old Mini App surface, while the approved static
shell remains available under its `/predvestnik` mount.

External smoke (2026-09-06): `tools/verify_preprod_smoke.py` passed through
the live configured Quick Tunnel.  It verifies the released HTTPS Mini App,
authenticated current profile/hub/appearance/pets/quests readers, and the
retired-route boundary.  This is a live-preprod fact only; the volatile Quick
Tunnel is not a production-domain continuity guarantee.

Visible browser proof: the same authenticated loopback persona opened
`/?startapp=quests` and rendered the active Quest Log, four daily and five
weekly cards, the standard 2/2 rerolls and all three claim-state cards.  This
also exposed a content limitation, not a navigation/auth bug: there are only
two daily terminal metrics (`rhythm_completed`, `minesweeper_completed`) for
four required cards, so duplicate game categories are unavoidable.  Do not
pretend shuffled target counts are variety.  Real variety needs new,
authoritative terminal writers for approved activities such as pet care/chests;
they are intentionally not invented before their reward and anti-abuse rules.

`http://127.0.0.1:8404/__preprod/login` now creates the minimal isolated
`@codex_test` user row and hands off a separate 120-second, purpose-bound ticket
to the Mini App origin.  The 8403 activation route sets the normal HttpOnly
local test cookie; if an automation WebView partitions cookies across the
8404→8403 redirect, the client keeps that short ticket only in session storage,
removes it from the address bar, and sends it only as a preprod test header.
Neither path accepts a real Telegram identity, and both are 404/disabled outside
isolated preprod.  `FastAPI/deps.py` gives genuine Telegram initData precedence
over either test mechanism and rejects forged tickets.

Verified after a `tools/run_preprod.ps1` restart: both loopback ports listen
from the same preprod bot process; direct cookie and partitioned-WebView header
proofs resolve the profile to `@codex_test` / `990000001`, while a stale normal
session cannot replace it and forged activation/header tickets fail (404/401).
The visible Codex in-app browser then loaded that real profile successfully.
The profile renderer was also hardened so a failing optional widget can no
longer overwrite an already loaded profile with the false registration message.

## PET-002 route terminal-state repair (2026-09-06)

Confirmed a real shared-timer softlock: a selected expedition route stayed
`ready`, and the partial unique active/ready index then rejected every later
trek or expedition.  The route writer now atomically records the chosen route
and changes the run to `claimed`; it creates no inventory, currency, loot or
other reward.  The action receipt still makes a retry return the same result,
while a changed second route is rejected.  The Mini App and chat now say plainly
that this currently completes without a reward.  PostgreSQL proof covers the
previous counterexample by starting a new trek immediately after the route;
rules, PG and bot parser/render tests pass.  Preprod was restarted after this
change.  A real outcome/reward contract remains unimplemented until its rules
are specified; level-only future effects are not represented as value here.

PET-003 timer-only trek repair (2026-09-07): a due `trek` previously moved to
`ready`, even though the approved timer-only trek has no follow-up choice.
That left the one-active/ready uniqueness guard blocking every later activity.
Due treks now become `claimed` automatically while due expeditions alone become
`ready` for a route decision.  Real PostgreSQL proof expires a trek, confirms
the overview has no active activity, then starts a new expedition immediately.
The preprod bot was restarted and external released-surface smoke stayed green;
the complete isolated regression run after this repair is **84/84 passed**.

Visible pet UI proof (2026-09-07): a preprod-only `Тестовый Лис` was added to
the existing synthetic `@codex_test` account.  The visible loopback Mini App
loaded `?startapp=pets` and rendered the real level 1/16, 100/100 endurance,
initial visual stage, route bonus and active-slot control.  This is test data
only and does not create a production pet, reward, payment or Echo Shard.
The same visible Mini App path selected that pet as active, started a 3-hour
trek, displayed the running timer, then (after only that preprod test run was
expired server-side) showed all six 3/6/9-hour activity controls again.  This
is end-to-end evidence that the timer-only slot is released through the actual
UI reader, not merely by an isolated repository assertion.

Visible expedition UI proof (2026-09-07): that same preprod test account
started a 3-hour expedition, its server time was advanced only in preprod, and
the Mini App rendered exactly the three approved routes (careful, steady,
bold).  Choosing `bold` produced the explicit no-reward completion toast and
returned the six activity controls.  This proves the UI → API → durable choice
→ shared-slot release path.  It does not claim a reward/outcome economy: the
approved reward contract remains deliberately absent.

Updated: 2026-09-05

## Active goal

2026-09-05 release work: the old cosmetic screen still called unregistered
`/cosmetics/*` endpoints. A new owner-only `/appearance` route and fitting-room
screen now use durable inventory/loadout only; no checkout or direct-Stars
writer was restored. Public profile projections hide every cosmetic while VIP
is inactive, while the owner retains a private saved-look preview. Narrow
projection tests, Python/JS compilation and isolated preprod browser smoke as
`@codex_test` pass. The next safe release slice is a read-only audit of the
remaining approved mechanics (pets/expeditions/quests) before introducing any
economic or progression writer.

PET-001 (2026-09-05): a fresh pure `core/pets_v1.py` replaces the incompatible
legacy rule basis. It enforces the owner-approved 1–16 levels, 0–100 endurance,
ten points/day drain, anti-abuse active-slot cost, and only 3/6/9-hour future
durations. `tools/test_pets_v1_rules.py` passes. It is not publicly wired: the
next step is an idempotent PostgreSQL state/action layer before an API or bot
writer is exposed.

PET-001 continuation: the PostgreSQL state/action layer and authenticated
`POST /pets-v1/active` adapter are now present. Real isolated PostgreSQL proof
in `tools/test_pets_v1_pg.py` verifies ownership isolation, exact 5-endurance
active-slot debit, idempotent replay and conflicting action-id rejection.
The Mini App read-only pet screen and active-slot control are now wired. It
does not yet implement care/food, bot presentation, expeditions or any reward.

QUEST-001 (2026-09-05): the retired quest module remains unregistered. A fresh
`quest_v1_*` PostgreSQL contract now assigns exactly four daily and five weekly
clear objectives, keeps definition snapshots and metric/action receipts, and
enforces two weekly rerolls (five only when VIP is server-confirmed). The new
`/quests-v1` Mini App screen is independently named `questlog`, so it does not
bypass the deliberate redirect of the historical `/quests` surface. Real
PostgreSQL proof verifies replacement, replay, action-key conflict, limit,
one-time terminal metric receipt and the daily+weekly combined guard. Rhythm
and Minesweeper terminal server paths now record those metrics by immutable
run id, including retry and timeout paths; their existing PostgreSQL proofs
assert the receipt exists exactly once. Mafia completion now grants one receipt
per participant by immutable match id; its PostgreSQL proof checks all four
seats and a scheduler retry. Pet-care and chests are
not in the active rotation until their corresponding authoritative terminal
writers exist; the migration replaces only zero-progress pre-reward rows.

QUEST-001 continuation: chat now has a read-only `бот квесты` / `бот задания`
renderer backed by the same `quests_v1.overview` service as the Mini App. Its
button opens `startapp=quests`, and the Mini App start-parameter handler now
opens `questlog` rather than the retired `quests` page. The chat path never
rerolls, grants a reward or records activity; rerolls remain authenticated,
idempotent Mini App actions. Renderer escaping, route registration, the real
PostgreSQL quest contract and a live loopback `startapp=quests` browser smoke
are verified.

QUEST-001 rewards (2026-09-06): completed milestones now have only explicit
free Mora rewards: 20 for all four daily tasks, 100 for all five weekly tasks,
and 75 for completing both. No Stars, Zarniki, cosmetics or random item is
created. The durable receipt identity is `daily:<UTC day>`, `weekly:<UTC
week>`, or `combined:<UTC week>`: the combined reward is intentionally weekly,
so finishing daily tasks on later days cannot re-credit a completed weekly
set. Receipt reservation and the append-only `quest_reward` ledger credit share
one transaction and one user lock. The Mini App exposes only claimable rewards.
Real PostgreSQL proof confirms 195 Mora for all three, exact replay safety and
three ledger operations; route/static/economy checks are green. An independent
critic was requested but its agent hit the product usage limit before producing
a review, so no external-review claim is made.

PET-001 continuation: chat now has a read-only `бот питомцы` / `бот питомец`
renderer and a `startapp=pets` link to the same Mini App view. It projects only
the caller's saved level/endurance/active state; chat never selects a pet or
awards value. `бот поход, 3|6|9` and `бот экспедиция, 3|6|9` now call the same
server-authoritative shared timer writer as the Mini App. The Mini App
start-parameter path and empty collection state are confirmed in the loopback
browser. Care/food and duplicate compensation remain intentionally unimplemented.

PET-002 (2026-09-05): the new pet layer now has one server-authoritative
shared timer for a timer-only trek or an expedition. Only the approved 3/6/9h
durations are accepted; starting requires an owned active pet, records an
idempotent action, and the partial unique index prevents a second active/ready
run even under concurrency. Timer completion changes only to `ready`: no loot,
currency or interactive expedition result is granted until those contracts are
implemented. A ready expedition now accepts exactly one durable, idempotent
route choice (`careful`, `steady` or `bold`) through the Mini App; it still
cannot award value or resolve an outcome. PostgreSQL proof covers no-active
rejection, replay, cross-kind double-start rejection and one-choice-only.
Chat has the same choice through `бот маршрут, осторожный|ровный|рискованный`;
its parser is strict and only invokes that existing authoritative writer.

Verification after the route-choice slice: the restarted isolated preprod bot
served the updated Mini App; the loopback browser loaded `startapp=pets` with
no console errors. The synthetic browser account has no pet, so visibility of
the route buttons is covered by real PostgreSQL state rather than a fabricated
client state. `tools/run_preprod_tests.ps1` completed `80/80` tests green.

ECON-001 (2026-09-05): owner-approved Zarniki conversion is now a separate
server-only policy, not a revival of the retired 150-Mora quote. It permits
only whole already-held `✨ → 🪙` (1:10) or `✨ → 💎` (1:0.01), with one shared
50-Zarniki UTC daily cap. A 200-Star package (2,200 Zarniki) therefore needs
at least 44 UTC days to be fully converted. The Mini App and chat both call
the same `services/zarniki_exchange_v1.py`; it locks the user, validates
idempotent replay before the quota, rejects an open Stars refund/review state,
writes both ledger legs atomically and then increments the quota. Pure and
real PostgreSQL proof cover input boundaries, replay, altered-key conflict,
split-target cap bypass, insufficient balance and review freeze. The current
full isolated preprod suite is `83/83` green.

PREPROD-URL-001 (2026-09-06): the prior Quick Tunnel expired in DNS, so it was
replaced with the live HTTPS endpoint configured in `.env.test`:
`https://foundations-profits-rebates-nut.trycloudflare.com/predvestnik`.
The restarted test bot log confirms `set_chat_menu_button` targeted this exact
URL. `tools/verify_preprod_menu_url.py`, external HTTP 200 and a visible
in-app-browser load all pass. It remains a Cloudflare Quick Tunnel and lives
only while its local tunnel process runs; a named tunnel/custom domain or
deployment requires an owner-approved hosting decision before a production
claim.

PREPROD-URL-001 continuation: `tools/verify_preprod_smoke.py` now exercises
the actual external authenticated release surface: health, profile, hub,
appearance, pets and quests must be 200; retired Reconstruction/VIP/game/streak
routes must be 404. It passed against the live Quick Tunnel. The attempted
automatic replacement helper is fail-closed: two fresh Cloudflare hosts did not
finish DNS propagation inside the one-minute probe window, so it did not alter
the working bot menu or `.env.test`. A named tunnel/custom domain remains the
only production-grade answer to address continuity.

Довести новый retention/content слой и честную cosmetic monetization до
проверенного preprod результата без локального mock-сервера.

Параллельная одобренная волна: новый гибридный центр игрока. Первый шаг уже
реализован как read-only `GET /hub/me`: единый уровень, семья, питомец, один
клан и последние операции без экономических writers. Внешний preprod smoke
пройден через новый quick tunnel. Следующий безопасный шаг — migration audit
на уникальность брака и отдельный append-only семейный журнал до разморозки
семейного кошелька.

2026-08-30: read-only audit уникальности брака добавлен в
`infrastructure/repositories/marriage_integrity.py`; его negative test и
проверка на isolated preprod зелёные. Автоматическое исправление исторических
дубликатов намеренно запрещено.

Продолжение 2026-08-30: добавлены loopback-only preflight и
operator-controlled migration `marriage_members` (один `user_id` на весь
брак). В isolated preprod migration применена; реальный rollback-test доказал
backfill, успешное создание и отказ второго брака для того же пользователя.
Бот и HTTP accept теперь fail-closed требуют этот реестр. Family bank остаётся
409/frozen: независимый critic выявил forged marriage id, no-idempotency,
FLOAT8, legacy scheduler writer, account-deletion и gift-after-remarriage
риски. До family ledger нужен owner выбор по transfer/chargeback-политике
Зарников и отдельный production read-only audit + backup approval.

Owner decision 2026-08-30: семейный кошелёк должен поддерживать все валюты,
включая Зарники. Реализованы и проверены только backend custody tables и
двухногий transfer service на isolated PostgreSQL: personal ledger + family
ledger + balance projections откатываются вместе; retry/foreign member/
fractional Zarniki/insufficient balance протестированы. Public HTTP/Telegram
writers остаются frozen до реализации refund/chargeback lineage: нельзя
выпускать перевод платной валюты раньше, чем возврат сможет снять только
вклад покупателя, а не баланс супруга.

Продолжение 2026-08-30: найден и закрыт lifecycle-риск развода. Запись
`marriages` больше не удаляется: `ended_at` сохраняет историю, а активные
строки `marriage_members` освобождаются только после нулевого семейного
баланса и отсутствия семейных питомцев. Поэтому новую семью можно создать
после развода, но нельзя уничтожить журнал прежней семьи. Migration применена
только на isolated preprod; rollback-test проверил отказ развода с имуществом,
сохранение history, освобождение membership и повторный законный брак.
Следующий незакрытый риск — payer-specific Stars custody/refund lineage для
Зарников; public writers всё ещё frozen.

Новый безопасный шаг 2026-08-30: authoritative negative Stars history теперь
сначала сопоставляется с immutable receipt Зарников. При точном совпадении
плательщика и суммы receipt переводится в `review`, а не ошибочно в
`refunded`; автоматического списания личного или семейного баланса нет. Real
PostgreSQL rollback-test доказал: неверная сумма не меняет receipt, верный
сигнал ставит review ровно один раз, повтор — no-op, 200 Зарников остаются
нетронуты. Это лишь предохранитель, не refund rail: следующий шаг — лоты
происхождения каждой единицы после перемещения в семью.

Независимый financial critic (2026-08-30) подтвердил следующий дизайн:
immutable origin lot на каждую Stars receipt, append-only lot ledger и
lockable projection availability. Один и тот же origin обязан переживать
personal→family→spouse personal; legacy/unattributed остатки никогда не
выдаются за refundable Stars. Критические negative cases: два вывода из
одного лота, retry после частичного распределения, refund-vs-withdrawal и
laundering в Мору/Алмазы. До их покрытия ни публичный transfer, ни automatic
refund не допускаются.

Owner policy decision 2026-08-30: Telegram-compliant manual-dispute policy,
not a user-facing return feature. `/paysupport` is mandatory; owner examines
the immutable charge and delivery record. Zarniki↔Stars conversion and an
automatic refund button are prohibited. A discretionary Stars refund is
normally considered only before the associated Zarniki leave the buyer's
personal balance; after spend/gift/exchange/family deposit, the request is
still answered but no return is promised. Therefore payer-specific lot
recovery is no longer a prerequisite for normal family transfers; it remains
required only if a future product decision permits refunds after transfer.

Продолжение 2026-08-30: public family-wallet adapters are now unfrozen on the
isolated preprod code path only. Mini App sends no marriage id, requires a
fresh idempotency key, and receives a server-resolved four-currency transfer.
Telegram creates a persisted, owner-bound, 10-minute currency-choice intent;
the callback is one-shot and the service locks it through both ledger legs.
Rollback proofs cover a foreign callback, expiry, sequential replay and two
concurrent callback deliveries (exactly one operation). The legacy scheduler
no longer mutates `marriages.family_balance` directly; it credits the old
expedition reward personally until a separately receipted family-reward source
exists. The obsolete legacy bank writer remains fail-closed. Remaining gate:
the updated isolated test bot is running and external authenticated HTTPS smoke
passed at `https://solving-humidity-canvas-greetings.trycloudflare.com/predvestnik`.
The next release gate is a manual end-to-end transfer with a disposable married
test account (Mini App and Telegram command) before treating this as
release-ready; production remains untouched and still needs the owner-approved
read-only migration audit.

BOT-001 implementation wave 2026-08-30: the public bearer path is replaced by
a 10-minute creator-bound request. The same Telegram user must retain live
administrator authority in the source and destination groups; the bot itself
must be an administrator in the destination. The repository consumes the
request with `DELETE ... RETURNING`, writes the one-to-one route and an
append-only bind audit in the same transaction. PostgreSQL enforces one source
per destination. A route cannot be changed while that source has an active
purge session, because its dossiers have already captured the old destination.

Independent BOT-001 critic 2026-08-30 supplied the attack matrix and confirmed
the critical readers: moderation notices, warn court and purge dossiers. The
implemented isolated-PostgreSQL proof rejects foreign owner, replay, expiry,
second source for one destination and rebind during an active purge; two
concurrent deliveries produce exactly one binding. `py_compile`, diff check,
schema startup and external authenticated HTTPS smoke all passed after the
test-bot restart. Residual release gate: manually perform a source→destination
bind with the disposable test bot in two real Telegram groups, including a
negative attempt by a non-owner/admin. Production remains untouched.

BOT-002 audit correction 2026-08-30: this was not reproducible. The registered
middleware receives an aiogram `Update`; a callback update has
`Update.message is None` even though `Update.callback_query.message` contains
the original button message. The activity branch explicitly requires
`event.message`, so it does not update chat counters for a callback. No code
change is justified; the stale backlog row was removed after a constructed
callback-update proof.

BOT-003 implementation 2026-08-30: the critic confirmed the order preprod gate
→ database writer → global-sanction gate. The evaluated sanction decision is
now obtained before automatic writes on the same acquired connection and reused
by the later middleware; failures stop the update. A globally banned appeal or
help command reaches its explicit handler but does not refresh profile/chat
activity. The new contract test, compile, existing preprod-gate test and
external HTTPS smoke passed after restarting the isolated test bot. Residual
race is documented in the release backlog: an update already evaluated before
a separately committed new ban can finish; strict cross-transaction ordering
requires a future shared lock around sanction issuance and activity writes.

BOT-004 implementation 2026-08-30: one shared settings-callback gate now
requires the original owner, a group context, current local rank ≥5 and a live
Telegram creator/manage-chat role for menu, rank-selection and every toggle.
The old Echo-only special check was folded into that gate. The contract test
proves local-rank demotion and lost Telegram authority stop before any writer;
a current moderator passes. Compile, test-bot restart and external HTTPS smoke
passed. Each callback is revalidated immediately before its write; a concurrent
demotion after that point cannot be transactionally locked against Telegram.

Next active investigation: BOT-005. Existing Stars recovery is idempotent and
retries transaction history, but uses stateless offset scans (100 pages at
startup, three pages periodically) and only logs when the safety cap is hit.
It has no durable watermark or operator-visible unresolved state, so a long
outage/history growth can leave an older purchase outside the scan. An
independent finance/reliability critic is reviewing a cursor design before any
payment-schema change.

BOT-005 critic result 2026-08-30: a persisted numeric offset is unsafe because
new Telegram history rows shift later pages and can cause a silent skip. The
safe design is append-only transaction observations keyed by Telegram ID,
durable reconciliation health/lease and unresolved alerts; every pass begins
at offset zero and only a repeated complete stable-head sweep may be called
complete. Observations and the economic/refund mutation must commit together.
Required negative proofs include head insertion, restart, cap/backlog alert,
concurrent delivery, failed write, reordered/refund-before-receipt and lease.

BOT-005 implementation begun 2026-08-30: schema definitions for immutable
observations, reconciliation state/lease and durable alerts were added in
`star_payments_v1`. The observation key is `(telegram_charge_id,event_kind)`,
not charge alone: Telegram intentionally reuses a payment ID for a matching
outgoing refund. The new tables compile but are not yet wired into the worker;
do not treat them as a completed recovery solution. Next: repository lease,
observation/alert functions and restart-from-zero stable-head passes.

## Fresh audit reset (2026-08-29)

- По запросу владельца удалены исторические планы, спецификации, аудиты,
  визуальные evidence-артефакты и старые статические отчёты. Код, миграции,
  тесты и операционные правила сохранены. Новый источник очереди —
  `docs/audits/AUTONOMOUS_RELEASE_BACKLOG.md`.
- Новый read-only аудит бота: `docs/audits/BOT_WEAKNESSES_FRESH_START_2026-08-29.md`.
  BOT-001 реализован и доказан на isolated PostgreSQL; до снятия release-gate
  остаётся ручная проверка двух реальных Telegram-групп тестовым ботом.
- Новый read-only аудит игровой части: `docs/audits/GAMEPLAY_ECONOMY_AUDIT_2026-08-29.md`.
  Главная продуктовая блокировка **GAME-001**: текущие награды намеренно
  shadow-only, поэтому у нового игрока отсутствует замкнутый цикл
  «сыграл → получил → выбрал → потратил». Отдельный технический stop-ship
  **GAME-002**: XP/ветви отображаются, но XP writer не вызван из terminal
  settlement, так что ветви уровня 5 недостижимы. Перед ценами и экономикой
  требуется owner decision: малая честная игровая валюта с одним non-power sink
  либо полностью currency-free сюжетный цикл.
- Новый единый продуктовый черновик: `docs/PROJECT_RECONSTRUCTION_MASTER_PLAN.md`.
  В нём зафиксирован рекомендуемый новый цикл: Ритм → подтверждённый XP/Эхо
  → сюжетный/косметический след → следующая глава; включая уровни Резонанса,
  модификаторы, спутников без таймерной фермы, магазины без pay-to-win и
  поэтапную реализацию. Это design source-of-truth до отдельного owner review;
  код по этому документу пока не менялся.
- Владелец уточнил, что Ритм — только одно из развлечений, не кор-механика.
  В master plan внесена критическая пометка: общая реконструкция ждёт выбора
  настоящего центрального цикла (рекомендованное направление — экспедиции по
  миру). Единственная активная design-волна сейчас — питомцы: карточки,
  отряд из трёх с малыми мировыми дарами/тенями, забота без таймерной фермы,
  короткие экспедиции и только бесплатные игровые сундуки с published odds;
  Stars не продают карточки, ключи, XP, Внимание или попытки.
- Новые owner decisions для питомцев (2026-08-30) заменяют последнюю строку
  выше: уровни 1–16 повышаются дубликатами конкретного питомца и
  Мора/Алмазами/Тёмной Морой либо эквивалентом Зарников; Зарники покупаются
  за Telegram Stars и обмениваются на Мору/Алмазы. Усталость пассивно
  **тратится** на 1 каждые 2 часа и восстанавливается едой из сундуков.
  Поход — таймер 3/6/9 часов с ключом как единственной наградой; Экспедиция
  — отдельная будущая мини-игра, также с одним ключом. Сундук имеет одну
  server-chosen награду и tap-reveal, 10★ = 0,3%; конкретные шансы, диапазоны
  и симуляции намеренно отложены до разработки. В гачу/владение включены
  карты-джокеры по редкостям и клановые запросы до 4 дубликатов.

## Completed

- На isolated preprod включён `game_reconstruction_v1`; реальные authenticated
  `/reconstruction/rhythm`, `/weekly-case`, `/companions` отвечают 200.
- Исправлена передача ISO string в PostgreSQL DATE.
- Реализованы Хроника подвигов, Архив находок, Ритм и безопасный admin opt-in
  чат-ивент «Эхо в чате» без валюты/силы/DM.
- Weekly Case расширен двумя immutable content pack: 8 дел / 24 meaningful days,
  шестнадцать путей, архив финалов, stale-card 409 и глобальный unique day credit.
  Legacy Bell мигрирует без изменения пути/progress/frozen finale.
  Definition digest fail-closed защищает историю; дни после 3/3 без пути больше
  не сгорают, exact cross-surface replay пути даёт no-op.
- Реализована 28-дневная Карта Шрамов: 12 узлов в трёх дорожках, финал при
  любых 9, общий state для Mini App и `бот ритм`, без валюты/силы и без покупки
  прогресса. Premium cosmetic track выключен до готового Stars refund rail.
- Тестовый бот `@predvestnik_v2_bot` и Mini App работают через текущий HTTPS
  tunnel; authenticated preprod smoke без ошибок API.
- 2026-08-28 тестовое меню указывает на
  `https://brakes-passengers-loads-finally.trycloudflare.com/predvestnik`;
  активная preprod exec-session `60811`, tunnel process `2616`.
- Хроника подвигов v2 содержит 13 конечных целей. Подтверждённый подвиг
  материализуется append-only receipt и не регрессирует; Weekly/Scar proofs
  fail-closed проверяют версию, definition digest и terminal state.
- Публичный writer покупки/подарка VIP удалён: HTTP purchase возвращает 410,
  чат показывает только сохранённый срок, Mini App не содержит цены или buy
  action. Legacy paid Battle Pass больше не рекламируется как доступная покупка.
- Owner-less callback compatibility удалена: callback с `user_id <= 0` теперь
  fail-closed; живой AI-help callback всегда встраивает id владельца.
- 2026-08-28 завершена дополнительная legacy-чистка: из Reconstruction JS
  удалены preview transport/fake session/EventSource и локальная карьера;
  HTML-шаблон production-only. Удалены неиспользуемые Telegram-адаптеры кланов,
  инвентаря, уведомлений, магазина, крафта, гачи, реликвий, достижений и
  одиннадцать локальных Puppeteer-аудитов. Удалён одноразовый `/static/icons/x.svg`,
  старый SQLite/Spaces backup, неиспользуемый NSFW-consent repository/DDL и
  сиротские keyboard/lexicon-модули.
- Read-only Red Team одобрил удаление недостижимых onboarding/referral,
  Alchemy replay, currency-streak reward/recovery и Dark Market writer слоёв.
  Удалены также их orphan constants, старый wager UI/CSS и устаревший x.svg
  backlog shim. Исторические данные и settlement/recovery readers сохранены.
- Возврат активной старой minigame-ставки теперь обнаруживается общим service:
  Mini App показывает условную recovery-card, чат — owner-bound кнопку. Refund
  остаётся атомарным и идемпотентным по session id; старые игры не оживлены.
- Реализован «Небосвод Предвестника» v1: 12 неэкономических узлов в трёх
  ветках, бюджет до 7 из immutable Chronicle receipts, взаимоисключающие линзы,
  публичные печати и одно бесплатное Затмение на version-bound Scar cycle.
  Mini App содержит подтверждения и click-lock; чат — summary/deep-link без
  fallback в production-бота. Старый power-концепт явно помечен архивным.
- Stars-инвойсы теперь fail-closed и на production до готовности двух доказанных
  rails: refund и direct cosmetic entitlements. Добавлены `/paysupport`,
  immutable charge receipt для будущих/authoritative reconciled credits,
  честный disabled-state в Mini App/чате и обновлённая refund policy без ложного
  blanket «цифровые товары возврату не подлежат».

## Test policy

- Новые точечные tests не входят в автоматический runner и сами по себе не
  расходуют контекст. Не запускать их пакетом.
- Для текущей волны использовать только затронутый test + `py_compile` /
  `node --check` + один authenticated preprod сценарий.
- Не использовать и не расширять удалённые preview/mock scripts; источник
  истины — test bot/preprod.
- Оставить короткие regression tests, защищающие economy, migration,
  idempotency, cross-chat и Telegram callback size. Не создавать source-string
  tests, если тот же инвариант можно проверить через core/service.

## Verified

- SQL negative proof: второй case не получает credit того же day key.
- Scar Map: реальный PostgreSQL rollback-probe подтвердил apply/no-op/conflict;
  локальный authenticated preprod endpoint отвечает 200 и отдаёт 12 узлов,
  threshold 9, `stars_can_buy_progress=false`.
- Weekly stale `case_id` → 409; v1/v2 migrated state equal; rollback-probe
  подтвердил capped-day preservation, cross-surface replay, конфликт и 4/4→5/8.
- Chat Echo: snapshot/cross-chat/exact replay/exactly-once completion.
- `game_reconstruction_v1=1`; chat Echo default opt-in = 0.
- Внешний authenticated preprod: Rhythm 200, Weekly Case 200/catalog 8,
  VIP status 200/purchase_retired, VIP purchase 410, Stars invoice 403.
- Точечные `py_compile`, `node --check` и `git diff --check` после retirement
  VIP/callback compatibility прошли.
- После legacy-чистки повторно зелёные `node --check`, `compileall`,
  `test_static_delivery_asgi`, `test_old_combat_retirement`,
  `test_passive_progression_retirement`, `test_economy_ledger` и внешний
  `verify_preprod_smoke.py`.
- Новый Cloudflare tunnel успешно зарегистрирован, внешний authenticated smoke
  снова зелёный, включая Scar Map. Управляемый in-app browser блокирует и HTTPS,
  и loopback с `ERR_BLOCKED_BY_CLIENT`; не выдавать это за дефект Mini App и не
  оставлять пользователю вкладку с чёрным/ошибочным экраном.
- Хроника v2: policy test, reconstruction service test, `node --check`, real
  PostgreSQL rollback-probe и внешний authenticated smoke (`feats=13`) зелёные.
  Quarantined/practice/lost run больше не продвигает mastery, onboarding или
  durable campaign progress.
- Legacy wave: `test_legacy_skill_games_retirement`, scheduler settlement,
  economy ledger, onboarding/passive retirement, `compileall`, JS check,
  ASGI static gate и внешний authenticated smoke (`games2`, streak archive,
  Dark Mora archive) зелёные.
- Sky v1: policy/event tests, `py_compile`, `node --check`, PostgreSQL rollback
  proof (allocation, fresh replay, fingerprint conflict, stale revision) и
  authenticated loopback endpoint 200/12 nodes зелёные. Независимый Red Team
  нашёл и после правок закрыты race Scar-cycle, corrupt-state acceptance,
  missing digest/events, stale replay, destructive one-click и double-click.
- Stars safety boundary: independent Red Team доказал неразрешимый без provenance
  gift/refund counterexample. Payment/static tests зелёные; test PostgreSQL создал
  `stars_payment_receipts_v1`; authenticated loopback: packages 200/disabled,
  invoice 403. Test bot перезапущен в exec-session `87274`.

## Known risks

- Production stop-ships остаются внешними: ротация раскрытого DB credential и
  owner-approved retirement compensation/snapshot.
- Stars reconciliation и invoice issuance намеренно выключены на preprod.
- Direct Stars supporter cosmetics v1 реализованы отдельно от legacy registry:
  immutable order snapshot → durable charge receipt → entitlement provenance →
  leased refund outbox. Production flags пока выключены до owner-approved
  production migration audit и real Telegram test purchase/refund. Существующие
  cosmetics также пересекаются с VIP-lock и combat set bonuses; новый SKU нельзя
  помещать в этот registry.
- Сгенерированные `__pycache__` безопасно игнорируются и не tracked; удаление
  было заблокировано политикой среды, повторять destructive cleanup не нужно.
- Telegram Login widget вне Telegram показывает `Bot domain invalid` на новом
  quick-tunnel domain: это требует ручной установки домена в BotFather. Сам
  запуск из меню test bot использует WebApp initData, но browser-only login не
  является доказательством Telegram-auth flow.

## Next action

Получить owner-approved production read-only audit/migration и выполнить один
реальный Stars purchase/refund на test bot перед включением production flags.
После этого продолжить release backlog, не трогая recovery/compensation без
LCB-002 snapshot.

## Completed — BOT-005 Stars recovery durability (2026-08-31)

Recovery now uses a durable single-worker lease, persists each outcome, scans
from Telegram history head and re-reads that head after a terminal page.  A
page cap, changed head, invalid/failed relevant row or Telegram API error opens
a durable critical alert; exceptional exits release the lease. Failed/invalid
rows receive an immutable per-charge observation, so operations can find the
specific evidence instead of an aggregate counter. `tools/test_stars_reconciliation_state_pg.py`
proves competing lease, failed Telegram call, alert state and immutable-journal
conflict on isolated PostgreSQL; `tools/test_bot_payments_contract.py` remains
green. Production work remains gated on the owner-approved read-only audit and
one real Telegram history-recovery test; Stars remain disabled on preprod.

## Completed — BOT-006 Smart Pulse delivery (2026-08-31)

`push_queue` now leases a single event before a Telegram call and records it as
delivered only after success. A transient failure clears the lease for retry;
forbidden/bad-request DMs are permanently classified rather than endlessly
retried; events unusable because of TTL/notification preference close without
pretending a DM happened. `tools/test_push_delivery_pg.py` proves the competing
lease, transient retry, success-only batch close and permanent classification
against isolated PostgreSQL. Residual: Telegram acceptance followed by a lost
HTTP response can cause a duplicate non-economic DM on retry, but no silent
loss; delivery is deliberately at-least-once.

## Completed — BOT-007 local-rank approvals (2026-08-31)

Local-rank confirmation callbacks now contain only an opaque token. The server
stores a ten-minute request bound to one chat, initiator, target, source rank
and desired rank. It checks approver authority before one-shot consume, then
rechecks the initiator's ability to assign and the target's unchanged source
rank. `tools/test_rank_requests_pg.py` proves wrong-chat denial and exact
one-shot consumption on isolated PostgreSQL. A changed source rank safely
invalidates the already-consumed request and requires a fresh one.

## Completed — BOT-008 background supervision (2026-08-31)

The co-hosted Mini App and every scheduler now have a named, retained task
handle. An unexpected return/crash logs critically and wakes the main owner,
which exits fail-fast rather than serving a partially dead process. Shutdown
cancels and awaits all handles. An injected failing coroutine proved the
critical failure signal; `py_compile` and `git diff --check` pass. The runtime
supervisor must remain configured to restart the process; individual tasks are
not hot-restarted in-place by design.

## Product-scope correction (2026-08-31)

`docs/PROJECT_RECONSTRUCTION_MASTER_PLAN.md` is the authority for current
game work. Its 2026-08-30 priority block explicitly removes the legacy
Reconstruction campaign, Memories, story chapters, Weekly Cases, Scar Map,
Feats and Sky from the new project. A brief attempt to generalize a second
legacy Memory reward was immediately reverted after the owner correction;
`tools/test_reconstruction_service.py` is green again. Do not implement or
extend those legacy game mechanics. Current approved near-term game scope is
only the new endless Rune Rhythm, Mini App Minesweeper and group-chat Mafia;
their detailed economies/catalogues remain deliberately deferred.

## Rhythm migration audit (2026-08-31)

The existing Mini App Rhythm is not a reusable implementation of the approved
endless rune game. It is coupled to the retired Reconstruction combat session,
weekly-case/scar-map surfaces and companion combat effects across
`reconstruction-lab.js`, `services/reconstruction_combat.py`,
`services/retention_v3.py` and related endpoints. The replacement needs a
separate server-owned run contract: endless health/score/chunks, normal versus
augments modes, global leaderboards, then quests/achievements only after their
owned event triggers are designed. Do not retrofit this legacy combat flow or
add its Memories/chapters back into the new Rhythm.

## New Rune Rhythm server contract (2026-08-31)

The approved endless Rune Rhythm now begins in independent files
`core/rhythm_v2.py`, `services/rhythm_v2.py`,
`infrastructure/repositories/rhythm_v2.py`, and `FastAPI/routers/rhythm_v2.py`.
It does not import the legacy Reconstruction/Memory/Scar Map layers. The server
owns the hidden deterministic seed, rune sequence, health, score, combo, pace
chunks and final result; a client may submit only one numbered rune tap plus an
opaque action id. Augmentation mode persists exactly three positive and three
negative offers and accepts exactly two from each offer. The current full v1
catalogue contains twenty of each polarity and is ruleset-versioned.

`tools/test_rhythm_v2_rules.py` and isolated PostgreSQL
`tools/test_rhythm_v2_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:55432/predvestnik_preprod`
are green. The latter proves duplicate-open-run refusal, action replay and
payload conflict, owner isolation, one-time final score, per-mode leaderboard,
unoffered augmentation refusal and two concurrent deliveries of the same tap.
Independent critic identified the remaining release gate: HTTP-arrival time is
not sufficient for a public competitive ranking. Add a time-synchronised
transport/anti-fraud review before exposing a global leaderboard. No rewards,
quests, achievements or Mini App UI are wired yet, intentionally, because their
economy/catalogue contracts remain deferred.

## Rune Rhythm live-transport correction (2026-08-31)

The independent transport critic rejected the original REST play path: returning
the expected rune from HTTP lets an authenticated script score perfectly.
`/rhythm-v2` REST now redacts the rune and has no tap writer. It issues only a
short hashed one-use transport ticket to the authenticated owner. The dedicated
`/rhythm-v2/runs/{run_id}/live` WebSocket receives the ticket as its first
message (not Telegram credentials in the URL), atomically claims one database
lease, then is the only channel that receives a rune or submits a tap. A silent
connection rechecks server deadlines every second; reconnect does not pause the
run. A minimal standalone Mini App screen has been added but stays behind
`game_rhythm_v2`.

The live transport test caught and fixed a real timezone bug: PGAdapter converts
aware datetimes to naive UTC, and PostgreSQL had reinterpreted them as local
time, moving a signal two hours into the past. The Rhythm repository now casts
those values explicitly as UTC timestamps. `test_rhythm_v2_pg.py` is green again
with live-ticket replay, first-signal timing, owner isolation and concurrent tap
coverage. Remaining product truth: websocket plus rate/lease controls mitigate
but cannot prove a human; a public global leaderboard remains feature-gated and
must use anomaly quarantine/manual review before any rewards are associated.

## Rhythm release gate correction (2026-08-31)

The system-flags repository is legacy fail-open for unknown keys. The new
`game_rhythm_v2` key is now explicitly registered as disabled by default,
protecting both the new screen and API before a controlled test rollout. The
Mini App screen and its CSS/JS routes are registered in `FastAPI/main.py`, but
remain unavailable until the explicit dev flag is enabled. A pure registry
assertion, syntax checks, rules test and isolated PostgreSQL contract test are
green. No browser smoke has been claimed yet because the running test process
must be restarted to load newly added static assets and the feature must remain
closed outside a controlled test account.

## Rhythm preprod screen correction (2026-08-31)

The initial document navigation to a Telegram Mini App cannot include the
`x-init-data` header: JavaScript receives `initData` only after that shell has
loaded. The first preprod launch incorrectly placed `require_tab_enabled` on
the `/rhythm-v2` HTML route and therefore returned 401 before the screen could
start. That dependency is now removed only from the static shell; every
`/rhythm-v2` API and WebSocket action remains feature-gated and requires the
authenticated server-owned contract. Isolated smoke proves unauthenticated
shell = 200 and unauthenticated `POST /runs` = 401. Rules and real PostgreSQL
contract tests are green. The test bot menu now intentionally opens this route
through the current temporary tunnel; production settings were not changed.

## Rhythm leaderboard screen (2026-08-31)

The standalone screen now renders two clearly separate per-mode tables with
the global top 20 and the viewer's own place after each finished run. It does
not disclose Telegram IDs or names: profile visibility is a separate product
and privacy decision. The DOM uses text nodes for all leaderboard data rather
than interpolating server fields as HTML. `node --check`, `git diff --check`,
the rule test and isolated PostgreSQL replay/finish/leaderboard proof are
green. The isolated test bot was restarted and both local plus external shells
returned 200. This is still a controlled test surface, not a fair public
competitive ranking: human verification/anomaly policy remains the release
gate.

External visual smoke at 320×680 and 390×844 found no horizontal overflow;
visible mode buttons are at least 52 px high and the compact view retains its
Telegram-only guidance without console errors. This does not substitute for a
real authenticated Telegram play-through.

## Rhythm reconnect correction (2026-08-31)

The old screen retained a closed WebSocket object, so its expiration handler
could never reconnect after a short mobile-network interruption. The client now
clears the old socket and retries a bounded exponential reconnect sequence;
server time keeps advancing throughout. The transport repository also prunes
only tickets expired for more than one hour before issuing another, preventing
reconnects from growing that short-lived table indefinitely. The real
PostgreSQL contract now proves a released lease can reconnect without changing
score or signal number, while action replay protection remains green. Static
syntax/diff checks and external preprod shell smoke pass after restart.

## Autonomous loopback test persona (2026-08-31)

For repeatable Mini App testing without a personal Telegram account, isolated
preprod now co-hosts a second ASGI listener bound only to `127.0.0.1:8404`.
Its sole route issues a 20-minute host-only HttpOnly cookie for synthetic user
`990000001`, then redirects locally to the main Mini App. `require_tg_user`
accepts that cookie only while `PREDVESTNIK_ENV=preprod`; no tunnel or
production route can issue it. The actual quick-tunnel request returns 404.
The visible Codex browser used this identity to load the app, call the normal
HTTP ticket route and complete the WebSocket handshake; no console errors.

Owner correction: an unfinished Rhythm run is an explicit cancellation, not a
loss. The new exit action and `pagehide` best-effort writer cancel it; starting
another run cancels a stranded one. Cancelled and zero-score runs do not appear
in the leaderboard. Real PostgreSQL proof now covers replacement/cancel,
foreign cancel refusal and zero-score omission; the visible browser proved
start → exit → immediate new start. The browser remains visible for live
testing. Production remains untouched.

## Rhythm screen interaction audit (2026-08-31)

Live inspection found the server was fast (direct isolated-PostgreSQL tap
processing measured about 7–10 ms), but the old screen made a correct tap look
ignored: it gave no immediate acknowledgement, allowed repeat presses before a
WebSocket reply, and did not distinguish a new signal when a random rune
repeated. `FastAPI/static/rhythm-v2.js`, `.html` and `.css` now lock all rune
buttons after the first tap, highlight the submitted button and render
“Тап принят — проверяем…”. A confirmed response then reenables input, visibly
marks “Новый такт” and shows the increasing signal number. The client derives
its fallback API mount path from the current screen, so a root-mounted preview
cannot accidentally call a missing `/rhythm-v2` route; the deployed HTML still
provides its authoritative `data-app-base` prefix. Restarted isolated preprod
served the new cache-busted HTML/assets. Visible browser proof completed seven
correct taps plus three deliberate errors for 604 points. `node --check`,
`tools/test_static_delivery_asgi.py`, pure rules and isolated PostgreSQL tests
are green. This improves feedback and prevents client-side double-submission;
network-time fairness remains unresolved and blocks public competitive rewards.

## Rhythm local-first loop (2026-08-31)

Owner rejected visible transport seams. The live WebSocket is therefore no
longer the play path: `offline_packet` gives the authenticated Mini App one
2,048-signal server-derived buffer; JavaScript resolves taps, timers, hearts,
score, chunks and feedback immediately in local storage. On defeat,
`finalize_offline_run` locks the run, replays the ordered journal against the
secret server seed and ignores all submitted totals. It allows only a journal
that ends at defeat and uses an idempotent finalization id. A visible preprod
run proved six correct + five deliberate errors → server-confirmed 660 with no
browser error. The approved initial pacing is ruleset `rhythm-v2-rules-3`:
five hearts, 2,000 ms initial window, 30-rune chunks and 5% speed increases;
buttons are colour/shape-coded (gold circle, teal square, violet triangle).
Rules, real PostgreSQL replay/packet/finalize proof, static ASGI and JS syntax
checks are green. Because client-reported timing is forgeable, this is strictly
a no-reward/test leaderboard until a future anti-cheat quarantine policy; do
not claim competitive fairness from the local-first transport.

The PostgreSQL proof now also rejects a foreign player's packet read, a journal
submitted before defeat, an altered replay under the same finalization id and a
journal with an action after defeat. This closes the initially untested offline
result boundaries; it does not change the known client-timing anti-cheat risk.

The local-first screen now removes its saved journal and sends a best-effort
keepalive cancellation both when the document becomes hidden and on `pagehide`;
this covers an immediate close before its local packet has loaded. A live
preprod browser test started a normal run, immediately navigated away, and the
latest `rhythm_v2_runs` row became `cancelled`. The explicit exit writer remains
the authoritative path. Browser close delivery is still best-effort by platform
design, so a future cleanup timeout is needed before claiming an absolute close
guarantee.

## Mini App Minesweeper (2026-08-31)

The approved new Minesweeper is a separate `/minesweeper` Mini App surface;
it replaces, rather than reuses or exposes, the retired wager implementation.
There are three mobile-fit difficulties: Easy 6×6/6 mines, Normal 9×9/10 and
Hard 9×9/18. Touch opens, a 420 ms hold flags, and the explicit flag mode is a
fallback. The server owns secret layouts and every action/revision; only after
the first server-validated safe open does the timer begin. Wins only are ranked
per difficulty by server elapsed time, then number of open actions. No rewards,
economy, quests or progression writer exists. New start cancels an unfinished
run. Rules and isolated PostgreSQL tests cover safe first halo, neighbour
counts, flood/flags, owner isolation, first-open requirement, idempotent action
retry, payload conflict, terminal loss and a verified ranking; static delivery,
Python and JavaScript checks pass. Browser proof on the 390px test tab covered
first safe open/cascade, a flag, difficulty switch and a completed loss showing
all six Easy mines without errors. A 320px test showed no horizontal overflow.
The new feature flag is `game_minesweeper_v2` (enabled only in isolated
preprod); it must be deliberately enabled for production rollout.

The player-facing `игры` command now names only the current Mini App games
(Ритм and the single new Сапёр) and its `startapp=game` link resolves to the
shared game hub. The legacy wager-session return remains a technical recovery
action only; it no longer presents a second player-facing Minesweeper.

## Chat Mafia v1 (2026-09-01, in progress)

The approved chat-native Mafia foundation is implemented behind the default-off
`game_mafia_v1` flag (enabled only on isolated preprod). Match state, roles,
deadline and actions are durable PostgreSQL state; one active match is allowed
per chat/topic. A separate message gate deletes only messages forbidden in the
current phase: during discussion living players may write, while at night and
voting the registered players are muted and nonplayers retain ordinary chat.
The code never changes the group’s baseline Telegram permissions. Lost delete
rights or an active purge pause the match safely. Lobby cards repeat after ten
human messages without resetting the server-stored party.

`tools/test_mafia_v1_pg.py` is a real isolated-PostgreSQL integration test
with four synthetic people and a deterministic Telegram transport. It proves
DM readiness, a private role delivery to every player (including Citizen), one
phase card edited rather than duplicated, phase access rules, stale start,
vote replacement, secret-vote non-disclosure, open-vote display, host-only
settings and cross-topic rejection. The pure rules, static delivery and
compile/diff checks are green. Mini App now has a read-only personal history
and statistics modal; its live loopback test also caught and fixed the broken
post-onboarding route into the current game hub.

Usability pass: lobby settings are now in the original Telegram card (seats,
optional roles, vote type), names in choice buttons have player numbers, and
each completed night/vote emits one clear group result line. A safety pause
stores its original phase and remaining duration; only the host may restore it
with `бот мафия, продолжить`, and never while purge remains active. Remaining
release gate: run one controlled real Telegram group test for bot deletion
rights, callback rendering and PM delivery before production enablement.

Follow-up UX pass: all primary actions are visible buttons (DM readiness,
lobby cancellation, host settings, pause resume/cancel); command text is only
a fallback. Settings now use a hierarchy rather than one wall: the first card
has only Players, Roles and Vote type; each opens its own focused picker. The
PostgreSQL integration now proves a foreign host and an active purge cannot
resume a party; the scheduler checks the feature flag before advancing stored
phases.

## Retired game-surface removal (2026-09-02)

Owner confirmed that legacy game code may be removed; compensation is deferred
to the final pre-release phase after a production-data audit. The public
Reconstruction client/router and the old Zoo router are removed; `/game` now
redirects to the activities hub, while former `/reconstruction/*`, `/zoo/*`
and Reconstruction static assets are absent. Old pet UI/navigation, chat
writes, Sky command and old expedition task are no longer active. Preserve
database rows only for the owner-approved later compensation audit.

Current approved public game scope remains Rune Rhythm, Mini App Minesweeper
and chat-native Mafia. The master plan also defines two role-aware concepts of
the same product: Activities Hub for players and Administrator Center for chat
admins; the UI may show both to a user who has relevant chat permissions.

Verification after the final surface-parity update: isolated preprod runner
completed `PREPROD_TESTS total=74 passed=74 failed=0`; direct ASGI probes prove
the retired routes are absent and the current hub redirect works. This is not a
production release verdict: real Telegram group Mafia verification and the
future owner-approved pet/economy/event/cosmetics waves remain outstanding.

## Legacy scheduler and chat-settings reduction (2026-09-02)

The test bot now starts only `maintenance_task` (daily expiry of timed warns,
account-deletion lifecycle and analytics retention) plus the approved Mafia
phase scheduler.  Legacy auction/duel, crypto, Smart Pulse, expedition and
other legacy-game loops are not scheduled.  An independent read-only audit
confirmed that Stars reconciliation remains required outside isolated preprod
for payment recovery.

Player and moderator help no longer advertises the retired market, expeditions
or closed passive rewards.  The chat and web admin settings now expose only
the current game/warp switches, while a stale former auction-rank callback is
explicitly rejected before any database writer.  The focused authorization
contract, Python compile checks, JavaScript syntax check and diff validation
are green; a restarted test bot log confirms maintenance and Mafia schedules.

The current approved-scope isolated preprod run completed `PREPROD_TESTS
total=73 passed=73 failed=0`.  The former lore-exchange test was removed from
that gate because it explicitly required the deleted crypto-alert scheduler;
the test runner continues to keep archival data and compensation tests.

## Readability cleanup (2026-10-07, in progress)

The owner paused design changes and requested code-only cleanup. Frontend
renderers for chat tracking, achievements and pets are separated into readable
builders. Backend audit removed dead imports and variables (`31c6ceea`), the
retired shop execution tail (`8760ee1c`), and 440 more unreachable lines behind
the fail-closed auction, gacha, direct-gift and legacy family-wallet boundaries
(`b224d9b8`). Inventory removal no longer turns a PostgreSQL failure into a
false "insufficient stock" result (`347e4415`); the error rolls back and reaches
the normal failure boundary. The full isolated preprod gate is 114/114 after
both behavior-sensitive waves. No unrelated `IESA_ROOT/` changes were staged.

Next: audit broad exception handlers that can still hide infrastructure faults,
starting with active payment/economy paths. The 1106-line exchange
`ensure_tables()` remains the highest-value structural target, but split it only
with the isolated PostgreSQL exchange migration test after every step.
