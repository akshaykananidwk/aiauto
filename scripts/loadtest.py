#!/usr/bin/env python3
"""Simple load test: hammers the API with concurrent logins + submissions.

    python scripts/loadtest.py --base http://localhost:8000 \
        --username admin --password X --requests 200 --concurrency 20

Measures p50/p95 latency and error rate for the submit + list endpoints.
For serious load testing use a dedicated tool (k6, locust); this script
gives a quick sanity check that the target of 50 users / 500 prompts a
day has plenty of headroom.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def worker(client: httpx.AsyncClient, headers: dict, results: list, n: int) -> None:
    for _ in range(n):
        start = time.perf_counter()
        try:
            r = await client.post("/api/v1/prompts", headers=headers,
                                  data={"prompt_text": "load test prompt", "wants_image": "false"})
            ok = r.status_code == 201
            if ok:
                await client.post(f"/api/v1/prompts/{r.json()['id']}/cancel", headers=headers)
            lr = await client.get("/api/v1/prompts?page_size=10", headers=headers)
            ok = ok and lr.status_code == 200
        except Exception:
            ok = False
        results.append((time.perf_counter() - start, ok))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=30) as client:
        login = await client.post("/api/v1/auth/login",
                                  json={"username": args.username, "password": args.password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        results: list[tuple[float, bool]] = []
        per_worker = max(1, args.requests // args.concurrency)
        started = time.perf_counter()
        await asyncio.gather(*[
            worker(client, headers, results, per_worker) for _ in range(args.concurrency)
        ])
        elapsed = time.perf_counter() - started

    latencies = sorted(t for t, _ in results)
    ok_count = sum(1 for _, ok in results if ok)
    print(f"requests:    {len(results)} (ok={ok_count}, errors={len(results) - ok_count})")
    print(f"total time:  {elapsed:.1f}s  ({len(results) / elapsed:.1f} req/s)")
    print(f"p50 latency: {statistics.median(latencies) * 1000:.0f} ms")
    print(f"p95 latency: {latencies[int(len(latencies) * 0.95) - 1] * 1000:.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
