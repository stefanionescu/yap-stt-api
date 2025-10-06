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

import websockets  # pip install websockets
import numpy as np
import msgpack
from utils import file_to_pcm16_mono_24k, file_duration_seconds, EOSDecider

class CapacityRejected(Exception):
    pass

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


def _ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Yap server ASR streaming endpoint"""
    if server.startswith(("ws://", "wss://")):
        return server
    scheme = "wss" if secure else "ws"
    # always add the path yap-server exposes
    host = server.rstrip("/")
    return f"{scheme}://{host}/api/asr-streaming"


async def _ws_one(server: str, pcm_bytes: bytes, audio_seconds: float, rtf: float) -> Dict[str, float]:
    """
    One session over WebSocket using Yap protocol with streaming mode.
    rtf: Real-time factor for throttling (1.0 for realtime, higher for faster)
    """
    url = _ws_url(server, secure=False)
    t0 = time.perf_counter()
    ttfw_word = None
    ttfw_text = None
    partial_ts: List[float] = []
    last_partial_ts = 0.0  # timestamp of last partial/word received
    last_chunk_sent_ts = 0.0
    last_signal_ts = 0.0
    final_recv_ts = 0.0
    last_text = ""
    final_text = ""
    words = []  # fallback transcript from Word events
    ready_event = asyncio.Event()
    done_event = asyncio.Event()
    reject_reason = None
    
    # Dynamic EOS settle gate
    eos_decider = EOSDecider()
    # original audio duration (based on the 24k PCM16 you built)
    orig_samples = len(pcm_bytes) // 2
    file_duration_s = orig_samples / 24000.0

    # Yap uses 24kHz, 80ms chunks
    samples_per_chunk = int(24000 * 0.080)  # 1920 samples
    bytes_per_chunk = samples_per_chunk * 2  # 3840 bytes
    chunk_ms = 80.0

    # Kyutai model authentication (do not use RunPod API key)
    API_KEY = os.getenv("KYUTAI_API_KEY")
    if not API_KEY:
        raise RuntimeError("KYUTAI_API_KEY is required for internal calls (bench).")
    ws_options = {
        "extra_headers": [("kyutai-api-key", API_KEY)],
        "compression": None,
        "max_size": None,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_queue": None,
        "write_limit": 2**22,
        "open_timeout": 10,
        "close_timeout": 0.2,
    }

    async with websockets.connect(url, **ws_options) as ws:
        
        # receiver: Handle Yap MessagePack message types
        async def receiver():
            nonlocal ttfw_word, ttfw_text, final_recv_ts, final_text, last_text, words, reject_reason
            try:
                async for raw in ws:
                    # yap-server only sends binary frames
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
                                    last_partial_ts = now  # track last partial timestamp
                                    eos_decider.update_partial(now)  # Update EOS state
                                    last_text = txt
                                final_text = txt  # prefer Partial/Text over Word assembly
                                # sync words array so later Words don't go backwards
                                words = final_text.split()
                                eos_decider.clear_pending_word()  # running text supersedes pending
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
                                    last_partial_ts = now  # track last partial timestamp
                                    eos_decider.update_partial(now)  # Update EOS state
                                    last_text = final_text
                        elif kind in ("Marker", "Final"):
                            # End-of-utterance - COMMIT any pending word before deciding final text
                            pending = eos_decider.get_pending_word()
                            if pending:
                                words.append(pending)
                                # If running text doesn't include it, sync it
                                if (not final_text) or len(final_text.split()) < len(words):
                                    final_text = " ".join(words).strip()
                            
                            txt = (data.get("text") or "").strip()
                            if txt:
                                final_text = txt  # prefer server-provided final
                            final_recv_ts = now
                            done_event.set()
                            break
                        elif kind == "Error":
                            msg_txt = (data.get("message") or data.get("error") or "").strip().lower()
                            if "no free channels" in msg_txt:
                                reject_reason = "capacity"
                            done_event.set()
                            break
                        elif kind == "Step":
                            # Ignore server step messages
                            continue
                        elif kind == "EndWord":
                            # Word end event - track for EOS decisions and handle pending words
                            w = (data.get("text") or data.get("word") or "").strip()
                            if w:
                                eos_decider.set_pending_word(w)
                            eos_decider.set_end_word()
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
                    # Check for pending word from EndWord events
                    pending = eos_decider.get_pending_word()
                    if pending:
                        words.append(pending)
                    
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

        # Optional grace period for Ready, but also check for immediate Error (capacity)
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass  # proceed to send anyway
        if done_event.is_set() and reject_reason == "capacity":
            with contextlib.suppress(Exception):
                asyncio.create_task(ws.close(code=1000, reason="capacity"))
            raise CapacityRejected("no free channels")
        
        # Convert PCM16 bytes to float32 normalized [-1,1] (no pre-padding)
        pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        hop = 1920  # 80 ms @ 24k
        
        # right before the loop
        t_stream0 = time.perf_counter()
        samples_sent = 0
        sr = 24000

        # sender: stream audio in MessagePack frames with RTF control
        # realistic streaming with RTF control - pace by wall-clock against audio timeline
        for i in range(0, len(pcm_int16), hop):
            pcm_chunk = pcm_int16[i:i+hop]
            if len(pcm_chunk) == 0:
                break
            msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                               use_bin_type=True, use_single_float=True)
            await ws.send(msg)
            last_chunk_sent_ts = time.perf_counter()

            # advance timeline by the *actual* chunk duration
            samples_sent += len(pcm_chunk)
            target = t_stream0 + (samples_sent / sr) / max(rtf, 1e-6)
            sleep_for = target - time.perf_counter()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

        # Dynamic EOS settle gate - wait for evidence utterance is over
        await eos_decider.wait_for_settle(max_wait_ms=600)
        
        # Top up with just enough silence if needed
        needed_ms = eos_decider.needed_padding_ms()
        frames = int((needed_ms + 79) // 80)  # ceil to 80ms frames
        
        # Ensure at least one decoder step happens before Flush
        MIN_PAD_FRAMES = 1
        frames = max(frames, MIN_PAD_FRAMES)
        
        if frames > 0:
            silence = np.zeros(1920, dtype=np.float32).tolist()
            for _ in range(frames):
                await ws.send(msgpack.packb({"type":"Audio","pcm":silence},
                                            use_bin_type=True, use_single_float=True))
        
        # Final flush
        await ws.send(msgpack.packb({"type": "Flush"}, use_bin_type=True))
        last_signal_ts = time.perf_counter()
        
        # Wait for server final with dynamic timeout
        timeout_s = max(10.0, file_duration_s / rtf + 3.0)
        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            # Check for pending word from EndWord events before giving up
            pending = eos_decider.get_pending_word()
            if pending:
                words.append(pending)
            
            if words or final_text:
                final_recv_ts = time.perf_counter()
                if not final_text and words:
                    final_text = " ".join(words).strip()
            else:
                pass  # real timeout, will be logged as error
        
        # Proactively close; don't block main path on close handshake
        with contextlib.suppress(Exception):
            asyncio.create_task(ws.close(code=1000, reason="client done"))
        # Receiver may still be draining; don't await it if we're done

    wall = time.perf_counter() - t0
    metrics = _metrics(file_duration_s, wall, ttfw_word, ttfw_text)
    # Add wall_to_final (up to Final). No default tail; no forced pad in timing.
    wall_to_final = (final_recv_ts - t0) if final_recv_ts else wall
    metrics["wall_to_final_s"] = float(wall_to_final)
    metrics["rtf_measured"] = float(wall_to_final / file_duration_s) if file_duration_s > 0 else None
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0

    # New derived metrics (honest taxonomy)
    send_duration_s = (last_chunk_sent_ts - t0) if last_chunk_sent_ts else 0.0
    post_send_final_s = (final_recv_ts - last_chunk_sent_ts) if (final_recv_ts and last_chunk_sent_ts) else 0.0
    delta_to_audio_s = wall_to_final - file_duration_s
    decode_tail_s = (final_recv_ts - last_partial_ts) if (final_recv_ts and last_partial_ts) else None

    metrics.update({
        "partials": float(len(partial_ts)),
        "avg_partial_gap_ms": float(avg_gap_ms),
        "final_len_chars": float(len(final_text)),
        "finalize_ms": float(((final_recv_ts - last_signal_ts) * 1000.0) if (final_recv_ts and last_signal_ts) else 0.0),
        "rtf_target": float(rtf),
        # New honest metrics
        "send_duration_s": float(send_duration_s),
        "post_send_final_s": float(post_send_final_s),
        "delta_to_audio_ms": float(delta_to_audio_s * 1000.0),
        "flush_to_final_ms": float(((final_recv_ts - last_signal_ts) * 1000.0) if (final_recv_ts and last_signal_ts) else 0.0),
        "decode_tail_ms": float(decode_tail_s * 1000.0) if decode_tail_s is not None else 0.0,
    })
    return metrics


async def bench_ws(server: str, file_path: str, total_reqs: int, concurrency: int, rtf: float) -> Tuple[List[Dict[str, float]], int, int]:
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
                r = await asyncio.wait_for(_ws_one(server, pcm, audio_seconds, rtf), timeout=timeout)
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
    args = ap.parse_args()

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    print(f"Benchmark → WS (streaming) | n={args.n} | concurrency={args.concurrency} | rtf={args.rtf} | server={args.server}")
    print(f"File: {os.path.basename(file_path)}")

    t0 = time.time()
    results, rejected, errors = asyncio.run(
        bench_ws(args.server, file_path, args.n, args.concurrency, args.rtf)
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
