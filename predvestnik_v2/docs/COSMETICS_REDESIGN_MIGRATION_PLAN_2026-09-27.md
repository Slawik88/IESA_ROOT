# Cosmetics redesign migration plan

Status: approved direction, not authorized for mass execution yet.

## Player promise

No paid cosmetic value disappears during the redesign. For each currently owned
item the player receives exactly one of these outcomes:

1. the redesigned successor with the same ownership entitlement; or
2. the item's actually paid Zarniki price returned once when no successor ships.

Items already retired and compensated by the 2026-09 migration are excluded.
They may not receive a second refund.

## Safe sequence

1. Close all cosmetic purchase writers while keeping owned items readable.
2. Take a repeatable snapshot of catalogue versions, ownership, purchase
   receipts, paid price and prior compensation references.
3. Publish the old-to-new catalogue mapping before changing entitlements.
4. Rehearse the migration on a restored production snapshot and reconcile every
   source row to exactly one outcome.
5. Apply append-only, replay-safe migration receipts. Never infer paid price
   from the current shop price when the original receipt exists.
6. Show each player a plain-language migration story: kept, redesigned, refunded.
7. Re-enable purchases only after the base UI, every saleable skin, mobile
   contrast, reduced-motion behavior and receipt reconciliation pass.

## Hard gates

- Purchase close is server-side, not a hidden button.
- Snapshot hash and catalogue mapping version are frozen before apply.
- One source entitlement produces one immutable result receipt.
- A second run produces only replays and zero balance/entitlement changes.
- Refund totals equal the frozen inventory; no negative balances or orphaned
  ownership rows remain.
- Opening the shop is a separate explicit release switch after verification.
