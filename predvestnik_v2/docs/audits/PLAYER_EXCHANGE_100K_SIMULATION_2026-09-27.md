# Player Exchange Spot MVP — 100,000-market simulation

Status: **PASS**

- Rules: `player-exchange-v1-2026-09-26`
- Seed: `20260927`
- Markets: `100000`
- Generated bids: `1201981`
- Non-empty auction models: `95923`
- Empty auction models: `4077`
- Allocated token units: `26832036639125`
- Spot trades executed by the mutable model: `146082`
- Partial fills: `146082`
- IOC residual cancellations: `162234`
- Self-crosses prevented: `58456`
- Owner/treasury crosses prevented: `29555`
- Treasury trades: `63862`
- Halt transitions: `112314`
- Explicit user cancellations: `143893`
- Maker side: buy `73074`, sell `73008`
- Modelled fees: `22251121.670512` Mora
- Deterministic digest: `787ced1d12b61668b166d8f975e6fb9d84b9b2df50c3a140492593f61021fdd5`

The same command was run twice and produced byte-identical output:

```text
python tools/simulate_player_exchange_v1.py --markets 100000 --seed 20260927
```

Every generated market checked auction supply and escrow conservation and then
ran an independent mutable order book through random placement, price-time
matching, partial fills, cancellation/refund, IOC residual closure, maker-side
reversal, self/owner-treasury cross prevention, treasury buy/sell and halt
sequences. After all open orders were drained, the model proved exact Mora,
token, fee-fund and circulating-supply conservation. It also checked ladder
separation, protected-order slippage and strict inward ±5% depth bounds.

This is a pure deterministic model gate. It complements rather than replaces the
real PostgreSQL concurrency and custody contract in
`tools/test_player_exchange_v1_pg.py`.
