"""Server-side latency of a light endpoint through the full FastAPI middleware stack.

Measures the cost the app itself adds per request (no network, no Telegram), so
instrumentation overhead can be compared before/after a change:

    BOT_TOKEN=1:x PYTHONPATH=. DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod \
        python tools/bench_http_overhead.py [--requests 10000] [--path /api/health]

Prints p50/p95/p99 in milliseconds. /api/health never touches the database; DATABASE_URL is only
required because importing the app reads its configuration.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time


async def _run(path: str, total: int) -> list[float]:
    import httpx
    from FastAPI.main import app

    samples: list[float] = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bench") as client:
        for _ in range(min(500, total)):   # warm-up: imports, first-call caches
            await client.get(path)
        for _ in range(total):
            started = time.perf_counter()
            response = await client.get(path)
            samples.append((time.perf_counter() - started) * 1000)
            if response.status_code != 200:
                raise SystemExit(f"{path} answered {response.status_code}")
    return samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=10_000)
    parser.add_argument("--path", default="/api/health")
    args = parser.parse_args()
    samples = sorted(asyncio.run(_run(args.path, args.requests)))
    pick = lambda q: samples[min(len(samples) - 1, int(q * len(samples)))]
    print(f"{args.path} x{len(samples)}: p50={pick(0.50):.3f} ms  p95={pick(0.95):.3f} ms  "
          f"p99={pick(0.99):.3f} ms  mean={statistics.fmean(samples):.3f} ms")


if __name__ == "__main__":
    main()
