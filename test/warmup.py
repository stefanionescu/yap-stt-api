from __future__ import annotations
import argparse
import asyncio
import contextlib
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
    """Generate WebSocket URL for Moshi server at root path"""
    if server.startswith("ws://") or server.startswith("wss://"):
        return server
    else:
        scheme = "wss" if secure else "ws"
        # Strip any existing paths - moshi server uses root path
        if "/" in server:
            server = server.split("/")[0]  # Keep only host:port
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

    # Moshi server doesn't need authentication headers
    ws_options = {
        "max_size": None,
        "compression": None,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_queue": 4,
        "write_limit": 2**22
    }

    t0 = time.perf_counter()
    async with websockets.connect(url, **ws_options) as ws:
        # No handshake needed - start streaming immediately
        done_event = asyncio.Event()
        final_seen = False

        async def receiver():
            nonlocal final_text, final_recv_ts, last_text, final_seen
            try:
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
                        
                        if msg_type == "Step":
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
                            final_seen = True
                            final_recv_ts = now
                            done_event.set()
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
            except websockets.exceptions.ConnectionClosedOK:
                # graceful close — okay
                if debug:
                    print("DEBUG: Connection closed gracefully")
                pass
            except websockets.exceptions.ConnectionClosedError as e:
                # server closed without a close frame — accept if we already saw final
                if debug:
                    print(f"DEBUG: Connection closed with error: {e}")
                if not final_seen:
                    raise

        recv_task = asyncio.create_task(receiver())

        # Start streaming immediately - no handshake needed
        if debug:
            print("DEBUG: Starting audio stream")

        if mode == "stream":
            for i in range(0, len(pcm_bytes), bytes_per_chunk):
                chunk = pcm_bytes[i:i+bytes_per_chunk]
                await ws.send(chunk)  # Send raw PCM bytes
                last_chunk_sent_ts = time.perf_counter()
                await asyncio.sleep(chunk_ms / 1000.0 / rtf)
        else:
            big = 48000  # ~2 sec of 24k audio per frame
            for i in range(0, len(pcm_bytes), big):
                chunk = pcm_bytes[i:i+big]
                await ws.send(chunk)  # Send raw PCM bytes
                last_chunk_sent_ts = time.perf_counter()

        await ws.send("Done")
        if debug:
            print("DEBUG: Sent Done")
        
        # Wait for server final (avoid indefinite waits)
        try:
            await asyncio.wait_for(done_event.wait(), timeout=10.0)
            if debug:
                print("DEBUG: Final received")
        except asyncio.TimeoutError:
            if debug:
                print("DEBUG: Timeout waiting for Final")
            pass
        
        # Proactively close; then await receiver task
        with contextlib.suppress(websockets.exceptions.ConnectionClosed, 
                                websockets.exceptions.ConnectionClosedError, 
                                websockets.exceptions.ConnectionClosedOK):
            await ws.close(code=1000, reason="client done")
        
        with contextlib.suppress(Exception):
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
    parser.add_argument("--server", type=str, default="localhost:8000", help="host:port or ws://host:port or full URL")
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

    if res.get("error"):
        print(f"Warmup error: {res['error']}")
    print(f"Text: {res.get('text', '')[:50]}...")
    print(f"Audio duration: {duration:.4f}s")
    print(f"Transcription time: {res.get('elapsed_s', 0.0):.4f}s")
    if duration > 0 and res.get('elapsed_s', 0.0) > 0:
        rtf = res["elapsed_s"] / duration
        xrt = (1.0/rtf) if rtf > 0 else 0.0
        print(f"RTF: {rtf:.4f}  xRT: {xrt:.2f}x")
    if args.mode == "stream":
        print(f"Partials: {res.get('partials', 0)}  Avg partial gap: {res.get('avg_partial_gap_ms', 0.0):.1f} ms  Finalize: {res.get('finalize_ms', 0.0):.1f} ms")

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
