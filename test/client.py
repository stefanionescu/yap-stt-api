#!/usr/bin/env python3
"""
Moshi WebSocket streaming client.

Streams PCM16@24k from a file to simulate realtime voice and prints partials/final.
"""
from __future__ import annotations
import argparse
import asyncio

import contextlib
import json
import os
import time
from pathlib import Path
import websockets
import numpy as np
import msgpack

from utils import file_to_pcm16_mono_24k, file_duration_seconds

SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}

def find_sample_files() -> list[str]:
    p = Path(SAMPLES_DIR)
    if not p.exists():
        return []
    files: list[str] = []
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

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocket Moshi client")
    parser.add_argument("--server", default=os.getenv("MOSHI_SERVER", "127.0.0.1:8000"),
                        help="host:port or ws://host:port or full URL")
    parser.add_argument("--secure", action="store_true", help="Use WSS (requires cert on server)")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    parser.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    parser.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot ASR")
    return parser.parse_args()

def _ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Moshi server ASR streaming endpoint"""
    if server.startswith(("ws://", "wss://")):
        return server
    scheme = "wss" if secure else "ws"
    # always add the path moshi-server exposes
    host = server.rstrip("/")
    return f"{scheme}://{host}/api/asr-streaming"

async def run(args: argparse.Namespace) -> None:
    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    pcm = file_to_pcm16_mono_24k(file_path)
    duration = file_duration_seconds(file_path)

    url = _ws_url(args.server, args.secure)
    print(f"Connecting to: {url}")
    print(f"File: {os.path.basename(file_path)} ({duration:.2f}s)")

    # Moshi uses 24kHz, 80ms chunks
    samples_per_chunk = int(24000 * 0.080)  # 1920 samples
    bytes_per_chunk = samples_per_chunk * 2  # 3840 bytes
    chunk_ms = 80.0
    # original audio duration (based on the 24k PCM16 you built)
    orig_samples = len(pcm) // 2
    file_duration_s = orig_samples / 24000.0

    partial_ts: list[float] = []
    last_partial_ts = 0.0  # timestamp of last partial/word received
    last_chunk_sent_ts = 0.0
    last_signal_ts = 0.0
    final_recv_ts = 0.0
    final_text = ""
    last_text = ""
    words: list[str] = []  # fallback transcript from Word events

    # Moshi server authentication
    API_KEY = os.getenv("MOSHI_API_KEY", "public_token")
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

    t0 = time.perf_counter()
    ttfw = None
    ready_event = asyncio.Event()
    done_event = asyncio.Event()
    async with websockets.connect(url, **ws_options) as ws:
        
        async def receiver():
            nonlocal final_text, final_recv_ts, last_text, ttfw, words
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
                            txt = (data.get("text") or "").strip()
                            if txt:
                                if ttfw is None:
                                    ttfw = now - t0
                                if txt != last_text:
                                    partial_ts.append(now - t0)
                                    last_partial_ts = now  # track last partial timestamp
                                    print(f"PART: {txt}")
                                    last_text = txt
                                final_text = txt  # prefer Partial/Text over Word assembly
                                # sync words array so later Words don't go backwards
                                words = final_text.split()
                        elif kind == "Word":
                            w = (data.get("text") or data.get("word") or "").strip()
                            if w:
                                if ttfw is None:
                                    ttfw = now - t0  # strict TTFW on first word
                                words.append(w)  # accumulate words
                                final_text = " ".join(words).strip()  # assemble running text
                                if final_text != last_text:  # treat each new word as a partial
                                    partial_ts.append(now - t0)
                                    last_partial_ts = now  # track last partial timestamp
                                    last_text = final_text
                                # print occasional words, not every single one
                                if len(words) % 5 == 1 or len(words) <= 3:
                                    print(f"WORD: {w!r}, assembled: {final_text!r}")
                        elif kind in ("Final", "Marker"):
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
                            # Word end event, ignore for display
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

        recv_task = asyncio.create_task(receiver())

        # Optional grace period for Ready (don't block if server doesn't send it)
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass  # proceed to send anyway
        
        # Convert PCM16 bytes to float32 normalized [-1,1] (no pre-padding)
        pcm_int16 = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        hop = 1920  # 80 ms @ 24k
        
        # right before the loop
        t_stream0 = time.perf_counter()
        samples_sent = 0
        sr = 24000

        if args.mode == "stream":
            # 80 ms @ 24k = 1920 samples - pace by wall-clock against audio timeline
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
                target = t_stream0 + (samples_sent / sr) / max(args.rtf, 1e-6)
                sleep_for = target - time.perf_counter()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
        else:
            # oneshot: larger chunks
            hop = int(24000 * 2.0)  # ~2 sec chunks
            for i in range(0, len(pcm_int16), hop):
                pcm_chunk = pcm_int16[i:i+hop]
                if len(pcm_chunk) == 0:
                    break
                msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                                   use_bin_type=True, use_single_float=True)
                await ws.send(msg)
                last_chunk_sent_ts = time.perf_counter()

        # flush + wait for final
        await ws.send(msgpack.packb({"type": "Flush"}, use_bin_type=True))
        last_signal_ts = time.perf_counter()
        
        # Wait for server final with dynamic timeout based on file duration
        timeout_s = max(10.0, file_duration_s / args.rtf + 3.0)
        # Minimal fast-path wait for Final
        fast_wait = min(max(2 * (chunk_ms / 1000.0) / args.rtf, 0.2), 1.0)  # 0.2–1.0 s
        try:
            await asyncio.wait_for(done_event.wait(), timeout=fast_wait)
        except asyncio.TimeoutError:
            # Fallback: one zero-hop (no sleep) + re-Flush, then wait the remainder
            print("No Final yet — sending single zero-hop + re-Flush")
            silence = np.zeros(1920, dtype=np.float32)
            msg = msgpack.packb({"type": "Audio", "pcm": silence.tolist()},
                                use_bin_type=True, use_single_float=True)
            await ws.send(msg)
            await ws.send(msgpack.packb({"type": "Flush"}, use_bin_type=True))
            last_signal_ts = time.perf_counter()
            try:
                remain = max(0.0, timeout_s - fast_wait)
                await asyncio.wait_for(done_event.wait(), timeout=remain)
            except asyncio.TimeoutError:
                if words or final_text:
                    final_recv_ts = time.perf_counter()
                    if not final_text and words:
                        final_text = " ".join(words).strip()
                    print(f"Accepting timeout with partial text: '{final_text}'")
                else:
                    print("Warning: Timeout waiting for final response and no text received")
        
        # Proactively close; don't block main path on close handshake
        with contextlib.suppress(Exception):
            asyncio.create_task(ws.close(code=1000, reason="client done"))
        # Receiver may still be draining; don't await it if we're done

    if final_text:
        print("\n=== Transcription Result ===")
        print(final_text)
    else:
        print("No final text")

    elapsed_s = time.perf_counter() - t0
    finalize_ms = ((final_recv_ts - last_signal_ts) * 1000.0) if (final_recv_ts and last_signal_ts) else 0.0
    # Add wall_to_final (up to Final). No default tail; no forced pad in timing.
    wall_to_final = (final_recv_ts - t0) if final_recv_ts else elapsed_s
    rtf_measured = (wall_to_final / file_duration_s) if file_duration_s > 0 else None
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0
    
    # New derived metrics (honest taxonomy)
    send_duration_s = (last_chunk_sent_ts - t0) if last_chunk_sent_ts else 0.0
    post_send_final_s = (final_recv_ts - last_chunk_sent_ts) if (final_recv_ts and last_chunk_sent_ts) else 0.0
    delta_to_audio_ms = (wall_to_final - file_duration_s) * 1000.0
    decode_tail_ms = ((final_recv_ts - last_partial_ts) * 1000.0) if (final_recv_ts and last_partial_ts) else 0.0
    
    ttfw_ms = (ttfw * 1000.0) if ttfw is not None else 0.0
    print(f"Transcription time (to Final): {wall_to_final:.3f}s  RTF(measured): {rtf_measured:.4f}  (target={args.rtf})")
    print(f"TTFW: {ttfw_ms:.1f}ms  Partials: {len(partial_ts)}  Avg partial gap: {avg_gap_ms:.1f} ms")
    print(f"Δ(audio): {delta_to_audio_ms:.1f}ms  Send dur: {send_duration_s:.3f}s  Post-send→Final: {post_send_final_s:.3f}s")
    print(f"Flush→Final: {finalize_ms:.1f}ms  Decode tail: {decode_tail_ms:.1f}ms")

    # metrics out
    out_dir = Path("test/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "client_metrics.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "elapsed_s": elapsed_s,              # includes close/cleanup
            "wall_to_final_s": wall_to_final,    # what users feel
            "audio_s": file_duration_s,          # original file duration at 24k
            "rtf_target": args.rtf,              # configured throttle
            "rtf_measured": rtf_measured,        # measured RTF
            "ttfw_ms": ttfw_ms,
            "partials": len(partial_ts),
            "avg_partial_gap_ms": avg_gap_ms,
            "finalize_ms": finalize_ms,
            "file": os.path.basename(file_path),
            "server": args.server,
            # New honest metrics
            "send_duration_s": send_duration_s,
            "post_send_final_s": post_send_final_s,
            "delta_to_audio_ms": delta_to_audio_ms,
            "flush_to_final_ms": finalize_ms,
            "decode_tail_ms": decode_tail_ms,
        }, ensure_ascii=False) + "\n")

def main() -> None:
    import asyncio
    asyncio.run(run(parse_args()))

if __name__ == "__main__":
    main()
