#!/usr/bin/env python3
"""
Simple load/latency benchmark for Parakeet ASR HTTP API.

Measures end-to-end latency, audio processing throughput, and queue performance
for a given number of requests with configurable concurrency using HTTP POST.

Examples (run on pod):
  python test/bench.py --n 40 --concurrency 2
  python test/bench.py --n 100 --concurrency 3 --host your-host
  python test/bench.py --n 20 --file long.mp3 --concurrency 4

Host/port default to localhost:8000; override with --host/--port.
"""
import argparse
import asyncio
import json
import os
import random
import statistics as stats
import time
from pathlib import Path
from typing import Dict, List

import httpx
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))


SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}
from utils import build_http_multipart, file_to_pcm16_mono_16k, ws_realtime_transcribe


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


def _metrics(audio_duration_s: float, wall_s: float, queue_wait_s: float = 0.0) -> Dict[str, float]:
    """Compute transcription metrics."""
    rtf = wall_s / audio_duration_s if audio_duration_s > 0 else float("inf")  # Real-time factor
    xrt = audio_duration_s / wall_s if wall_s > 0 else 0.0  # Times real-time
    throughput_min_per_min = audio_duration_s / wall_s if wall_s > 0 else 0.0  # Minutes of audio per minute of wall time
    return {
        "wall_s": wall_s,
        "audio_s": audio_duration_s,
        "queue_wait_s": queue_wait_s,
        "rtf": rtf,
        "xrt": xrt,
        "throughput_min_per_min": throughput_min_per_min,
    }


def summarize(title: str, results: List[Dict[str, float]]) -> None:
    """Print summary statistics."""
    if not results:
        print(f"{title}: no results")
        return
    
    wall = [r["wall_s"] for r in results]
    audio = [r["audio_s"] for r in results]
    queue_wait = [r.get("queue_wait_s", 0.0) for r in results]
    rtf = [r["rtf"] for r in results]
    xrt = [r["xrt"] for r in results]
    throughput = [r["throughput_min_per_min"] for r in results]
    n = len(results)
    
    def p(v: List[float], q: float) -> float:
        k = max(0, min(len(v)-1, int(round(q*(len(v)-1)))))
        return sorted(v)[k]
    
    print(f"\n== {title} ==")
    print(f"n={n}")
    print(f"Wall s      | avg={stats.mean(wall):.4f}  p50={stats.median(wall):.4f}  p95={p(wall,0.95):.4f}")
    print(f"Audio s     | avg={stats.mean(audio):.4f}")
    print(f"Queue wait s| avg={stats.mean(queue_wait):.4f}  p95={p(queue_wait,0.95):.4f}")
    print(f"RTF         | avg={stats.mean(rtf):.4f}  p50={stats.median(rtf):.4f}  p95={p(rtf,0.95):.4f}")
    print(f"xRT         | avg={stats.mean(xrt):.4f}")
    print(f"Throughput  | avg={stats.mean(throughput):.2f} min/min")


async def _http_worker(
    base_url: str, 
    file_paths: List[str], 
    requests_count: int, 
    worker_id: int,
    use_pcm: bool,
    raw: bool
) -> Dict[str, any]:
    """HTTP worker that sends requests using the specified file."""
    results: List[Dict[str, float]] = []
    rejected = 0
    errors = 0
    
    url = base_url.rstrip("/") + "/v1/audio/transcriptions"
    file_path = file_paths[0]  # Use the single specified file
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(requests_count):
            
            t0 = time.time()
            try:
                fname, content, ctype = build_http_multipart(file_path, use_pcm)
                if raw:
                    headers = {"content-type": ctype}
                    response = await client.post(url, content=content, headers=headers)
                else:
                    files = {"file": (fname, content, ctype)}
                    response = await client.post(url, files=files)
                
                t_end = time.time()
                wall_s = t_end - t0
                
                if response.status_code == 429:
                    rejected += 1
                    print(f"    Worker {worker_id}: Request {i+1} rejected (429)")
                    continue
                elif response.status_code != 200:
                    errors += 1
                    print(f"    Worker {worker_id}: Request {i+1} error ({response.status_code})")
                    continue
                
                data = response.json()
                audio_duration = data.get("duration", 0.0)
                
                # Note: we don't get queue_wait_s from the API response in this version
                # but we could extract it from metrics logs later if needed
                results.append(_metrics(audio_duration, wall_s))
                
                if (i + 1) % 10 == 0:
                    print(f"    Worker {worker_id}: Completed {i+1}/{requests_count}")
                    
            except Exception as e:
                errors += 1
                print(f"    Worker {worker_id}: Request {i+1} exception: {e}")
    
    return {"results": results, "rejected": rejected, "errors": errors}


def _split_counts(total: int, workers: int) -> List[int]:
    """Split total requests across workers."""
    base = total // workers
    rem = total % workers
    return [base + (1 if i < rem else 0) for i in range(workers)]


async def bench_http(base_url: str, file_paths: List[str], total_reqs: int, concurrency: int, use_pcm: bool, raw: bool) -> tuple[List[Dict[str, float]], int, int]:
    """Run HTTP benchmark with configurable concurrency."""
    workers = min(concurrency, total_reqs)
    counts = _split_counts(total_reqs, workers)
    
    print(f"Starting {workers} workers with counts: {counts}")
    
    tasks = [
        asyncio.create_task(_http_worker(base_url, file_paths, counts[i], i+1, use_pcm, raw)) 
        for i in range(workers)
    ]
    
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)
    
    results: List[Dict[str, float]] = []
    rejected_total = 0
    errors_total = 0
    
    for r in results_nested:
        if isinstance(r, dict):
            results.extend(r.get("results", []))
            rejected_total += int(r.get("rejected", 0))
            errors_total += int(r.get("errors", 0))
        else:
            print(f"Worker error: {r}")
            errors_total += 1
    
    return results[:total_reqs], rejected_total, errors_total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--n", type=int, default=40, help="Total requests")
    ap.add_argument("--concurrency", type=int, default=1, help="Concurrent workers")
    ap.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/ (default: mid.wav)")
    ap.add_argument("--no-pcm", action="store_true", help="Send original file (disable PCM mode) for HTTP")
    ap.add_argument("--ws", action="store_true", help="Use WebSocket realtime instead of HTTP")
    ap.add_argument("--raw", action="store_true", help="HTTP: send raw body (single-shot) instead of multipart")
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    
    # Find the specified file
    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return
    file_paths = [file_path]
    
    mode = "WS" if args.ws else "HTTP"
    print(f"Benchmark → {mode} | n={args.n} | concurrency={args.concurrency} | host={args.host}:{args.port}")
    print(f"Using {len(file_paths)} file(s): {[os.path.basename(f) for f in file_paths]}")

    t0 = time.time()
    if args.ws:
        # WS benchmark: send one stream per request with realistic frames
        async def _ws_bench() -> tuple[List[Dict[str, float]], int, int]:
            import asyncio, time
            ws_url = base_url.rstrip("/") + "/v1/realtime"
            pcm = file_to_pcm16_mono_16k(file_paths[0])
            workers = min(args.concurrency, args.n)
            counts = [1] * workers
            results: List[Dict[str, float]] = []
            rejected = 0
            errors = 0
            async def _do(i: int):
                nonlocal rejected, errors
                t0 = time.time()
                try:
                    txt = await ws_realtime_transcribe(ws_url, pcm)
                    wall = time.time() - t0
                    results.append(_metrics(len(pcm)/2/16000, wall))
                except Exception:
                    errors += 1
            await asyncio.gather(*[asyncio.create_task(_do(i)) for i in range(workers)])
            return results, rejected, errors
        results, rejected, errors = asyncio.run(_ws_bench())
    else:
        results, rejected, errors = asyncio.run(bench_http(base_url, file_paths, args.n, args.concurrency, not args.no_pcm, args.raw))
    elapsed = time.time() - t0
    
    summarize("HTTP Transcription", results)
    print(f"Rejected: {rejected}")
    print(f"Errors: {errors}")
    print(f"Total elapsed: {elapsed:.4f}s")
    
    if results:
        total_audio = sum(r["audio_s"] for r in results)
        print(f"Total audio processed: {total_audio:.2f}s")
        print(f"Overall throughput: {total_audio/elapsed*60:.2f} sec/min = {total_audio/elapsed:.2f} min/min")


if __name__ == "__main__":
    main()
