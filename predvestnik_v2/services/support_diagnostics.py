"""Bounded, safe per-process server breadcrumbs; never raw logs or response bodies."""
from collections import deque
import time

from core import support_reports as rules

MAX_SERVER_EVENTS = 10000
MAX_REPORT_SERVER_EVENTS = 300


class RecentDiagnostics:
    def __init__(self):
        self.events = deque(maxlen=MAX_SERVER_EVENTS)
        self.minutes = {}

    def record(self, user_id: int, kind: str, data: dict) -> None:
        now = time.time()
        while self.events and self.events[0][0] < now-rules.WINDOW_SECONDS:
            self.events.popleft()
        safe = rules.event_data(data)
        if user_id and kind in rules.EVENT_KINDS:
            self.events.append((now,int(user_id),{"at":int(now*1000),"kind":kind,"data":safe}))
        if kind in {"request","avatar"}:
            minute = int(now//60)
            bucket = self.minutes.setdefault(minute,{"requests":0,"errors_5xx":0,"auth_401":0,"avatar_miss":0,"slow":0})
            if kind == "request":
                bucket["requests"] += 1
                bucket["errors_5xx"] += int(safe.get("status",0) >= 500)
                bucket["auth_401"] += int(safe.get("status") == 401)
                bucket["slow"] += int(safe.get("duration_ms",0) >= 3000)
            elif safe.get("stage") == "final" and safe.get("outcome") == "empty":
                bucket["avatar_miss"] += 1
            self.minutes = {k:v for k,v in self.minutes.items() if k >= minute-59}

    def for_user(self, user_id: int) -> dict:
        since = time.time()-rules.WINDOW_SECONDS
        items = [event for at,uid,event in self.events if at >= since and uid == int(user_id)]
        return {"scope":"current_process","window_seconds":rules.WINDOW_SECONDS,
                "events":items[-MAX_REPORT_SERVER_EVENTS:],"truncated":len(items)>MAX_REPORT_SERVER_EVENTS}

    def overview(self) -> dict:
        since = int(time.time()//60)-59
        return {"scope":"current_process","window_seconds":rules.WINDOW_SECONDS,
                "totals":{key:sum(v[key] for m,v in self.minutes.items() if m>=since)
                          for key in ("requests","errors_5xx","auth_401","avatar_miss","slow")}}


recent = RecentDiagnostics()
