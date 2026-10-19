# Rhythm gift revision — 2026-10-19

## New choices

| Gift | Benefit | Cost |
|---|---|---|
| Метроном | Every fourth correct input in the uninterrupted combo: +115% score | Other inputs: -15%; max one copy |
| Последняя искра | +25% score at 1–2 hearts | Pays one heart on selection; -8% score at 3+ hearts; max one copy |
| Второе дыхание | After actual heart loss, next three signals have 25% wider windows | Permanent -12% score; no healing; max one copy |

All arithmetic remains server-side. Metronome adds its bonus to the common
percentage pool. Its long flat-combo average is +17.5%, not a multiplicative
loop. Last Spark scores from health before Vampire regeneration. Second Wind
triggers once for a surviving damaging error, regardless of how many hearts were
lost. Shields, free timeouts, selection costs and reconnects do not trigger it.
Every subsequent signal consumes one charge; another damaging error may re-arm
three charges. Dead runs never revive.

## Combination review and tuning

An initial Last Spark value (+37% at low health) made Spark → Glass Cannon
strictly stronger than the existing Glass + Gambit pair while keeping a wider
window. It was reduced to +25%. The final first order ends at two hearts with
+85% combined score; Glass → Spark ends at one heart. Glass + Gambit retains
+90% with its narrower window. These are deliberate tradeoffs.

Metronome was raised from a weak +2.5% flat-combo average to +17.5%. Slower
inputs never score more, including a fast fourth input with Sharp Eye. Even the
maximal legal positive score build, both Echo copies, Sharp Eye, a bloody charge,
Metronome accent and low-health Spark yields at most 5733 for one input. This is
a bounded burst, not exponential growth; triple-score charges still expire.

Tests enumerate 7689 eligible singles, ordered pairs and new-gift triples across
five health states. They also check maximum stacks, lower window bounds,
shield/free-timeout interactions, paid multi-heart damage, expiry, dead runs,
Vampire timing, and old offer pools. Continuous misses always exhaust health.

## Simulation and integration

The prior simulator omitted the live 250 ms grace. It now uses the same grace
and slow-tier scoring as the server. Comparison uses 250 runs for each of four
reaction/error profiles, three selection policies and two pools: 6000 runs.
Policies choose randomly within safe/non-safe categories, so this is not an
optimal-build solver. Published results are in
`rhythm-gifts-balance-2026-10-19.csv`.

No simulation reached its 6000-signal safety cap. New safe-policy median run
length increased by roughly 1–7%; score medians generally decreased, with no
broad score inflation. Fast non-safe random selection loses more score because
conditional gifts require deliberate build choices. These synthetic results do
not guarantee balance for every human strategy or limit perfect play.

New runs use rules 6; existing runs retain their original 14-gift pool and old
gift values. PG proof checks both pools, a real damaging tap, stored recovery,
reconnect and exactly three subsequent correct signals. Existing replay,
leaderboard, transport and grace checks pass. Mobile fixture screenshots at
320/430 verify readable bonus/cost/preview text and touch targets; they exercise
the production renderer with supplied draft state, not a live human run.
