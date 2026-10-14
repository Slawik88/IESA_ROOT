# A03 — bounded memory in the shared WebSocket session

**Risk:** T1 (availability; no money, data or permissions). **Status:** draft PR, not released.
**Source:** owner audit 2026-10-14, A03 (A07 checked in the same file).

## Goal and acceptance
- A stream of arbitrary `lot_id` commands leaves no persistent entries.
- A slow/stalled client cannot grow memory without bound.
- Two tabs of one account: closing either keeps delivery to the other (A07).

## Decisions
- The live lot-room protocol (`sub_lot`/`unsub_lot`/`lot_react`, `_lot_rooms`, `_react_last`)
  is removed, not hardened: the auction is retired, no client sends these commands
  (`app.*.js` sends only `ping`) and no server code calls `broadcast_lot`/`lot_viewers`.
- Per-connection queue is bounded (`WS_QUEUE_MAXSIZE = 256`). On overflow the connection is
  unregistered and closed with 1013; the client already reconnects with backoff
  (`app.01.js` `ws.onclose`). `notify()` returns False when no connection accepted the event,
  so callers keep their existing offline fallback.
- A07 is already fixed on master (`_queues` holds a set per user; `unregister(user_id, q)`).

## Checks
- New offline `tools/test_ws_session_bounds.py`: 10,000 junk room commands store nothing;
  stalled reader closed with 1013 and backlog ≤ 256; two-tab close in both orders keeps delivery.
  Fails on master.
- `test_release_public_routes.py`, `test_static_delivery_asgi.py`: OK.
- `test_balance_events_pg.py` fails on this DB and on master identically (`skins_v3_essence_accounts`
  missing: schema bootstrap gap, audit A14).
