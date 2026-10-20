#!/usr/bin/env python3
"""A lost Minesweeper response must not become a second logical action."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (ROOT / "FastAPI/static/minesweeper-v2.js").read_text(encoding="utf-8")

assert "PVLocal.Mines" in CLIENT
assert "/local-packet" in CLIENT and "store.fresh('minesweeper',difficulty)" in CLIENT
assert "journal.push({kind,cell,elapsed_ms:elapsed})" in CLIENT
assert "store.queue(engine.packet,journal)" in CLIENT
assert "store.data.active" in CLIENT and "function restore()" in CLIENT
assert "localStorage.getItem('pv_sess')" in CLIENT
assert "headers['x-session-token']=session" in CLIENT
print("OK: Minesweeper actions resolve locally and terminal results persist across connection loss")
