#!/usr/bin/env python3
"""
Benchmark gRPC streaming (Riva-compatible) for Parakeet ASR.

Streams PCM16@16k from audio files in chunks to simulate realtime voice.
Measures latency (wall), time-to-first-word, and throughput under concurrency.
"""
import argparse
import asyncio
import os
import statistics as stats
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import riva.client  # type: ignore
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))


SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}
from utils import file_to_pcm16_mono_16k, file_duration_seconds

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
    xrt = audio_duration_s / wall_s if wall_s > 0 else 0.0
    throughput_min_per_min = audio_duration_s / wall_s if wall_s > 0 else 0.0
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
    wall = [r["wall_s"] for r in results]
    audio = [r["audio_s"] for r in results]
    rtf = [r["rtf"] for r in results]
    xrt = [r["xrt"] for r in results]
    throughput = [r["throughput_min_per_min"] for r in results]
    ttfw_vals = [r["ttfw_s"] for r in results if "ttfw_s" in r]
    n = len(results)
    def p(v: List[float], q: float) -> float:
        k = max(0, min(len(v)-1, int(round(q*(len(v)-1)))))
        return sorted(v)[k]
    print(f"\n== {title} ==")
    print(f"n={n}")
    print(f"Wall s      | avg={stats.mean(wall):.4f}  p50={stats.median(wall):.4f}  p95={p(wall,0.95):.4f}")
    if ttfw_vals:
        print(f"TTFW s      | avg={stats.mean(ttfw_vals):.4f}  p50={stats.median(ttfw_vals):.4f}  p95={p(ttfw_vals,0.95):.4f}")
    print(f"Audio s     | avg={stats.mean(audio):.4f}")
    print(f"RTF         | avg={stats.mean(rtf):.4f}  p50={stats.median(rtf):.4f}  p95={p(rtf,0.95):.4f}")
    print(f"xRT         | avg={stats.mean(xrt):.4f}")
    print(f"Throughput  | avg={stats.mean(throughput):.2f} min/min")


def one_stream(server: str, secure: bool, pcm_bytes: bytes, audio_seconds: float, chunk_ms: int) -> Dict[str, float]:
    auth = riva.client.Auth(ssl_cert=None, use_ssl=bool(secure), uri=server)
    asr = riva.client.ASRService(auth)
    cfg = riva.client.RecognitionConfig(
        encoding=riva.client.AudioEncoding.LINEAR_PCM,
        sample_rate_hertz=16000,
        language_code="en-US",
        max_alternatives=1,
        enable_automatic_punctuation=False,
    )
    scfg = riva.client.StreamingRecognitionConfig(config=cfg, interim_results=True)

    bytes_per_ms = int(16000 * 2 / 1000)
    step = max(1, int(chunk_ms)) * bytes_per_ms

    last_chunk_sent_ts = 0.0

    def audio_iter():
        nonlocal last_chunk_sent_ts
        yield riva.client.StreamingRecognizeRequest(streaming_config=scfg)
        import time as _t
        for i in range(0, len(pcm_bytes), step):
            yield riva.client.StreamingRecognizeRequest(audio_content=pcm_bytes[i : i + step])
            last_chunk_sent_ts = _t.perf_counter() if hasattr(_t, "perf_counter") else _t.time()
            _t.sleep(max(0.0, chunk_ms / 1000.0))

    t0 = time.perf_counter()
    got_first = False
    ttfw = 0.0
    partial_ts: list[float] = []
    partials_count = 0
    final_len = 0
    final_recv_ts = 0.0
    for resp in asr.streaming_response_generator(audio_chunks=audio_iter(), streaming_config=scfg):
        for r in resp.results:
            if not r.alternatives:
                continue
            alt = r.alternatives[0]
            if not r.is_final and alt.transcript:
                partials_count += 1
                now = time.perf_counter()
                partial_ts.append(now - t0)
                if not got_first:
                    ttfw = now - t0
                    got_first = True
            elif r.is_final:
                final_len = len(alt.transcript or "")
                final_recv_ts = time.perf_counter()
    wall = time.perf_counter() - t0
    metrics = _metrics(audio_seconds, wall, ttfw if got_first else None)
    # Derive partial cadence metrics
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0
    metrics.update({
        "partials": float(partials_count),
        "avg_partial_gap_ms": float(avg_gap_ms),
        "final_len_chars": float(final_len),
        "finalize_ms": float(((final_recv_ts - last_chunk_sent_ts) * 1000.0) if (final_recv_ts and last_chunk_sent_ts) else 0.0),
    })
    return metrics


async def bench_grpc(server: str, secure: bool, file_path: str, total_reqs: int, concurrency: int, chunk_ms: int) -> tuple[List[Dict[str, float]], int, int]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(ERRORS_FILE, "w", encoding="utf-8") as ef:
            ef.write(f"=== Benchmark Error Log Started at {datetime.utcnow().isoformat()}Z ===\n")
    except Exception:
        pass

    sem = asyncio.Semaphore(max(1, concurrency))
    results: List[Dict[str, float]] = []
    errors_total = 0

    pcm = file_to_pcm16_mono_16k(file_path)
    audio_seconds = file_duration_seconds(file_path)

    async def worker(req_idx: int):
        nonlocal errors_total
        async with sem:
            try:
                res = await asyncio.to_thread(one_stream, server, secure, pcm, audio_seconds, chunk_ms)
                results.append(res)
            except Exception:
                errors_total += 1

    tasks = [asyncio.create_task(worker(i)) for i in range(total_reqs)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return results[:total_reqs], 0, errors_total


def main() -> None:
    ap = argparse.ArgumentParser(description="gRPC streaming benchmark")
    ap.add_argument("--server", default="localhost:8000")
    ap.add_argument("--secure", action="store_true")
    ap.add_argument("--n", type=int, default=20, help="Total streams")
    ap.add_argument("--concurrency", type=int, default=5, help="Max concurrent streams")
    ap.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    ap.add_argument("--chunk-ms", type=int, default=50, help="Chunk size in ms for streaming")
    args = ap.parse_args()

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    print(f"Benchmark → gRPC | n={args.n} | concurrency={args.concurrency} | server={args.server}")
    print(f"File: {os.path.basename(file_path)}")

    t0 = time.time()
    results, rejected, errors = asyncio.run(bench_grpc(args.server, args.secure, file_path, args.n, args.concurrency, args.chunk_ms))
    elapsed = time.time() - t0

    summarize("gRPC Streaming", results)
    print(f"Rejected: {rejected}")
    print(f"Errors: {errors}")
    print(f"Total elapsed: {elapsed:.4f}s")
    if results:
        total_audio = sum(r["audio_s"] for r in results)
        print(f"Total audio processed: {total_audio:.2f}s")
        print(f"Overall throughput: {total_audio/elapsed*60:.2f} sec/min = {total_audio/elapsed:.2f} min/min")


if __name__ == "__main__":
    main()
