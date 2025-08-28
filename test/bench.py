#!/usr/bin/env python3
"""
Benchmark WebSocket streaming for Moshi ASR server.

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

import websockets  # pip install websockets
import numpy as np
import msgpack
from utils import file_to_pcm16_mono_24k, file_duration_seconds

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
    xrt = [r["xrt"] for r in results]
    throughput = [r["throughput_min_per_min"] for r in results]
    ttfw_word_vals = [r["ttfw_word_s"] for r in results if "ttfw_word_s" in r]
    ttfw_text_vals = [r["ttfw_text_s"] for r in results if "ttfw_text_s" in r]
    fin = [r.get("finalize_ms", 0.0) for r in results if r.get("finalize_ms", 0.0) > 0]
    gaps = [r.get("avg_partial_gap_ms", 0.0) for r in results if r.get("avg_partial_gap_ms", 0.0) > 0]

    print(f"\n== {title} ==")
    print(f"n={len(results)}")
    print(f"Wall s      | avg={stats.mean(wall):.4f}  p50={stats.median(wall):.4f}  p95={p(wall,0.95):.4f}")
    if ttfw_word_vals:
        print(f"TTFW(word)  | avg={stats.mean(ttfw_word_vals):.4f}  p50={stats.median(ttfw_word_vals):.4f}  p95={p(ttfw_word_vals,0.95):.4f}")
    if ttfw_text_vals:
        print(f"TTFW(text)  | avg={stats.mean(ttfw_text_vals):.4f}  p50={stats.median(ttfw_text_vals):.4f}  p95={p(ttfw_text_vals,0.95):.4f}")
    print(f"Audio s     | avg={stats.mean(audio):.4f}")
    print(f"RTF         | avg={stats.mean(rtf):.4f}  p50={stats.median(rtf):.4f}  p95={p(rtf,0.95):.4f}")
    print(f"xRT         | avg={stats.mean(xrt):.4f}")
    print(f"Throughput  | avg={stats.mean(throughput):.2f} min/min")
    if fin:
        print(f"Finalize ms | avg={stats.mean(fin):.1f}  p50={p(fin,0.50):.1f}  p95={p(fin,0.95):.1f}")
    if gaps:
        print(f"Partial gap | avg={stats.mean(gaps):.1f}  p50={p(gaps,0.50):.1f}  p95={p(gaps,0.95):.1f}")


def _ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Moshi server ASR streaming endpoint"""
    if server.startswith(("ws://", "wss://")):
        return server
    scheme = "wss" if secure else "ws"
    # always add the path moshi-server exposes
    host = server.rstrip("/")
    return f"{scheme}://{host}/api/asr-streaming"


async def _ws_one(server: str, pcm_bytes: bytes, audio_seconds: float, rtf: float, mode: str) -> Dict[str, float]:
    """
    One session over WebSocket using Moshi protocol. For 'stream', sleeps per chunk to simulate realtime.
    For 'oneshot', sends with no sleeps.
    rtf: Real-time factor for throttling (1.0 for realtime, higher for faster)
    """
    url = _ws_url(server, secure=False)
    t0 = time.perf_counter()
    ttfw_word = None
    ttfw_text = None
    partial_ts: List[float] = []
    last_chunk_sent_ts = 0.0
    last_signal_ts = 0.0
    final_recv_ts = 0.0
    last_text = ""
    final_text = ""
    words = []  # fallback transcript from Word events
    ready_event = asyncio.Event()
    done_event = asyncio.Event()

    # Moshi uses 24kHz, 80ms chunks
    samples_per_chunk = int(24000 * 0.080)  # 1920 samples
    bytes_per_chunk = samples_per_chunk * 2  # 3840 bytes
    chunk_ms = 80.0

    # Moshi server authentication
    API_KEY = os.getenv("MOSHI_API_KEY", "public_token")
    ws_options = {
        "extra_headers": [("kyutai-api-key", API_KEY)],
        "compression": None,
        "max_size": None,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_queue": None,
        "write_limit": 2**22
    }

    async with websockets.connect(url, **ws_options) as ws:
        
        # receiver: Handle Moshi MessagePack message types
        async def receiver():
            nonlocal ttfw_word, ttfw_text, final_recv_ts, final_text, last_text, words
            try:
                async for raw in ws:
                    # moshi-server only sends binary frames
                    if isinstance(raw, (bytes, bytearray)):
                        data = msgpack.unpackb(raw, raw=False)
                        kind = data.get("type")
                        
                        now = time.perf_counter()
                        
                        if kind == "Ready":
                            ready_event.set()
                        elif kind in ("Partial", "Text"):
                            # Running transcript - prefer over Word assembly
                            txt = (data.get("text") or "").strip()
                            if txt:
                                if ttfw_text is None:
                                    ttfw_text = now - t0
                                if txt != last_text:
                                    partial_ts.append(now - t0)
                                    last_text = txt
                                final_text = txt  # prefer Partial/Text over Word assembly
                                # sync words array so later Words don't go backwards
                                words = final_text.split()
                        elif kind == "Word":
                            w = (data.get("text") or data.get("word") or "").strip()
                            if w:
                                # First word for strict TTFW
                                if ttfw_word is None:
                                    ttfw_word = now - t0
                                words.append(w)  # accumulate words
                                final_text = " ".join(words).strip()  # assemble running text
                                if final_text != last_text:  # treat each new word as a partial
                                    partial_ts.append(now - t0)
                                    last_text = final_text
                        elif kind in ("Marker", "Final"):
                            # End-of-utterance
                            txt = (data.get("text") or "").strip()
                            if txt:
                                final_text = txt
                            final_recv_ts = now
                            done_event.set()
                            break
                        elif kind == "Error":
                            done_event.set()
                            break
                        elif kind == "Step":
                            # Ignore server step messages
                            continue
                        elif kind == "EndWord":
                            # Word end event, ignore for metrics
                            continue
                    else:
                        # Skip text messages
                        continue
            except websockets.exceptions.ConnectionClosedOK:
                # graceful close — okay
                pass
            except websockets.exceptions.ConnectionClosedError as e:
                # server closed without a close frame — treat as final if we have content
                if not done_event.is_set():
                    if words or final_text:
                        final_recv_ts = time.perf_counter()
                        if not final_text and words:
                            final_text = " ".join(words).strip()
                        done_event.set()
                pass
                
            # socket closed
            if final_recv_ts == 0.0:
                final_recv_ts = time.perf_counter()

        recv_task = asyncio.create_task(receiver())

        # Optional grace period for Ready (don't block if server doesn't send it)
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass  # proceed to send anyway
        
        # Convert PCM16 bytes to float32 normalized [-1,1] and pad to full hops
        pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        hop = 1920  # 80 ms @ 24k
        rem = len(pcm_int16) % hop
        if rem:
            pad = hop - rem
            pcm_int16 = np.pad(pcm_int16, (0, pad))
        
        # sender: stream audio in MessagePack frames
        if mode == "stream":
            # realistic streaming with RTF control
            for i in range(0, len(pcm_int16), hop):
                pcm_chunk = pcm_int16[i:i+hop]
                if len(pcm_chunk) == 0:
                    break
                msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                                   use_bin_type=True, use_single_float=True)
                await ws.send(msg)
                last_chunk_sent_ts = time.perf_counter()
                await asyncio.sleep(chunk_ms / 1000.0 / rtf)
        else:
            # oneshot: no sleeps; still chunk for reasonable frame sizes
            hop = int(24000 * 2.0)  # ~2 sec chunks
            for i in range(0, len(pcm_int16), hop):
                pcm_chunk = pcm_int16[i:i+hop]
                if len(pcm_chunk) == 0:
                    break
                msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                                   use_bin_type=True, use_single_float=True)
                await ws.send(msg)
                last_chunk_sent_ts = time.perf_counter()

        # tail silence: send a short tail before Flush to commit last tokens
        silence = np.zeros(1920, dtype=np.float32)
        for _ in range(12):  # ~960 ms tail
            msg = msgpack.packb({"type": "Audio", "pcm": silence.tolist()},
                               use_bin_type=True, use_single_float=True)
            await ws.send(msg)
            last_chunk_sent_ts = time.perf_counter()
            await asyncio.sleep(0.080 / rtf)

        # flush + wait for final
        await ws.send(msgpack.packb({"type": "Flush"}, use_bin_type=True))
        last_signal_ts = time.perf_counter()
        
        # Wait for server final with dynamic timeout based on audio duration
        timeout_s = max(10.0, audio_seconds / rtf + 3.0)
        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            # if we have text, accept it; otherwise it's a real timeout
            if not (words or final_text):
                pass  # real timeout, will be logged as error
            else:
                # set final_recv_ts for metrics even on timeout
                final_recv_ts = time.perf_counter()
                if not final_text and words:
                    final_text = " ".join(words).strip()
            pass
        
        # Proactively close; then await receiver task
        with contextlib.suppress(websockets.exceptions.ConnectionClosed, 
                                websockets.exceptions.ConnectionClosedError, 
                                websockets.exceptions.ConnectionClosedOK):
            await ws.close(code=1000, reason="client done")
        
        with contextlib.suppress(Exception):
            await recv_task

    wall = time.perf_counter() - t0
    metrics = _metrics(audio_seconds, wall, ttfw_word, ttfw_text)
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0

    metrics.update({
        "partials": float(len(partial_ts)),
        "avg_partial_gap_ms": float(avg_gap_ms),
        "final_len_chars": float(len(final_text)),
        "finalize_ms": float(((final_recv_ts - last_signal_ts) * 1000.0) if (final_recv_ts and last_signal_ts) else 0.0),
        "mode": mode,
        "rtf": float(rtf),
    })
    return metrics


async def bench_ws(server: str, file_path: str, total_reqs: int, concurrency: int, rtf: float, mode: str) -> Tuple[List[Dict[str, float]], int, int]:
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

    # Use 24k PCM for Moshi, precompute once
    pcm = file_to_pcm16_mono_24k(file_path)
    audio_seconds = file_duration_seconds(file_path)

    async def worker(req_idx: int):
        nonlocal errors_total
        async with sem:
            # Stagger stream starts with jitter to avoid thundering-herd
            if req_idx > 0:
                await asyncio.sleep((req_idx % 32) * 0.025)  # up to ~800 ms stagger per wave
            try:
                # Dynamic timeout: audio duration * 2 + 60s buffer (minimum 300s for long streams)
                timeout = max(300.0, audio_seconds * 2 + 60.0)
                r = await asyncio.wait_for(_ws_one(server, pcm, audio_seconds, rtf, mode), timeout=timeout)
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
    ap = argparse.ArgumentParser(description="WebSocket streaming benchmark (Moshi)")
    ap.add_argument("--server", default="127.0.0.1:8000", help="host:port or ws://host:port or full URL")
    ap.add_argument("--secure", action="store_true", help="(ignored unless you run wss)")
    ap.add_argument("--n", type=int, default=20, help="Total sessions")
    ap.add_argument("--concurrency", type=int, default=5, help="Max concurrent sessions")
    ap.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    ap.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    ap.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot")
    args = ap.parse_args()

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    print(f"Benchmark → WS ({args.mode}) | n={args.n} | concurrency={args.concurrency} | rtf={args.rtf} | server={args.server}")
    print(f"File: {os.path.basename(file_path)}")

    t0 = time.time()
    results, rejected, errors = asyncio.run(
        bench_ws(args.server, file_path, args.n, args.concurrency, args.rtf, args.mode)
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
