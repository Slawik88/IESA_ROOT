#!/usr/bin/env python3
"""Policy/service abuse checks for the opt-in chat Echo event."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chat_echo_v1 import finale_for_counts, public_manifest, target_for_active_members  # noqa: E402
from services import chat_echo_v1 as service  # noqa: E402


assert [target_for_active_members(n) for n in (0, 3, 10, 1000)] == [3, 3, 4, 20]
assert finale_for_counts({"bell": 2, "tide": 1}) == "bell"
assert finale_for_counts({"bell": 1, "tide": 1, "silence": 1}) == "balanced"
assert public_manifest()["economic_reward"] is None
assert public_manifest()["admin_opt_in_required"] is True


class Connection:
    @asynccontextmanager
    async def transaction(self): yield


class DB: connection = Connection()


class Events:
    def __init__(self): self.names = []
    async def record_event(self, *args, **kwargs): self.names.append(kwargs["event_name"])


class Repo:
    def __init__(self):
        self.enabled = True; self.event = None; self.snapshot = set(); self.contrib = {}
    async def lock_chat(self, *_): return None
    async def opt_in_enabled(self, *_): return self.enabled
    async def expire_overdue(self, *_): return None
    async def recover_stale_creating(self, *_): return None
    async def open_event(self, *_):
        return dict(self.event) if self.event and self.event["status"] in {"creating", "active"} else None
    async def active_event(self, *_):
        return dict(self.event) if self.event and self.event["status"] == "active" else None
    async def latest_started_at(self, *_): return None
    async def create_event(self, _db, **values):
        now=datetime.now(timezone.utc)
        self.snapshot=set(values.pop("eligible_user_ids")); values.pop("duration_hours")
        self.event={"id":1,"status":"creating","starts_at":now,"ends_at":now+timedelta(hours=6),"message_id":None,"finale_id":None,**values}
        return dict(self.event)
    async def bind_message(self, _db, _eid, _cid, mid, _hours):
        self.event.update(status="active",message_id=mid); return dict(self.event)
    async def cancel_unpublished(self, *_): self.event["status"]="failed"
    async def lock_event(self, _db, eid, cid):
        return dict(self.event) if self.event and self.event["id"]==eid and self.event["chat_id"]==cid else None
    async def existing_contribution(self, _db, eid, uid): return self.contrib.get((eid,uid))
    async def in_snapshot(self, _db, _eid, uid): return uid in self.snapshot
    async def insert_contribution(self, _db, eid, uid, symbol):
        if (eid,uid) in self.contrib: return False
        self.contrib[(eid,uid)]=symbol; return True
    async def counts(self, _db, eid):
        out={}
        for (event_id,_),symbol in self.contrib.items():
            if event_id==eid: out[symbol]=out.get(symbol,0)+1
        return out
    async def complete(self, _db, _eid, finale):
        if self.event["status"]!="active": return None
        self.event.update(status="completed",finale_id=finale); return dict(self.event)
    async def set_enabled(self, _db, _cid, enabled):
        self.enabled=enabled
        if not enabled and self.event and self.event["status"] in {"creating","active"}:
            self.event["status"]="cancelled"; return dict(self.event)
        return None


async def main():
    repo, events = Repo(), Events(); old_repo, old_events = service.repo, service.events
    service.repo, service.events = repo, events
    try:
        view=await service.start(DB(),chat_id=-10,admin_id=7,eligible_user_ids=[1,2,3])
        assert view["status"]=="creating" and "chat_echo_started" not in events.names
        await service.bind_message(DB(),1,-10,99)
        assert events.names.count("chat_echo_started")==1
        try: await service.contribute(DB(),event_id=1,chat_id=-11,user_id=1,symbol_id="bell")
        except service.EchoError: pass
        else: raise AssertionError("cross-chat callback accepted")
        try: await service.contribute(DB(),event_id=1,chat_id=-10,user_id=8,symbol_id="bell")
        except service.EchoForbidden: pass
        else: raise AssertionError("non-snapshot user accepted")
        first=await service.contribute(DB(),event_id=1,chat_id=-10,user_id=1,symbol_id="bell")
        replay=await service.contribute(DB(),event_id=1,chat_id=-10,user_id=1,symbol_id="bell")
        assert first["total"]==1 and replay["idempotent_replay"]
        try: await service.contribute(DB(),event_id=1,chat_id=-10,user_id=1,symbol_id="tide")
        except service.EchoConflict: pass
        else: raise AssertionError("symbol changed after contribution")
        await service.contribute(DB(),event_id=1,chat_id=-10,user_id=2,symbol_id="tide")
        done=await service.contribute(DB(),event_id=1,chat_id=-10,user_id=3,symbol_id="silence")
        assert done["status"]=="completed" and done["finale_id"]=="balanced"
        assert events.names.count("chat_echo_completed")==1
        try: await service.contribute(DB(),event_id=1,chat_id=-10,user_id=3,symbol_id="silence")
        except service.EchoConflict: pass
        else: raise AssertionError("completed event accepted another callback")
    finally:
        service.repo, service.events = old_repo, old_events


asyncio.run(main())
print("OK: chat Echo is opt-in, snapshot-bound, cross-chat safe and exactly-once")
