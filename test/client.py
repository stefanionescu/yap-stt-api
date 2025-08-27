#!/usr/bin/env python3
"""
Moshi WebSocket streaming client.

Streams PCM16@24k from a file to simulate realtime voice and prints partials/final.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import json
import os
import time
from pathlib import Path
import websockets

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
    parser.add_argument("--server", default=os.getenv("MOSHI_SERVER", "localhost:8000/api/asr-streaming"),
                        help="host:port or ws://host:port or full URL")
    parser.add_argument("--secure", action="store_true", help="Use WSS (requires cert on server)")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    parser.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    parser.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot ASR")
    return parser.parse_args()

def _ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Moshi server with proper /api/asr-streaming path"""
    if server.startswith("ws://") or server.startswith("wss://"):
        return server
    else:
        scheme = "wss" if secure else "ws"
        # Handle host:port format - add path if missing
        if "/" not in server:
            server = f"{server}/api/asr-streaming"
        elif not server.endswith("/api/asr-streaming"):
            server = f"{server}/api/asr-streaming"
        return f"{scheme}://{server}"

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

    partial_ts: list[float] = []
    last_chunk_sent_ts = 0.0
    final_recv_ts = 0.0
    final_text = ""
    last_text = ""

    # API key header for Moshi server authentication
    API_KEY = os.getenv("MOSHI_API_KEY", "public_token")
    headers = [("kyutai-api-key", API_KEY)]
    
    ws_options = {
        "max_size": None,
        "compression": None,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_queue": 4,
        "write_limit": 2**22,
        "extra_headers": headers
    }

    t0 = time.perf_counter()
    async with websockets.connect(url, **ws_options) as ws:
        # Send handshake and wait for Ready
        ready_event = asyncio.Event()
        await ws.send(json.dumps({"type": "StartSTT"}))
        
        async def receiver():
            nonlocal final_text, final_recv_ts, last_text
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    continue  # Skip binary messages
                
                try:
                    j = json.loads(msg)
                    msg_type = j.get("type", "")
                    
                    now = time.perf_counter()
                    
                    if msg_type == "Ready":
                        # Server ready - unblock streaming
                        ready_event.set()
                        continue
                    elif msg_type == "Step":
                        # Ignore server step messages
                        continue
                    elif msg_type == "Word":
                        # Word-level events - can print if desired
                        word = j.get("word", "")
                        if word:
                            print(f"WORD: {word}")
                    elif msg_type in ("Partial", "Text"):
                        # Running transcript
                        txt = j.get("text", "").strip()
                        if txt and txt != last_text:
                            partial_ts.append(now - t0)
                            print(f"PART: {txt}")
                            last_text = txt
                        if txt:
                            final_text = txt
                    elif msg_type in ("Marker", "Final"):
                        # End-of-utterance
                        txt = j.get("text", "").strip()
                        if txt:
                            final_text = txt
                        final_recv_ts = now
                        return
                    elif msg_type == "EndWord":
                        # Word end event, ignore for display
                        continue
                    else:
                        # Unknown message type, treat as potential text
                        txt = j.get("text", "").strip()
                        if txt and txt != last_text:
                            print(f"UNK: {txt}")
                            partial_ts.append(now - t0)
                            last_text = txt
                        if txt:
                            final_text = txt
                            
                except (json.JSONDecodeError, TypeError):
                    # Non-JSON message, ignore
                    continue

        recv_task = asyncio.create_task(receiver())

        # Wait for server Ready before streaming audio
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            print("Timeout waiting for server Ready signal")
            return

        if args.mode == "stream":
            for i in range(0, len(pcm), bytes_per_chunk):
                chunk = pcm[i:i+bytes_per_chunk]
                audio_frame = {
                    "type": "Audio",
                    "audio": base64.b64encode(chunk).decode('ascii')
                }
                await ws.send(json.dumps(audio_frame))
                last_chunk_sent_ts = time.perf_counter()
                await asyncio.sleep(chunk_ms / 1000.0 / args.rtf)
        else:
            big = 48000  # ~2 sec of 24k audio per frame
            for i in range(0, len(pcm), big):
                chunk = pcm[i:i+big]
                audio_frame = {
                    "type": "Audio",
                    "audio": base64.b64encode(chunk).decode('ascii')
                }
                await ws.send(json.dumps(audio_frame))
                last_chunk_sent_ts = time.perf_counter()

        await ws.send(json.dumps({"type": "Flush"}))
        await recv_task

    if final_text:
        print("\n=== Transcription Result ===")
        print(final_text)
    else:
        print("No final text")

    elapsed_s = time.perf_counter() - t0
    finalize_ms = ((final_recv_ts - last_chunk_sent_ts) * 1000.0) if (final_recv_ts and last_chunk_sent_ts) else 0.0
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0
    print(f"Elapsed: {elapsed_s:.3f}s  Partials: {len(partial_ts)}  Avg partial gap: {avg_gap_ms:.1f} ms  Finalize: {finalize_ms:.1f} ms")

    # metrics out
    out_dir = Path("test/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "client_metrics.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "elapsed_s": elapsed_s,
            "partials": len(partial_ts),
            "avg_partial_gap_ms": avg_gap_ms,
            "finalize_ms": finalize_ms,
            "file": os.path.basename(file_path),
            "server": args.server,
        }, ensure_ascii=False) + "\n")

def main() -> None:
    import asyncio
    asyncio.run(run(parse_args()))

if __name__ == "__main__":
    main()
