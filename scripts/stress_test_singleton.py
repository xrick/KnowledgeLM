#!/usr/bin/env python3
"""
Stress Test Script for Singleton Connection Pattern

This script tests the SkillMetadataProvider's singleton connection
by making concurrent requests to the /api/v1/skills/tree endpoint.

Usage:
    python scripts/stress_test_singleton.py [num_requests]

    Default: 100 concurrent requests
"""

import asyncio
import aiohttp
import time
import sys
from typing import List, Tuple


async def make_request(session: aiohttp.ClientSession, url: str, request_id: int) -> Tuple[int, float, str]:
    """
    Make a single HTTP request and return results.

    Returns:
        Tuple of (request_id, response_time_ms, status)
    """
    start = time.perf_counter()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
            await response.json()
            elapsed = (time.perf_counter() - start) * 1000  # ms
            return (request_id, elapsed, f"OK ({response.status})")
    except asyncio.TimeoutError:
        elapsed = (time.perf_counter() - start) * 1000
        return (request_id, elapsed, "TIMEOUT")
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return (request_id, elapsed, f"ERROR: {str(e)[:50]}")


async def run_stress_test(num_requests: int = 100) -> None:
    """
    Run concurrent stress test.
    """
    url = "http://localhost:8082/api/v1/skills/tree"

    print(f"\n{'='*60}")
    print(f"🚀 Singleton Connection Stress Test")
    print(f"{'='*60}")
    print(f"Target URL: {url}")
    print(f"Concurrent Requests: {num_requests}")
    print(f"{'='*60}\n")

    # Create session with connection pool
    connector = aiohttp.TCPConnector(limit=200)  # Allow many connections
    async with aiohttp.ClientSession(connector=connector) as session:

        # Start timer
        total_start = time.perf_counter()

        # Create all tasks
        tasks = [
            make_request(session, url, i)
            for i in range(num_requests)
        ]

        # Run all requests concurrently
        print(f"⏳ Sending {num_requests} concurrent requests...")
        results = await asyncio.gather(*tasks)

        # Calculate total time
        total_elapsed = time.perf_counter() - total_start

    # Analyze results
    success_count = sum(1 for _, _, status in results if "OK" in status)
    timeout_count = sum(1 for _, _, status in results if "TIMEOUT" in status)
    error_count = sum(1 for _, _, status in results if "ERROR" in status)

    response_times = [t for _, t, status in results if "OK" in status]

    print(f"\n{'='*60}")
    print(f"📊 Results Summary")
    print(f"{'='*60}")
    print(f"Total Time:      {total_elapsed:.2f} seconds")
    print(f"Requests/second: {num_requests/total_elapsed:.1f}")
    print(f"")
    print(f"✅ Success:  {success_count:4d} ({success_count/num_requests*100:.1f}%)")
    print(f"⏱️  Timeout:  {timeout_count:4d} ({timeout_count/num_requests*100:.1f}%)")
    print(f"❌ Error:    {error_count:4d} ({error_count/num_requests*100:.1f}%)")

    if response_times:
        print(f"\n📈 Response Time Statistics (successful requests):")
        print(f"   Min:     {min(response_times):8.1f} ms")
        print(f"   Max:     {max(response_times):8.1f} ms")
        print(f"   Avg:     {sum(response_times)/len(response_times):8.1f} ms")

        # Percentiles
        sorted_times = sorted(response_times)
        p50 = sorted_times[len(sorted_times)//2]
        p95 = sorted_times[int(len(sorted_times)*0.95)]
        p99 = sorted_times[int(len(sorted_times)*0.99)] if len(sorted_times) >= 100 else sorted_times[-1]
        print(f"   P50:     {p50:8.1f} ms")
        print(f"   P95:     {p95:8.1f} ms")
        print(f"   P99:     {p99:8.1f} ms")

    print(f"\n{'='*60}")

    # Final verdict
    if success_count == num_requests:
        print(f"🎉 TEST PASSED: All {num_requests} requests successful!")
    elif success_count >= num_requests * 0.95:
        print(f"✅ TEST MOSTLY PASSED: {success_count}/{num_requests} requests successful")
    else:
        print(f"❌ TEST FAILED: Only {success_count}/{num_requests} requests successful")

    print(f"{'='*60}\n")

    # Show any errors
    if timeout_count > 0 or error_count > 0:
        print("❗ Failed Requests:")
        for req_id, elapsed, status in results:
            if "OK" not in status:
                print(f"   Request {req_id}: {status} ({elapsed:.1f}ms)")


if __name__ == "__main__":
    num_requests = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    asyncio.run(run_stress_test(num_requests))
