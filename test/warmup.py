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
RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"

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

async def _run(server: str, pcm_bytes: bytes, rtf: float, mode: str, debug: bool = False) -> dict:
    url = _ws_url(server, secure=False)
    
    # Moshi uses 24kHz, 80ms chunks
    samples_per_chunk = int(24000 * 0.080)  # 1920 samples
    bytes_per_chunk = samples_per_chunk * 2  # 3840 bytes
    chunk_ms = 80.0

    partial_ts = []
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
        if debug:
            print("DEBUG: Sent StartSTT handshake")

        async def receiver():
            nonlocal final_text, final_recv_ts, last_text
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    if debug:
                        print(f"DEBUG: Received binary message (length: {len(msg)})")
                    continue  # Skip binary messages
                
                try:
                    j = json.loads(msg)
                    msg_type = j.get("type", "")
                    
                    if debug:
                        print(f"DEBUG: Received {msg_type}: {j}")
                    
                    now = time.perf_counter()
                    
                    if msg_type == "Ready":
                        # Server ready - unblock streaming
                        if debug:
                            print("DEBUG: Server Ready received")
                        ready_event.set()
                        continue
                    elif msg_type == "Step":
                        # Ignore server step messages
                        continue
                    elif msg_type == "Word":
                        # First word for strict TTFW
                        if debug:
                            word = j.get("word", "")
                            print(f"DEBUG: Word: {word}")
                    elif msg_type in ("Partial", "Text"):
                        # Running transcript
                        txt = j.get("text", "").strip()
                        if txt and txt != last_text:
                            partial_ts.append(now - t0)
                            last_text = txt
                            if debug:
                                print(f"DEBUG: New partial text: '{txt}'")
                        if txt:
                            final_text = txt
                    elif msg_type in ("Marker", "Final"):
                        # End-of-utterance
                        txt = j.get("text", "").strip()
                        if txt:
                            final_text = txt
                        final_recv_ts = now
                        if debug:
                            print(f"DEBUG: Final message received, text: '{txt}'")
                        return
                    elif msg_type == "EndWord":
                        # Word end event, ignore for metrics
                        continue
                    else:
                        # Unknown message type, treat as potential text
                        txt = j.get("text", "").strip()
                        if txt and txt != last_text:
                            partial_ts.append(now - t0)
                            last_text = txt
                            if debug:
                                print(f"DEBUG: Unknown message type '{msg_type}' with text: '{txt}'")
                        if txt:
                            final_text = txt
                            
                except (json.JSONDecodeError, TypeError):
                    # Non-JSON message, ignore
                    if debug:
                        print(f"DEBUG: Non-JSON message: {repr(msg)}")
                    continue

        recv_task = asyncio.create_task(receiver())

        # Wait for server Ready before streaming audio
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=10.0)
            if debug:
                print("DEBUG: Ready received, starting audio stream")
        except asyncio.TimeoutError:
            if debug:
                print("DEBUG: Timeout waiting for server Ready signal")
            return {"error": "timeout_waiting_for_ready"}

        if mode == "stream":
            for i in range(0, len(pcm_bytes), bytes_per_chunk):
                chunk = pcm_bytes[i:i+bytes_per_chunk]
                audio_frame = {
                    "type": "Audio",
                    "audio": base64.b64encode(chunk).decode('ascii')
                }
                await ws.send(json.dumps(audio_frame))
                last_chunk_sent_ts = time.perf_counter()
                await asyncio.sleep(chunk_ms / 1000.0 / rtf)
        else:
            big = 48000  # ~2 sec of 24k audio per frame
            for i in range(0, len(pcm_bytes), big):
                chunk = pcm_bytes[i:i+big]
                audio_frame = {
                    "type": "Audio",
                    "audio": base64.b64encode(chunk).decode('ascii')
                }
                await ws.send(json.dumps(audio_frame))
                last_chunk_sent_ts = time.perf_counter()

        await ws.send(json.dumps({"type": "Flush"}))
        if debug:
            print("DEBUG: Sent Flush")
        await recv_task

    elapsed_s = time.perf_counter() - t0
    finalize_ms = ((final_recv_ts - last_chunk_sent_ts) * 1000.0) if (final_recv_ts and last_chunk_sent_ts) else 0.0
    avg_gap_ms = 0.0
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0

    return {
        "text": final_text,
        "elapsed_s": elapsed_s,
        "partials": len(partial_ts) if mode == "stream" else 0,
        "avg_partial_gap_ms": avg_gap_ms if mode == "stream" else 0.0,
        "finalize_ms": finalize_ms if mode == "stream" else 0.0,
        "mode": mode,
        "rtf": rtf,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Warmup via Moshi WebSocket streaming")
    parser.add_argument("--server", type=str, default="localhost:8000/api/asr-streaming", help="host:port or ws://host:port or full URL")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file. Absolute path or name in samples/")
    parser.add_argument("--rtf", type=float, default=1000.0, help="Real-time factor (1000=fast warmup, 1.0=realtime)")
    parser.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot ASR")
    parser.add_argument("--debug", action="store_true", help="Print debug info including raw server messages")
    args = parser.parse_args()

    # Resolve path: allow absolute path; otherwise look under samples/
    candidate = Path(args.file)
    if candidate.is_absolute() and candidate.exists():
        audio_path = candidate
    else:
        audio_path = Path(SAMPLES_DIR) / args.file
    if not audio_path.exists():
        print(f"Audio not found: {audio_path}")
        return 2

    pcm_bytes = file_to_pcm16_mono_24k(str(audio_path))
    duration = file_duration_seconds(str(audio_path))

    res = asyncio.run(_run(args.server, pcm_bytes, args.rtf, args.mode, args.debug))

    print(f"Text: {res['text'][:50]}...")
    print(f"Audio duration: {duration:.4f}s")
    print(f"Transcription time: {res['elapsed_s']:.4f}s")
    if duration > 0:
        rtf = res["elapsed_s"] / duration
        xrt = (1.0/rtf) if rtf > 0 else 0.0
        print(f"RTF: {rtf:.4f}  xRT: {xrt:.2f}x")
    if args.mode == "stream":
        print(f"Partials: {res['partials']}  Avg partial gap: {res['avg_partial_gap_ms']:.1f} ms  Finalize: {res['finalize_ms']:.1f} ms")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps({
            **res,
            "duration": duration,
        }, ensure_ascii=False))
        out.write("\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
