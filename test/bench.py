#!/usr/bin/env python3
"""
Benchmark WebSocket streaming for Yap ASR server.

Streams PCM16@24k from audio files in JSON frames to simulate realtime voice.
Measures latency (wall), time-to-first-word, and throughput under concurrency.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import json
import os
import statistics as stats
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import websockets

from utils import (
    file_to_pcm16_mono_24k, file_duration_seconds, SAMPLES_DIR, EXTS,
    find_sample_files, find_sample_by_name, ws_url, append_auth_query,
    AudioStreamer, BenchMessageHandler
)

class CapacityRejected(Exception):
    pass


RESULTS_DIR = Path("test/results")
ERRORS_FILE = RESULTS_DIR / "bench_errors.txt"


def _metrics(audio_duration_s: float, wall_s: float, ttfw_word_s: float | None = None, ttfw_text_s: float | None = None) -> Dict[str, float]:
    rtf = wall_s / audio_duration_s if audio_duration_s > 0 else float("inf")
    xrt = (audio_duration_s / wall_s) if wall_s > 0 else 0.0
    throughput_min_per_min = (audio_duration_s / wall_s) if wall_s > 0 else 0.0
    return {
        "wall_s": wall_s,
        "audio_s": audio_duration_s,
        "rtf": rtf,
        "xrt": xrt,
        "throughput_min_per_min": throughput_min_per_min,
        **({"ttfw_word_s": float(ttfw_word_s)} if ttfw_word_s is not None else {}),
        **({"ttfw_text_s": float(ttfw_text_s)} if ttfw_text_s is not None else {}),
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
    rtf_measured = [r["rtf_measured"] for r in results if "rtf_measured" in r and r["rtf_measured"] is not None]
    xrt = [r["xrt"] for r in results]
    throughput = [r["throughput_min_per_min"] for r in results]
    ttfw_word_vals = [r["ttfw_word_s"] for r in results if "ttfw_word_s" in r]
    ttfw_text_vals = [r["ttfw_text_s"] for r in results if "ttfw_text_s" in r]
    fin = [r.get("finalize_ms", 0.0) for r in results if r.get("finalize_ms", 0.0) > 0]
    gaps = [r.get("avg_partial_gap_ms", 0.0) for r in results if r.get("avg_partial_gap_ms", 0.0) > 0]

    # New honest metrics
    deltas = [r["delta_to_audio_ms"] for r in results if "delta_to_audio_ms" in r]
    sendd = [r["send_duration_s"] for r in results if "send_duration_s" in r]
    postf = [r["post_send_final_s"] for r in results if "post_send_final_s" in r]
    f2f = [r["flush_to_final_ms"] for r in results if "flush_to_final_ms" in r and r["flush_to_final_ms"] > 0]
    dtail = [r["decode_tail_ms"] for r in results if "decode_tail_ms" in r and r["decode_tail_ms"] > 0]

    print(f"\n== {title} ==")
    print(f"n={len(results)}")
    print(f"Wall s      | avg={stats.mean(wall):.4f}  p50={stats.median(wall):.4f}  p95={p(wall,0.95):.4f}")
    if ttfw_word_vals:
        print(f"TTFW(word)  | avg={stats.mean(ttfw_word_vals):.4f}  p50={stats.median(ttfw_word_vals):.4f}  p95={p(ttfw_word_vals,0.95):.4f}")
    if ttfw_text_vals:
        print(f"TTFW(text)  | avg={stats.mean(ttfw_text_vals):.4f}  p50={stats.median(ttfw_text_vals):.4f}  p95={p(ttfw_text_vals,0.95):.4f}")
    print(f"Audio s     | avg={stats.mean(audio):.4f}")
    print(f"RTF         | avg={stats.mean(rtf):.4f}  p50={stats.median(rtf):.4f}  p95={p(rtf,0.95):.4f}")
    if rtf_measured:
        print(f"RTF(meas)   | avg={stats.mean(rtf_measured):.4f}  p50={stats.median(rtf_measured):.4f}  p95={p(rtf_measured,0.95):.4f}")
    print(f"xRT         | avg={stats.mean(xrt):.4f}")
    print(f"Throughput  | avg={stats.mean(throughput):.2f} min/min")
    
    # New honest metrics display
    if deltas: print(f"Δ(audio) ms | avg={stats.mean(deltas):.1f}  p50={p(deltas,0.50):.1f}  p95={p(deltas,0.95):.1f}")
    if sendd:  print(f"Send dur s  | avg={stats.mean(sendd):.3f}  p50={stats.median(sendd):.3f}  p95={p(sendd,0.95):.3f}")
    if postf:  print(f"Post-send→Final s | avg={stats.mean(postf):.3f}  p50={stats.median(postf):.3f}  p95={p(postf,0.95):.3f}")
    if f2f:    print(f"Flush→Final ms    | avg={stats.mean(f2f):.1f}  p50={p(f2f,0.50):.1f}  p95={p(f2f,0.95):.1f}")
    if dtail:  print(f"Decode tail ms    | avg={stats.mean(dtail):.1f}  p50={p(dtail,0.50):.1f}  p95={p(dtail,0.95):.1f}")
    if gaps:   print(f"Partial gap ms    | avg={stats.mean(gaps):.1f}  p50={p(gaps,0.50):.1f}  p95={p(gaps,0.95):.1f}")


async def _ws_one(server: str, pcm_bytes: bytes, audio_seconds: float, rtf: float, kyutai_key: str) -> Dict[str, float]:
    """One session over WebSocket using Yap protocol with streaming mode."""
    url = ws_url(server, secure=False)
    url = append_auth_query(url, kyutai_key, override=True)
    
    file_duration_s = len(pcm_bytes) // 2 / 24000.0
    
    # Initialize handlers
    handler = BenchMessageHandler(debug=False)
    streamer = AudioStreamer(pcm_bytes, rtf, debug=False)
    
    ws_options = {
        "compression": None,
        "max_size": None,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_queue": None,
        "write_limit": 2**22,
        "open_timeout": 10,
        "close_timeout": 0.2,
    }
    
    t0 = time.perf_counter()
    async with websockets.connect(url, **ws_options) as ws:
        # Start message processing
        recv_task = asyncio.create_task(handler.process_messages(ws, t0))
        
        # Wait for Ready (optional)
        try:
            await asyncio.wait_for(handler.ready_event.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass
        
        # Check for immediate capacity rejection
        if handler.done_event.is_set() and handler.reject_reason == "capacity":
            with contextlib.suppress(Exception):
                asyncio.create_task(ws.close(code=1000, reason="capacity"))
            raise CapacityRejected("no free channels")
        
        # Stream audio
        last_signal_ts = await streamer.stream_audio(ws, handler.eos_decider)
        
        # Wait for final response
        timeout_s = max(10.0, file_duration_s / rtf + 3.0)
        try:
            await asyncio.wait_for(handler.done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            handler.handle_connection_close()
        
        # Clean close
        with contextlib.suppress(Exception):
            asyncio.create_task(ws.close(code=1000, reason="client done"))
    
    # Calculate metrics
    wall = time.perf_counter() - t0
    wall_to_final = (handler.final_recv_ts - t0) if handler.final_recv_ts else wall
    
    metrics = _metrics(file_duration_s, wall, handler.ttfw_word, handler.ttfw_text)
    metrics.update({
        "wall_to_final_s": float(wall_to_final),
        "rtf_measured": float(wall_to_final / file_duration_s) if file_duration_s > 0 else None,
        "partials": float(len(handler.partial_ts)),
        "avg_partial_gap_ms": float((sum(b - a for a, b in zip(handler.partial_ts[:-1], handler.partial_ts[1:])) / len(handler.partial_ts[:-1])) * 1000.0 if len(handler.partial_ts) >= 2 else 0.0),
        "final_len_chars": float(len(handler.final_text)),
        "finalize_ms": float(((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0),
        "rtf_target": float(rtf),
        "send_duration_s": float((streamer.last_chunk_sent_ts - t0) if streamer.last_chunk_sent_ts else 0.0),
        "post_send_final_s": float((handler.final_recv_ts - streamer.last_chunk_sent_ts) if (handler.final_recv_ts and streamer.last_chunk_sent_ts) else 0.0),
        "delta_to_audio_ms": float((wall_to_final - file_duration_s) * 1000.0),
        "flush_to_final_ms": float(((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0),
        "decode_tail_ms": float(((handler.final_recv_ts - handler.last_partial_ts) * 1000.0) if (handler.final_recv_ts and handler.last_partial_ts) else 0.0),
    })
    return metrics


async def bench_ws(server: str, file_path: str, total_reqs: int, concurrency: int, rtf: float, kyutai_key: str) -> Tuple[List[Dict[str, float]], int, int]:
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

    # Use 24k PCM for Yap, precompute once
    pcm = file_to_pcm16_mono_24k(file_path)
    audio_seconds = file_duration_seconds(file_path)

    async def worker(req_idx: int):
        nonlocal errors_total, rejected
        async with sem:
            # Stagger stream starts with jitter to avoid thundering-herd
            if req_idx > 0:
                await asyncio.sleep((req_idx % 32) * 0.025)  # up to ~800 ms stagger per wave
            try:
                # Dynamic timeout: audio duration * 2 + 60s buffer (minimum 300s for long streams)
                timeout = max(300.0, audio_seconds * 2 + 60.0)
                r = await asyncio.wait_for(_ws_one(server, pcm, audio_seconds, rtf, kyutai_key), timeout=timeout)
                results.append(r)
            except CapacityRejected as e:
                rejected += 1
                try:
                    with open(ERRORS_FILE, "a", encoding="utf-8") as ef:
                        ef.write(f"{datetime.utcnow().isoformat()}Z idx={req_idx} REJECTED capacity: {e}\n")
                except Exception:
                    pass
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
    ap = argparse.ArgumentParser(description="WebSocket streaming benchmark (Yap)")
    ap.add_argument("--server", default="127.0.0.1:8000", help="host:port or ws://host:port or full URL")
    ap.add_argument("--secure", action="store_true", help="(ignored unless you run wss)")
    ap.add_argument("--n", type=int, default=20, help="Total sessions")
    ap.add_argument("--concurrency", type=int, default=5, help="Max concurrent sessions")
    ap.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    ap.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    ap.add_argument("--kyutai-key", type=str, default=None, help="Kyutai API key (overrides KYUTAI_API_KEY env)")
    args = ap.parse_args()

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    kyutai_key = args.kyutai_key or os.getenv("KYUTAI_API_KEY")
    if not kyutai_key:
        print("Error: Kyutai API key missing. Use --kyutai-key or set KYUTAI_API_KEY env.")
        return

    print(f"Benchmark → WS (streaming) | n={args.n} | concurrency={args.concurrency} | rtf={args.rtf} | server={args.server}")
    print(f"File: {os.path.basename(file_path)}")

    t0 = time.time()
    results, rejected, errors = asyncio.run(
        bench_ws(args.server, file_path, args.n, args.concurrency, args.rtf, kyutai_key)
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
