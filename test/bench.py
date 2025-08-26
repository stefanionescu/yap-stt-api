#!/usr/bin/env python3
"""
Benchmark WebSocket streaming (sherpa-onnx) for FastConformer CTC.

Streams PCM16@16k from audio files in chunks to simulate realtime voice.
Measures latency (wall), time-to-first-word, and throughput under concurrency.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import statistics as stats
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import websockets  # pip install websockets
from utils import file_to_pcm16_mono_16k, file_duration_seconds

SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}
RESULTS_DIR = Path("test/results")
ERRORS_FILE = RESULTS_DIR / "bench_errors.txt"


def find_sample_files() -> List[str]:
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
    target = Path(SAMPLES_DIR) / filename
    if target.exists() and target.suffix.lower() in EXTS:
        return str(target)
    return None


def _metrics(audio_duration_s: float, wall_s: float, ttfw_s: float | None = None) -> Dict[str, float]:
    rtf = wall_s / audio_duration_s if audio_duration_s > 0 else float("inf")
    xrt = (audio_duration_s / wall_s) if wall_s > 0 else 0.0
    throughput_min_per_min = (audio_duration_s / wall_s) if wall_s > 0 else 0.0
    return {
        "wall_s": wall_s,
        "audio_s": audio_duration_s,
        "rtf": rtf,
        "xrt": xrt,
        "throughput_min_per_min": throughput_min_per_min,
        **({"ttfw_s": float(ttfw_s)} if ttfw_s is not None else {}),
    }


def summarize(title: str, results: List[Dict[str, float]]) -> None:
    if not results:
        print(f"{title}: no results")
        return
    def p(v: List[float], q: float) -> float:
        k = max(0, min(len(v)-1, int(round(q*(len(v)-1)))))
        return sorted(v)[k]

    wall = [r["wall_s"] for r in results]
    audio = [r["audio_s"] for r in results]
    rtf = [r["rtf"] for r in results]
    xrt = [r["xrt"] for r in results]
    throughput = [r["throughput_min_per_min"] for r in results]
    ttfw_vals = [r["ttfw_s"] for r in results if "ttfw_s" in r]
    fin = [r.get("finalize_ms", 0.0) for r in results if r.get("finalize_ms", 0.0) > 0]
    gaps = [r.get("avg_partial_gap_ms", 0.0) for r in results if r.get("avg_partial_gap_ms", 0.0) > 0]

    print(f"\n== {title} ==")
    print(f"n={len(results)}")
    print(f"Wall s      | avg={stats.mean(wall):.4f}  p50={stats.median(wall):.4f}  p95={p(wall,0.95):.4f}")
    if ttfw_vals:
        print(f"TTFW s      | avg={stats.mean(ttfw_vals):.4f}  p50={stats.median(ttfw_vals):.4f}  p95={p(ttfw_vals,0.95):.4f}")
    print(f"Audio s     | avg={stats.mean(audio):.4f}")
    print(f"RTF         | avg={stats.mean(rtf):.4f}  p50={stats.median(rtf):.4f}  p95={p(rtf,0.95):.4f}")
    print(f"xRT         | avg={stats.mean(xrt):.4f}")
    print(f"Throughput  | avg={stats.mean(throughput):.2f} min/min")
    if fin:
        print(f"Finalize ms | avg={stats.mean(fin):.1f}  p50={p(fin,0.50):.1f}  p95={p(fin,0.95):.1f}")
    if gaps:
        print(f"Partial gap | avg={stats.mean(gaps):.1f}  p50={p(gaps,0.50):.1f}  p95={p(gaps,0.95):.1f}")


def _ws_url(server: str, secure: bool) -> str:
    if server.startswith("ws://") or server.startswith("wss://"):
        return server
    scheme = "wss" if secure else "ws"
    return f"{scheme}://{server}"


async def _ws_one(server: str, pcm_bytes: bytes, audio_seconds: float, chunk_ms: int, mode: str) -> Dict[str, float]:
    """
    One session over WebSocket. For 'stream', sleeps per chunk to simulate realtime.
    For 'oneshot', sends with no sleeps.
    """
    url = _ws_url(server, secure=False)
    t0 = time.perf_counter()
    ttfw = None
    partial_ts: List[float] = []
    last_chunk_sent_ts = 0.0
    final_recv_ts = 0.0
    last_text = ""
    final_text = ""

    bytes_per_ms = int(16000 * 2 / 1000)
    step = max(1, int(chunk_ms)) * bytes_per_ms

    async with websockets.connect(url, max_size=None) as ws:
        # receiver: JSON partials {"text": "...", "segment": n}; final sentinel is "Done!"
        async def receiver():
            nonlocal ttfw, final_recv_ts, final_text, last_text
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    # server shouldn't send binary; ignore
                    continue
                if msg == "Done!":
                    final_recv_ts = time.perf_counter()
                    return
                try:
                    j = json.loads(msg)
                    txt = j.get("text", "")
                except Exception:
                    continue
                now = time.perf_counter()
                if txt:
                    if ttfw is None:
                        ttfw = now - t0
                    # Only count when it changes to avoid 100s of dup prints
                    if txt != last_text:
                        partial_ts.append(now - t0)
                        last_text = txt
                    final_text = txt  # keep last as final
            # socket closed without Done!
            final_recv_ts = time.perf_counter()

        recv_task = asyncio.create_task(receiver())

        # sender: stream audio
        if mode == "stream":
            # realistic streaming
            for i in range(0, len(pcm_bytes), step):
                await ws.send(pcm_bytes[i:i+step])
                last_chunk_sent_ts = time.perf_counter()
                await asyncio.sleep(chunk_ms / 1000.0)
        else:
            # oneshot: no sleeps; still chunk to avoid huge frames
            big = 64000  # ~2 sec per frame; adjust if you like
            for i in range(0, len(pcm_bytes), big):
                await ws.send(pcm_bytes[i:i+big])
                last_chunk_sent_ts = time.perf_counter()

        # signal end
        await ws.send("Done")
        await recv_task

    wall = time.perf_counter() - t0
    metrics = _metrics(audio_seconds, wall, ttfw)
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0

    metrics.update({
        "partials": float(len(partial_ts)),
        "avg_partial_gap_ms": float(avg_gap_ms),
        "final_len_chars": float(len(final_text)),
        "finalize_ms": float(((final_recv_ts - last_chunk_sent_ts) * 1000.0) if (final_recv_ts and last_chunk_sent_ts) else 0.0),
        "mode": mode,
    })
    return metrics


async def bench_ws(server: str, file_path: str, total_reqs: int, concurrency: int, chunk_ms: int, mode: str) -> Tuple[List[Dict[str, float]], int, int]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(ERRORS_FILE, "w", encoding="utf-8") as ef:
            ef.write(f"=== Benchmark Error Log Started at {datetime.utcnow().isoformat()}Z ===\n")
    except Exception:
        pass

    sem = asyncio.Semaphore(max(1, concurrency))
    results: List[Dict[str, float]] = []
    rejected = 0
    errors_total = 0

    pcm = file_to_pcm16_mono_16k(file_path)
    audio_seconds = file_duration_seconds(file_path)

    async def worker(req_idx: int):
        nonlocal errors_total
        async with sem:
            try:
                r = await _ws_one(server, pcm, audio_seconds, chunk_ms, mode)
                results.append(r)
            except Exception as e:
                errors_total += 1
                try:
                    with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                        ef.write(f"{datetime.utcnow().isoformat()}Z idx={req_idx} err={e}\n")
                except Exception:
                    pass

    tasks = [asyncio.create_task(worker(i)) for i in range(total_reqs)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return results[:total_reqs], rejected, errors_total


def main() -> None:
    ap = argparse.ArgumentParser(description="WebSocket streaming benchmark (sherpa-onnx)")
    ap.add_argument("--server", default="localhost:8000", help="host:port or ws://host:port")
    ap.add_argument("--secure", action="store_true", help="(ignored unless you run wss)")
    ap.add_argument("--n", type=int, default=20, help="Total sessions")
    ap.add_argument("--concurrency", type=int, default=5, help="Max concurrent sessions")
    ap.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    ap.add_argument("--chunk-ms", type=int, default=120, help="Chunk size in ms for streaming")
    ap.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot")
    args = ap.parse_args()

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    print(f"Benchmark → WS ({args.mode}) | n={args.n} | concurrency={args.concurrency} | server={args.server}")
    print(f"File: {os.path.basename(file_path)}")

    t0 = time.time()
    results, rejected, errors = asyncio.run(
        bench_ws(args.server, file_path, args.n, args.concurrency, args.chunk_ms, args.mode)
    )
    elapsed = time.time() - t0

    summarize("WebSocket Streaming", results)
    print(f"Rejected: {rejected}")
    print(f"Errors: {errors}")
    print(f"Total elapsed: {elapsed:.4f}s")
    if results:
        total_audio = sum(r["audio_s"] for r in results)
        print(f"Total audio processed: {total_audio:.2f}s")
        print(f"Overall throughput: {total_audio/elapsed*60:.2f} sec/min = {total_audio/elapsed:.2f} min/min")

    # per-stream JSONL (overwrite each run)
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        metrics_path = RESULTS_DIR / "bench_metrics.jsonl"
        with open(metrics_path, "w", encoding="utf-8") as f:
            for rec in results:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"Saved per-stream metrics to {metrics_path}")
    except Exception as e:
        print(f"Warning: could not write metrics JSONL: {e}")


if __name__ == "__main__":
    main()
