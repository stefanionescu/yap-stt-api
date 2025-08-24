#!/usr/bin/env python3
"""
Simple load/latency benchmark for Parakeet ASR HTTP API.

Measures end-to-end latency, audio processing throughput, and queue performance
for a given number of requests with configurable concurrency using HTTP POST.

Optimized for high concurrency with improved error handling, connection debugging,
and reliable HTTP/1.1 transport with proper connection pooling.

Examples (run on pod):
  python test/bench.py --n 40 --concurrency 2
  python test/bench.py --n 100 --concurrency 50 --host your-host --verbose
  python test/bench.py --n 20 --file long.mp3 --concurrency 4 --read-timeout 600

Debugging high-concurrency issues:
  python test/bench.py --n 100 --concurrency 100 --verbose --disable-retries

Host/port default to localhost:8000; override with --host/--port.
"""
import argparse
import asyncio
import os
import statistics as stats
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import httpx
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))


SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}
from utils import build_http_multipart, file_to_pcm16_mono_16k, ws_realtime_transcribe, ws_realtime_transcribe_with_ttfw, file_duration_seconds

RESULTS_DIR = Path("test/results")
ERRORS_FILE = RESULTS_DIR / "bench_errors.txt"


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


def _metrics(audio_duration_s: float, wall_s: float, ttfw_s: float = 0.0) -> Dict[str, float]:
    """Compute transcription metrics (queue wait not tracked by API)."""
    rtf = wall_s / audio_duration_s if audio_duration_s > 0 else float("inf")  # Real-time factor
    xrt = audio_duration_s / wall_s if wall_s > 0 else 0.0  # Times real-time
    throughput_min_per_min = audio_duration_s / wall_s if wall_s > 0 else 0.0  # Minutes of audio per minute of wall time
    return {
        "wall_s": wall_s,
        "audio_s": audio_duration_s,
        "rtf": rtf,
        "xrt": xrt,
        "throughput_min_per_min": throughput_min_per_min,
        "ttfw_s": ttfw_s,  # Time to first word/response
    }


def summarize(title: str, results: List[Dict[str, float]]) -> None:
    """Print summary statistics."""
    if not results:
        print(f"{title}: no results")
        return
    
    wall = [r["wall_s"] for r in results]
    audio = [r["audio_s"] for r in results]
    rtf = [r["rtf"] for r in results]
    xrt = [r["xrt"] for r in results]
    throughput = [r["throughput_min_per_min"] for r in results]
    ttfw = [r.get("ttfw_s", 0.0) for r in results]
    n = len(results)
    
    def p(v: List[float], q: float) -> float:
        k = max(0, min(len(v)-1, int(round(q*(len(v)-1)))))
        return sorted(v)[k]
    
    print(f"\n== {title} ==")
    print(f"n={n}")
    print(f"Wall s      | avg={stats.mean(wall):.4f}  p50={stats.median(wall):.4f}  p95={p(wall,0.95):.4f}")
    print(f"TTFW s      | avg={stats.mean(ttfw):.4f}  p50={stats.median(ttfw):.4f}  p95={p(ttfw,0.95):.4f}")
    print(f"Audio s     | avg={stats.mean(audio):.4f}")
    print(f"RTF         | avg={stats.mean(rtf):.4f}  p50={stats.median(rtf):.4f}  p95={p(rtf,0.95):.4f}")
    print(f"xRT         | avg={stats.mean(xrt):.4f}")
    print(f"Throughput  | avg={stats.mean(throughput):.2f} min/min")


def _split_counts(total: int, workers: int) -> List[int]:
    """Split total requests across workers."""
    base = total // workers
    rem = total % workers
    return [base + (1 if i < rem else 0) for i in range(workers)]


async def bench_http(base_url: str, file_paths: List[str], total_reqs: int, concurrency: int, use_pcm: bool, raw: bool, timestamps: bool, read_timeout_s: float, verbose: bool = False, disable_retries: bool = False) -> tuple[List[Dict[str, float]], int, int]:
    """Run HTTP benchmark limiting in-flight requests to `concurrency` without worker sharding."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Initialize errors file properly
    try:
        with open(ERRORS_FILE, "w", encoding="utf-8") as ef:
            ef.write(f"=== Benchmark Error Log Started at {datetime.utcnow().isoformat()}Z ===\n")
    except Exception as e:
        print(f"Warning: Could not initialize error log file: {e}")

    sem = asyncio.Semaphore(max(1, concurrency))
    error_lock: asyncio.Lock = asyncio.Lock()
    results: List[Dict[str, float]] = []
    rejected_total = 0
    errors_total = 0

    url = base_url.rstrip("/") + "/v1/audio/transcribe"
    file_path = file_paths[0]

    # Configure transport based on debugging options
    retries = 0 if disable_retries else 3
    # Use public httpx API only; avoid private attributes
    transport = httpx.AsyncHTTPTransport(
        retries=retries,
        http2=False,
        keepalive_expiry=60.0,
    )
    
    if verbose:
        print(f"HTTP transport config: retries={retries}, keepalive_expiry=60.0s, http2=False")
        print(f"Connection limits: keepalive={max(512, concurrency*4)}, max_conn={max(1024, concurrency*8)}")
        print(f"Timeouts: connect=30.0s, read={read_timeout_s}s, write=60.0s, pool=10.0s")
    # Scale connection limits based on concurrency, ensure sufficient headroom
    limits = httpx.Limits(
        max_keepalive_connections=max(512, concurrency*4), 
        max_connections=max(1024, concurrency*8)
    )
    timeout = httpx.Timeout(connect=30.0, read=read_timeout_s, write=60.0, pool=10.0)
    
    # Helper function to log errors reliably
    async def log_error(message: str) -> None:
        """Log error message to file and stdout, don't fail silently."""
        async with error_lock:
            error_line = f"[{datetime.utcnow().isoformat()}Z] {message}"
            if verbose:
                print(f"ERROR: {message}")  # Print to console when verbose
            try:
                with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                    ef.write(error_line + "\n")
            except Exception as log_err:
                print(f"Failed to write error to log file: {log_err}")
    
    # Request tracking for verbose mode
    completed_requests = 0

    async with httpx.AsyncClient(timeout=timeout, transport=transport, limits=limits, http2=False) as client:
        async def one_request(req_idx: int) -> None:
            nonlocal rejected_total, errors_total, completed_requests
            async with sem:
                t0 = time.time()
                if verbose:
                    print(f"Starting request {req_idx+1}/{total_reqs}")
                ttfw_s = 0.0  # Time to first word
                try:
                    fname, content, ctype = build_http_multipart(file_path, use_pcm)
                    
                    # Use streaming to detect first response bytes (time to first word)
                    if raw:
                        headers = {"content-type": ctype}
                        stream_request = client.stream("POST", url + ("?timestamps=1" if timestamps else ""), content=content, headers=headers)
                    else:
                        files = {"file": (fname, content, ctype)}
                        stream_request = client.stream("POST", url + ("?timestamps=1" if timestamps else ""), files=files)
                    
                    async with stream_request as response:
                        # Record time to first response byte
                        ttfw_s = time.time() - t0
                        
                        # Read the full response
                        response_content = await response.aread()

                    t_end = time.time()
                    wall_s = t_end - t0

                    if response.status_code == 429:
                        rejected_total += 1
                        return
                    if response.status_code != 200:
                        errors_total += 1
                        try:
                            msg = response_content.decode('utf-8', errors='replace')
                        except Exception:
                            msg = "<no body>"
                        sanitized = (msg[:300]).replace("\n", " ")
                        await log_error(f"req={req_idx+1} HTTP {response.status_code} body={sanitized}")
                        return

                    try:
                        import json
                        data = json.loads(response_content.decode('utf-8'))
                    except Exception as e:
                        await log_error(f"req={req_idx+1} JSON decode error: {str(e)[:100]}")
                        errors_total += 1
                        return

                    try:
                        audio_duration = float(data.get("duration"))
                    except Exception:
                        audio_duration = 0.0
                    if not audio_duration or audio_duration <= 0:
                        audio_duration = file_duration_seconds(file_path)
                    results.append(_metrics(audio_duration, wall_s, ttfw_s))
                    
                    # Track successful completion  
                    completed_requests += 1
                    if verbose and completed_requests % 10 == 0:
                        print(f"Completed {completed_requests} requests successfully")
                except Exception as e:
                    errors_total += 1
                    exc_text = (str(e)[:300]).replace("\n", " ")
                    await log_error(f"req={req_idx+1} EXC {type(e).__name__}: {exc_text}")
                    # Print additional debugging info for common connection issues
                    if "connection" in str(e).lower() or "timeout" in str(e).lower():
                        print(f"Connection issue detected: {type(e).__name__}: {str(e)[:200]}")

        tasks = [asyncio.create_task(one_request(i)) for i in range(total_reqs)]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results[:total_reqs], rejected_total, errors_total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--n", type=int, default=40, help="Total requests")
    ap.add_argument("--concurrency", type=int, default=10, help="Max in-flight requests")
    ap.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/ (default: mid.wav)")
    ap.add_argument("--no-pcm", action="store_true", help="Send original file (disable PCM mode) for HTTP")
    ap.add_argument("--ws", action="store_true", help="Use WebSocket realtime instead of HTTP")
    ap.add_argument("--raw", action="store_true", help="HTTP: send raw body (single-shot) instead of multipart")
    ap.add_argument("--timestamps", action="store_true", help="Request word timestamps in the same transaction (HTTP only)")
    ap.add_argument("--read-timeout", type=float, default=300.0, help="httpx read timeout seconds (increase for long audio)")
    ap.add_argument("--verbose", action="store_true", help="Enable verbose connection debugging")
    ap.add_argument("--disable-retries", action="store_true", help="Disable HTTP retries (useful for debugging)")
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
        # WS benchmark: create independent WS connections per request, distributed across workers
        async def _ws_bench() -> tuple[List[Dict[str, float]], int, int]:
            import asyncio, time
            ws_url = base_url.rstrip("/") + "/v1/realtime"
            pcm = file_to_pcm16_mono_16k(file_paths[0])
            workers = min(args.concurrency, args.n)
            counts = _split_counts(args.n, workers)
            results: List[Dict[str, float]] = []
            rejected = 0
            errors = 0

            async def _worker(i: int, cnt: int):
                nonlocal rejected, errors
                for j in range(cnt):
                    t0 = time.time()
                    try:
                        _, ttfw = await ws_realtime_transcribe_with_ttfw(ws_url, pcm)
                        wall = time.time() - t0
                        results.append(_metrics(len(pcm)/2/16000, wall, ttfw))
                    except Exception:
                        errors += 1
                        continue

            await asyncio.gather(*[asyncio.create_task(_worker(i, counts[i])) for i in range(workers)])
            return results, rejected, errors

        results, rejected, errors = asyncio.run(_ws_bench())
    else:
        results, rejected, errors = asyncio.run(bench_http(base_url, file_paths, args.n, args.concurrency, not args.no_pcm, args.raw, args.timestamps, args.read_timeout, args.verbose, args.disable_retries))
    elapsed = time.time() - t0
    
    summarize("HTTP Transcription", results)
    print(f"Rejected: {rejected}")
    print(f"Errors: {errors}")
    print(f"Total elapsed: {elapsed:.4f}s")
    
    # Additional debugging output
    if errors > 0:
        print(f"\n🔍 {errors} errors occurred. Check test/results/bench_errors.txt for details.")
        if not args.verbose:
            print("💡 Run with --verbose for real-time error output")
        print("🔧 Common fixes:")
        print("  - Try --disable-retries to see raw connection errors")
        print("  - Reduce --concurrency if connection pool exhausted")
        print("  - Increase --read-timeout for very long audio files")
    
    if results:
        total_audio = sum(r["audio_s"] for r in results)
        print(f"Total audio processed: {total_audio:.2f}s")
        print(f"Overall throughput: {total_audio/elapsed*60:.2f} sec/min = {total_audio/elapsed:.2f} min/min")


if __name__ == "__main__":
    main()
