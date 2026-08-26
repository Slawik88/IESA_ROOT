#!/usr/bin/env python3
"""Static contract for the cross-platform local preview launcher."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
preview = (ROOT / "tools" / "preview_server.mjs").read_text(encoding="utf-8")
bridge = (ROOT / "tools" / "reconstruction_preview_api.py").read_text(encoding="utf-8")
docs = (ROOT / "LOCAL_PREVIEW.md").read_text(encoding="utf-8")
tasks = (ROOT.parent / ".vscode" / "tasks.json").read_text(encoding="utf-8")

assert "process.env.PYTHON?.trim()" in preview
assert "'.venv', 'Scripts', 'python.exe'" in preview
assert "'.venv', 'bin', 'python'" in preview
assert "process.platform === 'win32' ? 'python' : 'python3'" in preview
assert "spawn('python3'" not in preview
assert "child.once('error'" in preview
assert "if (!requested)" in preview
assert "setTimeout(() => {\n      startReconstructionApi();" in preview
assert "}, 80).unref();" in preview

assert "process.env.RECON_PREVIEW_PORT) || 8404" in preview
assert 'os.environ.get("RECON_PREVIEW_PORT", "8404")' in bridge
assert "tempfile.gettempdir()" in bridge
assert "STATE_FILE.parent.mkdir(parents=True, exist_ok=True)" in bridge
assert "8404" in docs and "8403" in docs

assert '"command": "nix-shell"' not in tasks
assert '"label": "Predvestnik: local preview"' in tasks
assert '"label": "Predvestnik: UI regressions"' in tasks

print("windows preview contract: OK")
