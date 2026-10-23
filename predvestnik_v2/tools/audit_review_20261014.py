"""Offline reproductions for the 2026-10-14 audit; no application DB or network.

Run from predvestnik_v2 with the project Python. Assertions document CURRENT
defects, not desired behavior. After fixes these probes should stop passing.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['BOT_TOKEN'] = '123456:offline-audit-fixture'


def extract(path, name, scope):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(ROOT / path), 'exec'), scope)
    return scope[name]


async def main():
    from FastAPI import auth, notifications as n
    results = []
    def passed(name, evidence):
        results.append({'probe': name, 'current_defect_reproduced': True, 'evidence': evidence})

    with patch.dict(os.environ, {'BOT_TOKEN': ''}):
        payload = f'101:{int(time.time()) + 600}'
        sig = hmac.new(hashlib.sha256(b'session').digest(), payload.encode(), hashlib.sha256).hexdigest()
        assert auth.verify_session_token(payload + ':' + sig) == 101
    passed('empty_bot_token', 'Known-key token accepted when BOT_TOKEN is empty; conditional configuration defect.')

    a, b = asyncio.Queue(), asyncio.Queue()
    n.register(101, a)
    n.register(101, b)
    n.unregister(101)  # first connection closes after the second registered
    assert not await n.notify(101, {'type': 'audit'})
    passed('two_websockets', 'Closing A removes the queue belonging to still-open B.')

    before = len(n._react_last)
    for i in range(100):
        await n._handle_client_message(101, json.dumps({'type': 'lot_react', 'lot_id': 100000 + i}))
    await n._leave_all(101)
    assert len(n._react_last) == before + 100
    passed('websocket_memory', '100 reactions to nonexistent rooms leave 100 permanent keys after disconnect cleanup.')
    n._react_last.clear()

    class Socket:
        accepted = False
        async def accept(self): self.accepted = True
        async def close(self, **kwargs): self.accepted = False
    async def session(ws, uid): pass
    ws_fn = extract('FastAPI/main.py', 'ws_endpoint', {
        'asyncio': asyncio, 'verify_session_token': auth.verify_session_token,
        'verify_webapp_data': auth.verify_webapp_data,
        'notifications': SimpleNamespace(ws_session=session), 'WebSocketDisconnect': type('Disconnect', (Exception,), {})})
    sock = Socket()
    await ws_fn(sock, 101, token=auth.create_session_token(101))
    assert sock.accepted
    passed('websocket_gate', 'Exact endpoint body accepts a signed identity without any account, ban or allowlist lookup; AST harness, not full ASGI.')

    from FastAPI import deps
    semaphore = asyncio.Semaphore(5)
    barrier = asyncio.Event()
    entered = 0
    class Lease:
        async def __aenter__(self):
            await semaphore.acquire()
            return None
        async def __aexit__(self, *args): semaphore.release()
    pool = SimpleNamespace(acquire=lambda: Lease())
    async def no_create(): pass
    async def request(uid):
        nonlocal entered
        async with pool.acquire():  # get_db holds its connection until response
            entered += 1
            if entered == 5: barrier.set()
            await barrier.wait()
            return await deps._is_banned_cached(uid)
    deps._BAN_CACHE.clear()
    with patch.object(deps, 'get_pool', return_value=pool), patch.object(deps, 'create_pool', no_create):
        try:
            await asyncio.wait_for(asyncio.gather(*(request(i) for i in range(1, 6))), timeout=.3)
        except asyncio.TimeoutError:
            passed('nested_pool_acquisition', 'Five cold-cache requests hold all five slots and each waits for another slot; deterministic semaphore harness.')
        else:
            raise AssertionError('Expected circular pool wait')

    sql_tree = ast.parse((ROOT / 'FastAPI/routers/dev_console/sql.py').read_text(encoding='utf-8'))
    heads = ast.literal_eval(next(n.value for n in sql_tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_READONLY_HEADS' for t in n.targets)))
    assert 'explain' in heads
    passed('sql_readonly_classification', 'EXPLAIN ANALYZE UPDATE is classified readonly by its first word; static classification proof only.')

    parts = (1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14)
    js = ''.join((ROOT / f'FastAPI/static/app.{p:02d}.js').read_text(encoding='utf-8') for p in parts)
    import re
    assert 'connectWS();' in js
    assert not re.search(r'(?:function\s+connectWS\s*\(|connectWS\s*=)', js)
    passed('missing_connectWS', 'Served JS calls connectWS but contains no function declaration or assignment; static bundle proof.')

    writes = []
    class CleanupDB:
        async def execute(self, sql, args=()):
            writes.append(sql)
            if sql.startswith('DELETE FROM inventory '):
                raise RuntimeError('injected cleanup failure')
    async def no_marriage(db, uid): return False
    async def retire(db, uid): pass
    log = SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None)
    finalize = extract('services/account_deletion.py', '_finalize', {
        '_has_active_marriage': no_marriage, 'chest_repo': SimpleNamespace(retire_account=retire), 'logger': log})
    await finalize(CleanupDB(), 101)
    assert any("status = 'finalized'" in q for q in writes)
    passed('partial_account_finalization', 'Injected inventory cleanup failure is swallowed and finalized is still written; fake DB failure injection.')

    class ReadyConn:
        async def fetchval(self, sql):
            assert "to_regnamespace" in sql
            return 'predvestnik'
    class ReadyLease:
        async def __aenter__(self): return ReadyConn()
        async def __aexit__(self, *a): pass
    ready = extract('FastAPI/main.py', 'ready', {
        'create_pool': no_create, 'get_pool': lambda: SimpleNamespace(acquire=lambda: ReadyLease()), '_log': log})
    assert await ready() == {'status': 'ready'}
    passed('namespace_only_readiness', 'Only the namespace lookup is requested; readiness never asks for required tables or migrations.')

    from datetime import datetime, timezone
    calls = []
    class GcDB:
        async def execute(self, *a): calls.append('analytics'); raise RuntimeError('injected transient failure')
    async def broken(*a): calls.append('other'); raise RuntimeError('injected transient failure')
    scope = {'_daily_gc_day': None, 'datetime': datetime, 'timezone': timezone, 'logger': log}
    gc = extract('services/scheduler.py', '_daily_gc', scope)
    with patch.dict(sys.modules, {'infrastructure.repositories.moderation': SimpleNamespace(expire_due_warns=broken), 'services.account_deletion': SimpleNamespace(daily_tick=broken)}):
        await gc(GcDB())
        count = len(calls)
        await gc(GcDB())
    assert count == 3 and len(calls) == count
    passed('daily_maintenance_retry', 'All three cleanup operations fail; the second invocation on the same day retries none.')
    if '--postgres' in sys.argv:
        # Fixed disposable audit instance only; temp tables disappear on close.
        import asyncpg
        from fastapi import HTTPException
        from infrastructure.pg_adapter import PGAdapter
        conn = await asyncpg.connect('postgresql://predvestnik_preprod@127.0.0.1:55439/predvestnik_preprod')
        try:
            await conn.execute('CREATE TEMP TABLE audit_sql_probe (v int)')
            await conn.execute('INSERT INTO audit_sql_probe VALUES (0)')
            audit_calls = []
            async def permission(*a): return 3
            async def audit_ok(*a): audit_calls.append(a)
            sql_scope = {'Depends': lambda *a: None, 'get_db': None, 'require_tg_user': None,
                         'require_console_perm': permission, '_READONLY_HEADS': heads,
                         'HTTPException': HTTPException, 'add_sys': audit_ok}
            dev_sql = extract('FastAPI/routers/dev_console/sql.py', 'dev_sql', sql_scope)
            response = await dev_sql(SimpleNamespace(query='EXPLAIN ANALYZE UPDATE audit_sql_probe SET v=1', confirm=False), PGAdapter(conn), {'id': 101})
            assert await conn.fetchval('SELECT v FROM audit_sql_probe') == 1
            assert response['logged'] is False and not audit_calls
            passed('sql_explain_postgres', 'Real local PostgreSQL changed temp row 0->1 with confirm=False and no admin log.')
            async def audit_failure(*a): raise RuntimeError('injected audit failure')
            sql_scope['add_sys'] = audit_failure
            try:
                await dev_sql(SimpleNamespace(query='UPDATE audit_sql_probe SET v=2', confirm=True), PGAdapter(conn), {'id': 101})
            except HTTPException:
                pass
            else:
                raise AssertionError('Expected failed log write')
            assert await conn.fetchval('SELECT v FROM audit_sql_probe') == 2
            passed('sql_audit_atomicity_postgres', 'Real local PostgreSQL retains mutation despite failed audit write and HTTP error.')
        finally:
            await conn.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
