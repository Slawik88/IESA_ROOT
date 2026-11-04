#!/usr/bin/env python3
"""Fast, real test gate for Predvestnik (used by the pre-push hook and by hand).

What it runs:
  * every quick test that needs no database, in parallel (≈ a minute);
  * PostgreSQL tests that touch the changed files, one by one on the disposable loopback
    cluster (``tools/preprod_postgres.ps1``: 127.0.0.1:55432/predvestnik_preprod), each from clean
    data via ``reset_test_data.py`` — the same isolation as ``run_preprod_tests.ps1``.

Which test needs a database, how long it takes and which ones already fail on master lives in
``tools/test_gate.json``. Rebuild it after big test changes (≈ 15 min, needs the cluster):

    python tools/run_fast_tests.py --refresh-manifest

Usage:
    python tools/run_fast_tests.py                      # quick no-DB set only
    python tools/run_fast_tests.py --changed a.py b.js  # + DB tests related to these files
    python tools/run_fast_tests.py --all                # everything in the manifest (the slow full gate)

Exit code 0 = green. A test listed in ``quarantine`` is skipped (it fails on master for a known
reason); any other failure is red. A new test file that is not in the manifest yet is run too
(with the database if one is up).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]          # predvestnik_v2/
TOOLS = ROOT / "tools"
MANIFEST = TOOLS / "test_gate.json"
DSN = os.environ.get("PREPROD_TEST_DSN") or \
    f"postgresql://predvestnik_preprod@127.0.0.1:{os.environ.get('PREPROD_PG_PORT', '55432')}/predvestnik_preprod"
FAST_LIMIT_S = 20        # a no-DB test slower than this runs only when related to the change
TEST_TIMEOUT_S = 240
PG_BIN_DIR = Path(r"C:\Program Files\PostgreSQL")


def _env(with_db: bool) -> dict:
    env = dict(os.environ)
    for key in ("BOT_TOKEN", "BOT_USERNAME", "DEVELOPER_ID", "DATABASE_URL", "PREDVESTNIK_DATABASE_URL",
                "COSMETIC_TEST_DATABASE_URL", "THEME_TEST_DATABASE_URL", "MINIAPP_URL", "PREPROD_MINIAPP_URL",
                "PREPROD_ALLOWED_TG_IDS", "PREDVESTNIK_ENV", "PORT", "ROOT_PATH"):
        env.pop(key, None)
    # Without a database the DSN points at a closed loopback port: a test that silently needs one fails
    # fast instead of reaching anything real.
    dsn = DSN if with_db else "postgresql://nobody@127.0.0.1:1/none"
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT), DATABASE_URL=dsn,
               COSMETIC_TEST_DATABASE_URL=dsn, THEME_TEST_DATABASE_URL=dsn, BOT_TOKEN="123456:offline-preprod-tests",
               BOT_USERNAME="offline_preprod_test_bot", DEVELOPER_ID="101", PREPROD_ALLOWED_TG_IDS="101,202",
               MINIAPP_URL="https://preprod.invalid/predvestnik", PORT="0")
    return env


def _proc(argv: list[str], env: dict | None) -> tuple[int | str, str]:
    """Run with a timeout that kills the whole tree: a venv python.exe is a launcher whose child keeps the pipes open."""
    p = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        out, _ = p.communicate(timeout=TEST_TIMEOUT_S)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            p.kill()
        try:
            out, _ = p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out = ""
        return "timeout", (out or "")[-2000:]


def _run_test(path: Path, with_db: bool) -> tuple[str, int | str, float, str]:
    src = path.read_text(encoding="utf-8", errors="replace")
    argv = [sys.executable, str(path)]
    env = _env(with_db)
    if with_db and re.search(r"add_argument\([\"']--dsn", src):
        argv += ["--dsn", DSN]
    if with_db and "PREDVESTNIK_ENV" in src:
        env["PREDVESTNIK_ENV"] = "preprod"
    start = time.time()
    code, out = _proc(argv, env)
    return path.name, code, round(time.time() - start, 1), out


def _run_node(path: Path) -> tuple[str, int | str, float, str]:
    start = time.time()
    code, out = _proc(["node", str(path)], None)
    return path.name, code, round(time.time() - start, 1), out


# ---------- database ----------

def _pg_bin() -> Path | None:
    if os.environ.get("PREDVESTNIK_PG_BIN"):
        return Path(os.environ["PREDVESTNIK_PG_BIN"])
    found = shutil.which("pg_ctl")
    if found:
        return Path(found).parent
    versions = sorted((p for p in PG_BIN_DIR.glob("*") if p.name.isdigit()), key=lambda p: -int(p.name)) \
        if PG_BIN_DIR.exists() else []
    return versions[0] / "bin" if versions else None


def _data_dir() -> Path:
    if os.environ.get("PREPROD_PG_DATA_DIR"):
        return Path(os.environ["PREPROD_PG_DATA_DIR"])
    # Worktrees share the main checkout's cluster: <main>/.local/preprod-postgres.
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    main = Path(common).parent if common else ROOT.parent
    return main / ".local" / "preprod-postgres"


def db_up() -> bool:
    try:
        import asyncio
        import asyncpg

        async def ping():
            c = await asyncpg.connect(DSN, timeout=3)
            await c.close()
        asyncio.run(ping())
        return True
    except Exception:
        return False


def ensure_db(log) -> bool:
    if urlparse(DSN).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("only a loopback PostgreSQL DSN is allowed")
    if db_up():
        return True
    pg, data = _pg_bin(), _data_dir()
    if not pg or not (data / "PG_VERSION").exists():
        log(f"no local PostgreSQL cluster ({data}); DB tests skipped. Create one: tools/preprod_postgres.ps1 start")
        return False
    port = urlparse(DSN).port or 55432
    log(f"starting PostgreSQL {data} on :{port} ...")
    # stdio to a file, not a pipe: the postmaster inherits it and would keep the pipe open forever.
    with open(data / "postgres.log", "ab") as logf:
        subprocess.run([str(pg / "pg_ctl"), f"--pgdata={data}", "-w", "-t", "60", "-o", f"-p {port} -h 127.0.0.1",
                        "start"], stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, timeout=90,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return db_up()


def prepare_db(log, bootstrap: bool) -> bool:
    py = [sys.executable]
    env = _env(True)
    steps = ([("bootstrap", [str(TOOLS / "bootstrap_test_db.py"), "--dsn", DSN]),
              ("snapshot", [str(TOOLS / "reset_test_data.py"), "--dsn", DSN, "--snapshot-refresh"])]
             if bootstrap else [])
    for label, argv in steps:
        r = subprocess.run(py + argv, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        if r.returncode != 0:
            log(f"{label} failed:\n" + (r.stdout + r.stderr)[-3000:])
            return False
    return True


def reset_db() -> bool:
    r = subprocess.run([sys.executable, str(TOOLS / "reset_test_data.py"), "--dsn", DSN], cwd=ROOT,
                       env=_env(True), capture_output=True, timeout=180)
    return r.returncode == 0


def snapshot_present() -> bool:
    try:
        import asyncio
        import asyncpg

        async def q():
            c = await asyncpg.connect(DSN, timeout=3)
            try:
                return await c.fetchval("SELECT count(*) FROM information_schema.schemata WHERE schema_name='reset_backup'")
            finally:
                await c.close()
        return bool(asyncio.run(q()))
    except Exception:
        return False


# ---------- selection ----------

def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"tests": {}, "quarantine": {}}


def related(test: Path, changed: list[str]) -> bool:
    """A test is related when its name or its source mentions a changed module / file."""
    src = None
    for rel in changed:
        p = Path(rel)
        if p.name == test.name:
            return True
        stem = p.stem
        if len(stem) < 4 or stem in {"__init__", "main", "utils", "index", "app", "base"}:
            continue
        if stem in test.stem:
            return True
        if src is None:
            src = test.read_text(encoding="utf-8", errors="replace")
        if re.search(rf"(?<![\w]){re.escape(stem)}(?![\w])", src) or p.name in src:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--changed", nargs="*", default=None, help="repo-relative changed files")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--bootstrap", action="store_true", help="re-run the schema bootstrap + snapshot first")
    ap.add_argument("--refresh-manifest", action="store_true")
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4))
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):   # test output carries emoji; a redirected Windows console is cp1251
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    def log(msg):
        print(msg, flush=True)

    manifest = load_manifest()
    meta, quarantine = manifest.get("tests", {}), manifest.get("quarantine", {})
    py_tests = sorted(TOOLS.glob("test_*.py"))
    js_tests = sorted(TOOLS.glob("test_*.js"))
    changed = [c.replace("\\", "/") for c in (args.changed or [])]
    changed = [c[len("predvestnik_v2/"):] if c.startswith("predvestnik_v2/") else c for c in changed]

    if args.refresh_manifest:
        return refresh_manifest(py_tests, quarantine, args.jobs, log)

    nodb, withdb, skipped = [], [], []
    for t in py_tests:
        if t.name in quarantine:
            skipped.append(t.name)
            continue
        info = meta.get(t.name)
        rel = bool(changed) and related(t, changed)
        if info is None:                       # new test: run it, prefer the database
            withdb.append(t)
        elif not info.get("db"):
            if args.all or rel or info.get("s", 0) <= FAST_LIMIT_S:
                nodb.append(t)
        elif args.all or rel:
            withdb.append(t)

    results = []
    t0 = time.time()
    log(f"no-DB tests: {len(nodb)} (parallel x{args.jobs}); DB tests selected: {len(withdb)}; quarantined: {len(skipped)}")
    with ThreadPoolExecutor(args.jobs) as ex:
        results += list(ex.map(lambda t: _run_test(t, False), nodb))
        results += list(ex.map(_run_node, js_tests if (args.all or any(c.endswith(".js") for c in changed)) else []))

    if withdb and not args.no_db:
        if ensure_db(log) and prepare_db(log, args.bootstrap or not snapshot_present()):
            for t in withdb:
                if not reset_db():
                    results.append((t.name, "reset-failed", 0.0, ""))
                    continue
                results.append(_run_test(t, True))
        else:
            fresh = [t.name for t in withdb if t.name not in meta]
            log("DB unavailable: skipped DB tests " + ", ".join(t.name for t in withdb)[:600])
            # New tests not yet classified: run them without the DB so pure ones still count.
            results += [_run_test(TOOLS / n, False) for n in fresh]

    failed = [r for r in results if r[1] != 0]
    for name, code, secs, out in failed:
        log(f"\nFAIL {name} (exit {code}, {secs}s)\n" + "\n".join(out.strip().splitlines()[-25:]))
    log(f"\nPREDVESTNIK_FAST_TESTS total={len(results)} passed={len(results) - len(failed)} "
        f"failed={len(failed)} quarantined={len(skipped)} time={round(time.time() - t0)}s")
    return 1 if failed else 0


def refresh_manifest(py_tests, quarantine, jobs, log) -> int:
    """Run every test without the DB (parallel), then the failures with it: that sorts db / no-db / broken."""
    log(f"pass 1: {len(py_tests)} tests without a database ...")
    with ThreadPoolExecutor(jobs) as ex:
        first = {r[0]: r for r in ex.map(lambda t: _run_test(t, False), py_tests)}
    tests, new_q = {}, {}
    for name, (_, code, secs, _o) in first.items():
        if code == 0:
            tests[name] = {"db": False, "s": secs}
    retry = [t for t in py_tests if t.name not in tests]
    if not (ensure_db(log) and prepare_db(log, True)):
        log("database unavailable: cannot classify the remaining tests")
        return 2
    log(f"pass 2: {len(retry)} tests with the database, one by one ...")
    for t in retry:
        reset_db()
        name, code, secs, out = _run_test(t, True)
        if code == 0:
            tests[name] = {"db": True, "s": secs}
        else:
            last = next((ln.strip() for ln in reversed(out.strip().splitlines()) if ln.strip()), "")
            new_q[name] = quarantine.get(name) or f"fails on master at manifest refresh (exit {code}): {last[:160]}"
            log(f"  quarantine {name}: {new_q[name]}")
    MANIFEST.write_text(json.dumps({"_doc": "generated by tools/run_fast_tests.py --refresh-manifest; "
                                             "quarantine = known failures on master (fix the test, then remove it here)",
                                    "tests": dict(sorted(tests.items())), "quarantine": dict(sorted(new_q.items()))},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"manifest: {len(tests)} green ({sum(1 for v in tests.values() if v['db'])} need DB), {len(new_q)} quarantined")
    return 0


if __name__ == "__main__":
    sys.exit(main())
