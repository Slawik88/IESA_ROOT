# VIP conditional spot orders — 2026-10-19

## Player behavior

An active VIP may create up to ten pending buy/sell orders across all v2 coins.
Choose a price at or below / at or above a threshold that has not yet been met.
Buy uses a Mora budget (minimum 10); sell uses an explicit coin quantity.
The lifetime is 30 days in server ticks. Execution occurs at a later server tick
price, which may pass the threshold, with the same 0.5% fee as manual spot trades.
No exact threshold price is promised. No margin/short position is created.

Funds and units are not reserved. The form and confirmation explain this.
Execution checks available funds/units again; insufficient balance, missing units,
account deletion or expired VIP produces a terminal failure with a visible reason.
There is no repeated buy attempt after a failure. Completed history shows the
actual execution price; ordinary trade markers also include automatic fills.

Orders are checked by `advance` in the existing server maintenance path, including
while the player is offline. Entry switch off pauses all automatic trades; order
expiry continues. Existing holders or pending-order owners retain market access
and cancellation when entry is off. Cancellation does not require current VIP.
A simultaneous fill/cancel returns the actual winning terminal status.

## Authority and accounting

Strict authenticated HTTP adapter accepts only buy/sell, two directions, a numeric
threshold and bounded units. No caller-supplied user, payout or execution price.
Creation serializes the per-user cap across coins and stores an immutable receipt.
The client reuses its existing persisted action/receipt recovery protocol.
A successful POST followed by failed refresh does not repeat order creation.

Coin locks serialize ticks, cancellation and manual spot trades. Before an actual
catch-up, involved user advisory locks are acquired in ascending order across
coins. A no-op advance skips participant locks. Each attempted fill has a savepoint;
wallet, inventory, cost basis, immutable receipt/event and order status succeed
atomically. Manual and automatic trades share `execute_spot` and core quote rules.
Unexpected failures roll back the entire tick, leaving orders retryable. Expected
insufficiency rolls back only that order, then records its failure reason.

The pending-coin index restricts trigger lookup to the relevant coin. Creation is
capped per user, not globally. Large simultaneous trigger cohorts still require
server work proportional to the cohort; no unsupported constant-latency claim.
Existing coin catch-up remains bounded to 288 ticks per call. No production flag
or production database was changed by this revision.

## Verification

`tools/test_coin_market_orders_pg.py` runs the existing exchange regression suite
in a disposable schema on the isolated loopback 55856 cluster, then verifies:

- VIP placement and expiration, no reservation/debit at placement;
- shared ten-order cap, receipt replay and payload conflict;
- private/strict authenticated endpoints;
- two workers executing one tick produce exactly one fill;
- actual price differs from crossed threshold and fee/accounting remain canonical;
- insufficient Mora/units, expiration, entry pause and later resume;
- pending-buy-only market visibility while entry is disabled;
- placement and fill receipt failure roll back order/wallet/account/tick;
- cancellation versus fill and two coins with overlapping users do not deadlock;
- no participant locks on a no-op quote/advance.

Existing 15 core tests, chart, preview and persisted recovery Node checks pass.
Edge at 320/430 px with real app assets and HTTP fixtures verifies the form,
confirmation, lists and cancellation without horizontal overflow. A simulated
committed POST with lost response recovers via GET receipt with one create POST.
These are browser delivery fixtures; server economics are proven separately by PG.
