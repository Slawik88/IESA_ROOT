"""Health-panel aggregator and client telemetry limits without a database.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_ops_metrics.py
"""
from __future__ import annotations

from core import ops_metrics
from core.ops_metrics import BUCKETS_MS, MAX_SERIES, OVERFLOW_NAME, Registry, Series, percentile
from services import ops_health


def test_percentiles() -> None:
    series = Series()
    for value in range(1, 101):          # 1..100 ms
        series.add(value)
    assert series.count == 100 and series.peak == 100
    assert percentile(series.buckets, 0.5, series.peak) == 50.0      # 50th value falls in the ≤50 bucket
    assert percentile(series.buckets, 0.95, series.peak) == 100.0    # ≤100 bucket, capped by the peak
    assert percentile(series.buckets, 0.99, series.peak) == 100.0
    assert percentile([0] * (len(BUCKETS_MS) + 1), 0.95) == 0.0
    slow = Series()
    slow.add(45_000)                     # beyond the last bound: the overflow bucket reports the peak
    assert percentile(slow.buckets, 0.95, slow.peak) == 45_000.0
    fast = Series()
    fast.add(0.3)
    assert percentile(fast.buckets, 0.5, fast.peak) == 0.3            # never above what was actually seen
    negative = Series()
    negative.add(-5)
    assert negative.buckets[0] == 1 and negative.total == 0


def test_windows_merge_and_restore() -> None:
    reg = Registry()
    reg.observe("http", "GET /a", 10)
    reg.count("auth_401", "bad_hash")
    first = reg.drain()
    assert reg.window.timings == {} and reg.window.counters == {}
    reg.observe("http", "GET /a", 2000)
    reg.count("auth_401", "bad_hash", 2)
    reg.restore(first)                    # a failed write puts the old window back
    merged = reg.window.timings[("http", "GET /a")]
    assert merged.count == 2 and merged.peak == 2000
    assert reg.window.counters[("auth_401", "bad_hash")] == 3


def test_overflow_is_bounded() -> None:
    reg = Registry()
    for index in range(MAX_SERIES + 500):
        reg.observe("http", f"GET /r{index}", 1)
        reg.count("http_4xx", f"GET /r{index}")
    keys = len(reg.window.timings) + len(reg.window.counters)
    assert keys <= MAX_SERIES + 2, keys
    assert reg.window.timings[("http", OVERFLOW_NAME)].count >= 500
    reg.observe("http", "x" * 500, 1)
    assert all(len(name) <= 120 for _, name in reg.window.timings)


def test_alert_thresholds() -> None:
    quiet = ops_metrics.Window()
    lag = Series()
    for _ in range(60):
        lag.add(5)
    quiet.timings[("loop_lag", "event_loop")] = lag
    quiet.counters[("http_5xx", "GET /a")] = 3
    assert ops_health.alerts_for(quiet) == []

    loud = ops_metrics.Window()
    slow = Series()
    for _ in range(60):
        slow.add(2500)
    loud.timings[("loop_lag", "event_loop")] = slow
    loud.timings[("pool_wait", "http")] = slow
    requests = Series()
    for _ in range(100):
        requests.add(10)
    loud.timings[("http", "GET /a")] = requests
    loud.counters[("http_5xx", "GET /a")] = 25
    loud.counters[("client", "js_error")] = 60
    loud.counters[("bot_error", "bot.chat.x:handle|KeyError")] = 12
    keys = [key for key, _ in ops_health.alerts_for(loud)]
    assert keys == ["loop_lag", "pool_wait", "http_5xx", "client", "bot_error"], keys

    def server(total: int, ours: int, limit: int) -> ops_metrics.Window:
        window = ops_metrics.Window()
        for name, value in (("total", total), ("ours", ours), ("limit", limit)):
            series = Series()
            series.add(value)
            window.timings[("db_server", name)] = series
        return window
    assert ops_health.alerts_for(server(10, 6, 22)) == []
    (key, text), = ops_health.alerts_for(server(20, 9, 22))
    assert key == "db_server" and "20 из 22" in text and "Предвестник — 9" in text, text
    refused = ops_metrics.Window()
    refused.counters[("db_refused", "server_full")] = 1
    assert [k for k, _ in ops_health.alerts_for(refused)] == ["db_server"]


def test_trim() -> None:
    assert ops_health._trim([3, 0, 1, 0, 0]) == [3, 0, 1]
    assert ops_health._trim([0, 0]) == [0]


def test_scrub_and_paths() -> None:
    dirty = "token=123456:ABCDEFabcdef_long https://t.me/x user 987654321 initData=query_id%3D1\nnext"
    clean = ops_health.scrub(dirty, 200)
    assert "123456:" not in clean and "https://" not in clean and "987654321" not in clean and "query_id" not in clean
    assert "\n" not in clean
    assert ops_health._route_path("/public-profile-v3/u/123456789?x=1") == "/public-profile-v3/u/:value"
    assert ops_health._route_path("/profile/me") == "/profile/me"


def _fresh_limits() -> None:
    ops_health._limits = ops_health._Limits()
    ops_health._client_buffer.clear()


def test_client_events_validation_and_limits() -> None:
    _fresh_limits()
    payload = {"sid": "abc123def4", "version": "v1", "device": "ios/phone", "user_id": 777001, "initData": "secret",
               "events": [{"type": "js_error", "message": "TypeError: x 123456789", "path": "app.12.js:345:6",
                           "screen": "/profile/me", "first_name": "Ivan", "status": True},
                          {"type": "nonsense"}, "garbage",
                          {"type": "fetch_fail", "path": "/u/5550001112/stats", "status": 401, "ms": 18000, "timeout": True}]}
    accepted, limited = ops_health.accept_client_events("1.2.3.4", payload)
    assert (accepted, limited) == (2, False)
    stored = list(ops_health._client_buffer)
    assert stored[0]["path"] == "app.12.js:345:6" and "123456789" not in stored[0]["message"]
    assert stored[0]["status"] is None                       # a bool is not a status code
    assert stored[1]["path"] == "/u/:value/stats" and stored[1]["detail"] == {"ms": 18000, "timeout": True}
    allowed_keys = {"at", "sid", "type", "version", "device", "screen", "path", "status", "message", "detail"}
    assert all(set(e) == allowed_keys for e in stored)         # extra fields (ids, names, initData) never pass
    assert "777001" not in repr(stored) and "secret" not in repr(stored) and "Ivan" not in repr(stored)

    assert ops_health.accept_client_events("1.2.3.4", {"sid": "BAD SID!", "events": [{"type": "js_error"}]}) == (0, False)

    _fresh_limits()                                           # one IP cannot exceed its minute budget
    batch = {"sid": "s0000001", "events": [{"type": "js_error", "message": str(i)} for i in range(10)]}
    total = 0
    for n in range(20):
        batch["sid"] = f"s{n:07d}"
        got, _ = ops_health.accept_client_events("5.5.5.5", batch)
        total += got
    assert total == ops_health.PER_IP_PER_MINUTE, total

    _fresh_limits()                                           # one page id cannot exceed its hourly budget
    total = 0
    for n in range(20):
        got, _ = ops_health.accept_client_events(f"10.0.0.{n}", {"sid": "samesid1", "events": batch["events"]})
        total += got
    assert total == ops_health.PER_SID_PER_HOUR, total

    _fresh_limits()                                           # many IPs together hit the global ceiling
    total = 0
    for n in range(100):
        got, _ = ops_health.accept_client_events(f"10.1.{n}.1", {"sid": f"g{n:07d}", "events": batch["events"]})
        total += got
    assert total == ops_health.GLOBAL_PER_MINUTE, total
    assert len(ops_health._client_buffer) == ops_health.GLOBAL_PER_MINUTE

    _fresh_limits()                                           # the daily storage cap keeps counting but stops storing
    ops_health._limits.roll(0)
    ops_health._limits.stored_today = ops_health.STORED_PER_DAY
    got, _ = ops_health.accept_client_events("9.9.9.9", {"sid": "daycap01", "events": [{"type": "js_error"}]})
    assert got == 1 and not ops_health._client_buffer
    _fresh_limits()


def test_handler_name() -> None:
    def helper():
        raise KeyError("player text must not leak")

    def handle_command():   # the handler is the outer frame, not the helper that raised
        helper()
    try:
        handle_command()
    except KeyError as exc:
        tb = exc.__traceback__.tb_next   # drop this test frame: aiogram calls the handler directly
        name = ops_health.handler_name(tb)
        trace = ops_health.short_trace(tb)
    assert name == "tools.test_ops_metrics:handle_command", name
    assert "player text" not in trace and "tools/test_ops_metrics.py" in trace


def main() -> None:
    for test in (test_percentiles, test_windows_merge_and_restore, test_overflow_is_bounded, test_alert_thresholds,
                 test_trim, test_scrub_and_paths, test_client_events_validation_and_limits, test_handler_name):
        test()
    print("OK: ops metrics aggregator, alerts and client telemetry limits")


if __name__ == "__main__":
    main()
