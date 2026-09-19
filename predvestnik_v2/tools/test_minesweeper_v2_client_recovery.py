#!/usr/bin/env python3
"""A lost Minesweeper response must not become a second logical action."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (ROOT / "FastAPI/static/minesweeper-v2.js").read_text(encoding="utf-8")

assert "uncertain={runId:run.run_id,actionId:crypto.randomUUID(),expectedRevision:run.revision,kind,cell}" in CLIENT
assert "action_id:request.actionId" in CLIENT
assert "expected_revision:request.expectedRevision" in CLIENT
assert "await api(`/runs/${encodeURIComponent(request.runId)}`)" in CLIENT
assert "Number(current.revision)!==Number(request.expectedRevision)" in CLIENT
assert "uncertain?'Восстановить ход':'Новая партия'" in CLIENT
assert "button.disabled=busy||Boolean(uncertain)" in CLIENT

print("OK: uncertain Minesweeper actions reuse their id and refetch authority")
