#!/usr/bin/env python3
"""The shipped Rhythm client must use only the trusted server-timed channel."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (ROOT / "FastAPI/static/rhythm-v2.js").read_text(encoding="utf-8")
SERVICE = (ROOT / "services/rhythm_v2.py").read_text(encoding="utf-8")
ROUTER = (ROOT / "FastAPI/routers/rhythm_v2.py").read_text(encoding="utf-8")

assert "/transport-ticket" in CLIENT
assert "new WebSocket(target)" in CLIENT
assert "type:'authenticate'" in CLIENT
assert "type:'tap'" in CLIENT
assert "pendingTap.actionId" in CLIENT
assert "scheduleReconnect" in CLIENT
assert "localStorage.getItem('pv_sess')" in CLIENT
assert "headers['x-session-token'] = session" in CLIENT
assert "/offline-packet" not in CLIENT
assert "/finalize" not in CLIENT
assert "predvestnik-rhythm-v2-local" in CLIENT  # cleanup only
assert '"remaining_ms": remaining_ms' in SERVICE
assert 'trusted_transport: bool = False' in SERVICE
assert 'integrity_status="clear" if trusted_transport else "review_required"' in SERVICE
assert "promote_authenticated_transport_reviews" in SERVICE
assert 'integrity_status="clear", integrity_reason="server_timed_transport"' in SERVICE
assert "await game.review_run(" in ROUTER
assert '@router.get("/integrity/reviews")' in ROUTER
assert '@router.post("/integrity/reviews/{run_id}")' in ROUTER
assert "DEVELOPER_GLOBAL_RANK" in ROUTER
assert "ожидает проверки" in CLIENT
assert "await repo.lock_integrity_review_id(db, review_id=review_id)" in SERVICE

print("OK: shipped Rhythm uses ticketed WS, stable replay, authoritative timing and gated review")
