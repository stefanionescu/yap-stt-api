#!/usr/bin/env python3
"""
Yap WebSocket streaming client.

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

from utils import file_to_pcm16_mono_24k, file_duration_seconds, EOSDecider

# Optionally load .env to pick up RUNPOD_* defaults if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(override=True)
except Exception:
    pass

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
    parser = argparse.ArgumentParser(description="WebSocket Yap client")
    # Prefer RUNPOD_TCP_HOST/PORT when available, else fall back to YAP_SERVER or localhost
    runpod_host = os.getenv("RUNPOD_TCP_HOST")
    runpod_port = os.getenv("RUNPOD_TCP_PORT") or "8000"
    if runpod_host:
        default_server = f"{runpod_host}:{runpod_port}"
    else:
        default_server = os.getenv("YAP_SERVER", "127.0.0.1:8000")
    parser.add_argument("--server", default=default_server,
                        help="host:port or ws://host:port or full URL (uses RUNPOD_TCP_HOST/PORT if set)")
    parser.add_argument("--secure", action="store_true", help="Use WSS (requires cert on server)")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    parser.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    return parser.parse_args()

def _ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Yap server ASR streaming endpoint"""
    if server.startswith(("ws://", "wss://")):
        return server
    scheme = "wss" if secure else "ws"
    # always add the path yap-server exposes
    host = server.rstrip("/")
    return f"{scheme}://{host}/api/asr-streaming"

def _is_runpod_host(server: str) -> bool:
    s = (server or "").strip().lower()
    return "runpod.net" in s

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

    # Auto-enable TLS when targeting RunPod hosts unless explicitly overridden by scheme
    url = _ws_url(args.server, args.secure or _is_runpod_host(args.server))
    print(f"Connecting to: {url}")
    print(f"File: {os.path.basename(file_path)} ({duration:.2f}s)")

    # Yap uses 24kHz, 80ms chunks
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
    
    # Dynamic EOS settle gate
    eos_decider = EOSDecider()

    # Yap server authentication (prefer RunPod key if provided)
    API_KEY = os.getenv("RUNPOD_API_KEY") or os.getenv("YAP_API_KEY") or "public_token"
    ws_options = {
        "extra_headers": [("yap-api-key", API_KEY)],
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
    
    # Network latency measurements
    connect_start = time.perf_counter()
    async with websockets.connect(url, **ws_options) as ws:
        connect_time = time.perf_counter() - connect_start
        
        first_response_time = None
        
        async def receiver():
            nonlocal final_text, final_recv_ts, last_text, ttfw, words, first_response_time
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
                            txt = (data.get("text") or "").strip()
                            if txt:
                                if ttfw is None:
                                    ttfw = now - t0
                                # Track first response latency
                                if first_response_time is None and first_audio_sent is not None:
                                    first_response_time = now - first_audio_sent
                                if txt != last_text:
                                    partial_ts.append(now - t0)
                                    last_partial_ts = now  # track last partial timestamp
                                    eos_decider.update_partial(now)  # Update EOS state
                                    print(f"PART: {txt}")
                                    last_text = txt
                                final_text = txt  # prefer Partial/Text over Word assembly
                                # sync words array so later Words don't go backwards
                                words = final_text.split()
                                eos_decider.clear_pending_word()  # running text supersedes pending
                        elif kind == "Word":
                            w = (data.get("text") or data.get("word") or "").strip()
                            if w:
                                if ttfw is None:
                                    ttfw = now - t0  # strict TTFW on first word
                                # Track first response latency
                                if first_response_time is None and first_audio_sent is not None:
                                    first_response_time = now - first_audio_sent
                                words.append(w)  # accumulate words
                                final_text = " ".join(words).strip()  # assemble running text
                                if final_text != last_text:  # treat each new word as a partial
                                    partial_ts.append(now - t0)
                                    last_partial_ts = now  # track last partial timestamp
                                    eos_decider.update_partial(now)  # Update EOS state
                                    last_text = final_text
                                # print occasional words, not every single one
                                if len(words) % 5 == 1 or len(words) <= 3:
                                    print(f"WORD: {w!r}, assembled: {final_text!r}")
                        elif kind in ("Final", "Marker"):
                            # End-of-utterance - COMMIT any pending word before deciding final text
                            pending = eos_decider.get_pending_word()
                            if pending:
                                words.append(pending)
                                print(f"Added pending word on Final: {pending!r}")
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
                                print(f"EndWord pending: {w!r}")
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
                        print(f"Added pending word on close: {pending!r}")
                    
                    if words or final_text:
                        final_recv_ts = time.perf_counter()
                        if not final_text and words:
                            final_text = " ".join(words).strip()
                        done_event.set()
                pass

        recv_task = asyncio.create_task(receiver())

        # Measure handshake latency (connection to Ready message)
        handshake_start = time.perf_counter()
        handshake_time = None
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=0.2)
            handshake_time = time.perf_counter() - handshake_start
        except asyncio.TimeoutError:
            handshake_time = 0.2  # timeout duration
            pass  # proceed to send anyway
        
        # Convert PCM16 bytes to float32 normalized [-1,1] (no pre-padding)
        pcm_int16 = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        hop = 1920  # 80 ms @ 24k
        
        # right before the loop
        t_stream0 = time.perf_counter()
        samples_sent = 0
        sr = 24000
        first_audio_sent = None

        # Stream audio with RTF control - pace by wall-clock against audio timeline
        # 80 ms @ 24k = 1920 samples
        for i in range(0, len(pcm_int16), hop):
            pcm_chunk = pcm_int16[i:i+hop]
            if len(pcm_chunk) == 0:
                break
            msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                               use_bin_type=True, use_single_float=True)
            await ws.send(msg)
            last_chunk_sent_ts = time.perf_counter()
            
            # Track first audio chunk sent for response latency
            if first_audio_sent is None:
                first_audio_sent = last_chunk_sent_ts

            # advance timeline by the *actual* chunk duration
            samples_sent += len(pcm_chunk)
            target = t_stream0 + (samples_sent / sr) / max(args.rtf, 1e-6)
            sleep_for = target - time.perf_counter()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

        # Dynamic EOS settle gate - wait for evidence utterance is over
        print("Starting dynamic EOS settle gate")
        await eos_decider.wait_for_settle(max_wait_ms=600)
        
        observed = eos_decider.observed_silence_ms()
        needed = eos_decider.needed_padding_ms()
        print(f"Settle complete - observed: {observed:.1f}ms, needed padding: {needed:.1f}ms")
        
        # Top up with just enough silence if needed
        needed_ms = eos_decider.needed_padding_ms()
        frames = int((needed_ms + 79) // 80)  # ceil to 80ms frames
        
        # Ensure at least one decoder step happens before Flush
        MIN_PAD_FRAMES = 1
        frames = max(frames, MIN_PAD_FRAMES)
        
        if frames > 0:
            print(f"Adding {frames} silence frames ({frames * 80:.0f}ms)")
            silence = np.zeros(1920, dtype=np.float32).tolist()
            for _ in range(frames):
                await ws.send(msgpack.packb({"type":"Audio","pcm":silence},
                                            use_bin_type=True, use_single_float=True))
        
        # Final flush
        await ws.send(msgpack.packb({"type": "Flush"}, use_bin_type=True))
        last_signal_ts = time.perf_counter()
        print("Sent final Flush")
        
        # Wait for server final with dynamic timeout
        timeout_s = max(10.0, file_duration_s / args.rtf + 3.0)
        print(f"Waiting for Final (timeout {timeout_s:.1f}s)")
        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            # Check for pending word from EndWord events before giving up
            pending = eos_decider.get_pending_word()
            if pending:
                words.append(pending)
                print(f"Added pending word on timeout: {pending!r}")
            
            if words or final_text:
                final_recv_ts = time.perf_counter()
                if not final_text and words:
                    final_text = " ".join(words).strip()
                print(f"Accepting timeout with text: '{final_text}'")
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
    
    # Network latency metrics
    connect_ms = connect_time * 1000.0
    handshake_ms = handshake_time * 1000.0 if handshake_time is not None else 0.0
    first_response_ms = first_response_time * 1000.0 if first_response_time is not None else 0.0
    
    ttfw_ms = (ttfw * 1000.0) if ttfw is not None else 0.0
    
    print(f"\n=== Network Latency ===")
    print(f"Connection time: {connect_ms:.1f}ms")
    print(f"Handshake time: {handshake_ms:.1f}ms")
    print(f"First response: {first_response_ms:.1f}ms")
    
    print(f"\n=== Transcription Performance ===")
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
            # Network latency metrics
            "connect_ms": connect_ms,
            "handshake_ms": handshake_ms,
            "first_response_ms": first_response_ms,
            # Processing metrics
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
