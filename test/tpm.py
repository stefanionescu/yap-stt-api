#!/usr/bin/env python3
"""
Transactions Per Minute (TPM) benchmark for Parakeet ASR HTTP API.

Maintains constant concurrency by immediately sending a new request when one completes.
Runs for exactly 60 seconds and reports total transactions processed.

Examples (run on pod):
  python test/tpm.py --concurrency 6
  python test/tpm.py --concurrency 12 --file long.mp3
  python test/tpm.py --concurrency 4 --duration 120  # 2 minutes

Host/port default to localhost:8000; override with --host/--port.
"""
import argparse
import asyncio
import os
import random
import statistics as stats
import time
from pathlib import Path
from typing import Dict, List

import httpx


SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}


def find_sample_files() -> List[str]:
    """Find all audio files in samples/ directory."""
    p = Path(SAMPLES_DIR)
    if not p.exists():
        return []
    files = []
    for root, _, filenames in os.walk(p):
        for f in filenames:
            if Path(f).suffix.lower() in EXTS:
                files.append(str(Path(root) / f))
    return files


def find_sample_by_name(filename: str) -> str | None:
    """Find specific file in samples/ directory."""
    target = Path(SAMPLES_DIR) / filename
    if target.exists() and target.suffix.lower() in EXTS:
        return str(target)
    return None


async def _tpm_worker(
    worker_id: int,
    base_url: str,
    file_paths: List[str],
    duration_s: float,
    results: List[Dict[str, any]],
    stats_lock: asyncio.Lock
) -> None:
    """Worker that continuously sends requests for duration_s seconds."""
    url = base_url.rstrip("/") + "/v1/transcribe"
    start_time = time.time()
    completed = 0
    rejected = 0
    errors = 0
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        while time.time() - start_time < duration_s:
            # Pick random file for variety
            file_path = random.choice(file_paths)
            
            t0 = time.time()
            try:
                with open(file_path, "rb") as f:
                    files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
                    response = await client.post(url, files=files)
                
                t_end = time.time()
                wall_s = t_end - t0
                
                if response.status_code == 429:
                    rejected += 1
                    continue
                elif response.status_code != 200:
                    errors += 1
                    continue
                
                data = response.json()
                audio_duration = data.get("duration", 0.0)
                
                async with stats_lock:
                    results.append({
                        "worker_id": worker_id,
                        "wall_s": wall_s,
                        "audio_s": audio_duration,
                        "file": os.path.basename(file_path),
                        "timestamp": t_end,
                    })
                
                completed += 1
                
                # Brief status every 10 completions
                if completed % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed * 60  # per minute
                    print(f"    Worker {worker_id}: {completed} done, {rate:.1f}/min, {rejected} rejected, {errors} errors")
                    
            except Exception as e:
                errors += 1
                # Don't spam on errors, just continue
                continue
    
    elapsed = time.time() - start_time
    rate = completed / elapsed * 60 if elapsed > 0 else 0
    print(f"Worker {worker_id} final: {completed} completed, {rate:.1f}/min, {rejected} rejected, {errors} errors")


async def run_tpm_test(base_url: str, file_paths: List[str], concurrency: int, duration_s: float) -> List[Dict[str, any]]:
    """Run TPM test with constant concurrency for duration_s seconds."""
    results: List[Dict[str, any]] = []
    stats_lock = asyncio.Lock()
    
    print(f"Starting {concurrency} workers for {duration_s}s...")
    
    # Start all workers
    tasks = [
        asyncio.create_task(_tpm_worker(i+1, base_url, file_paths, duration_s, results, stats_lock))
        for i in range(concurrency)
    ]
    
    # Wait for all to complete
    await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--concurrency", type=int, default=6, help="Concurrent workers")
    ap.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    ap.add_argument("--file", type=str, default="", help="Specific file from samples/ (default: use all)")
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    
    # Determine which files to use
    if args.file:
        file_path = find_sample_by_name(args.file)
        if not file_path:
            print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
            return
        file_paths = [file_path]
    else:
        file_paths = find_sample_files()
        if not file_paths:
            print(f"No audio files found in {SAMPLES_DIR}/")
            return
    
    print(f"TPM Test → HTTP | concurrency={args.concurrency} | duration={args.duration}s | host={args.host}:{args.port}")
    print(f"Using {len(file_paths)} file(s): {[os.path.basename(f) for f in file_paths]}")

    t0 = time.time()
    results = asyncio.run(run_tpm_test(base_url, file_paths, args.concurrency, args.duration))
    elapsed = time.time() - t0
    
    if results:
        total_completed = len(results)
        total_audio = sum(r["audio_s"] for r in results)
        wall_times = [r["wall_s"] for r in results]
        
        print(f"\n== TPM Results ==")
        print(f"Total completed: {total_completed}")
        print(f"Rate: {total_completed / elapsed * 60:.1f} transactions/minute")
        print(f"Total audio processed: {total_audio:.2f}s")
        print(f"Audio throughput: {total_audio / elapsed:.2f}x real-time")
        print(f"Avg latency: {stats.mean(wall_times):.4f}s")
        print(f"P95 latency: {sorted(wall_times)[int(0.95 * len(wall_times))]:.4f}s")
        print(f"Test duration: {elapsed:.2f}s")
    else:
        print("No successful transactions completed")


if __name__ == "__main__":
    main()
