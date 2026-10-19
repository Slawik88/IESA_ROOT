# Achievement revision — 2026-10-19

The previous player screen offered five identical long paths: Rhythm,
Minesweeper, Mafia, chests and pet activities. All required both terminal counts
and active weeks; level 40 required 156 weeks. Chat achievements already cover
conversation, warps, transfers, family and games. Retired legacy achievements
remain history and are not reactivated as reward writers.

## New finite series

| Series | Verified fact | Cumulative milestones | Lifetime Mora |
|---|---|---|---:|
| Заботливый | A successful feeding day, once per account UTC day | 1, 3, 7, 14, 30, 60, 120, 365 | 40 |
| Мастер лагеря | A paid camp building level has started | 1, 3, 6, 10, 15 | 25 |
| Мастер образов | A distinct skin + target tier was actually upgraded | 1, 3, 6, 12, 24, 48, 96 | 35 |
| Дело дня | The daily quest bundle reward was claimed | 1, 3, 7, 14, 30, 60, 120, 365 | 40 |

These series have no weekly gate. Their 28 levels add at most 140 Mora over
the account lifetime, without resets or payouts for page views, repeated feeding
in one day, equip/unequip, failed actions, weekly/combined quest claims or replay.
The old five paths retain thresholds, reward identities and all earned progress.
There are now nine paths / 228 levels, plus the existing chat achievements.

## Atomicity and historical fairness

Each live fact is recorded inside the successful source transaction. A canonical
fact-only snapshot makes multiple pets in one day the same immutable identity.
Camp counts the irreversible paid start, accurately described in the UI.
Skins acquire the global achievement user lock before the existing user-row lock.

An authenticated owned POST reconciliation restores history from negative
skin/camp Essence receipts, successful cached feeding actions and daily quest
reward receipts. It never trusts client counters or imports retired awards.
Valid historical facts use the exact same IDs as live hooks. Known facts are
skipped; later reconciliations still detect old-worker receipts that committed
after an earlier import. The import audit marker is append-only. Malformed or
future history is not treated as evidence. GET overview remains read-only.

## Presentation and validation

The new Development filter uses each series' actual level limit and measure.
Finite series omit the weekly meter; the summary sums server limits. The profile
aspect strip wraps in five columns. On narrow phones the help button retains a
44 px target without overlapping the heading.

Passing checks: pure thresholds/reward budget, existing achievement PG replay,
conflict and immutable rewards, new history PG proof (all 15 camp levels and
96 skin tiers, feeding-day dedupe, daily-only claims, late receipts, replay and
rollback), real pet/skin/quest PG integrations, legacy retirement/gallery checks,
and static visual delivery. Edge 320/430 verifies all nine families, limits,
filters, details, preserved game conditions and no header/page overflow.
Local screenshots: .local/ui-achievements-life/.
