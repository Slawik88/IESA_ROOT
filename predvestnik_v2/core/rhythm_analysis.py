"""Bounded server-observed Rhythm analysis. No seeds, runes or client timing."""
from __future__ import annotations

MAX_CHUNKS = 64


def fresh() -> dict:
    return {"version": 1, "best_streak": 0, "latency_total": 0, "samples": 0,
            "wrong": 0, "timeouts": 0, "hearts_lost": 0,
            "timing": {"early": 0, "middle": 0, "late": 0}, "chunks": {}}


def record(stats: dict | None, *, signal: int, chunk_size: int, window: int,
           correct: bool, timeout: bool = False, elapsed: int = 0,
           streak: int = 0, hearts_lost: int = 0) -> None:
    if not stats or stats.get("version") != 1:
        return  # historical/offline runs never acquire invented telemetry
    key = str(min(MAX_CHUNKS, (signal - 1) // chunk_size))
    row = stats["chunks"].setdefault(key, {"correct": 0, "wrong": 0, "timeouts": 0, "hearts_lost": 0})
    label = "correct" if correct else "timeouts" if timeout else "wrong"
    row[label] += 1
    row["hearts_lost"] += hearts_lost
    stats["hearts_lost"] += hearts_lost
    if correct:
        stats["best_streak"] = max(stats["best_streak"], streak)
        stats["latency_total"] += max(0, elapsed)
        stats["samples"] += 1
        bucket = "early" if elapsed * 3 <= window else "middle" if elapsed * 3 <= 2 * window else "late"
        stats["timing"][bucket] += 1
    else:
        stats[label] += 1


def summary(stats: dict | None, *, correct: int, mistakes: int) -> dict:
    total = correct + mistakes
    result = {"accuracy": round(100 * correct / total, 1) if total else 0,
              "signals": total, "complete": bool(stats and stats.get("version") == 1)}
    if not result["complete"]:
        return result
    result.update({"best_streak": stats["best_streak"], "wrong": stats["wrong"],
                   "timeouts": stats["timeouts"], "hearts_lost": stats["hearts_lost"],
                   "response_ms": round(stats["latency_total"] / stats["samples"]) if stats["samples"] else None,
                   "timing": dict(stats["timing"]),
                   "chunks": [{"chunk": int(k) + 1, "merged": int(k) == MAX_CHUNKS, **v}
                              for k, v in sorted(stats["chunks"].items(), key=lambda kv: int(kv[0]))]})
    if "previous_best" in stats:
        result["previous_best"] = stats["previous_best"]
    return result
