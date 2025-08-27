from __future__ import annotations
import argparse
import asyncio
import json
import time
from pathlib import Path
import websockets

from utils import file_to_pcm16_mono_16k, file_duration_seconds

SAMPLES_DIR = "samples"
RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"

def _ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Sherpa-ONNX server (no special endpoints needed)"""
    if server.startswith("ws://") or server.startswith("wss://"):
        return server
    else:
        scheme = "wss" if secure else "ws"
        return f"{scheme}://{server}"

async def _run(server: str, pcm_bytes: bytes, chunk_ms: int, mode: str, debug: bool = False) -> dict:
    url = _ws_url(server, secure=False)
    bytes_per_ms = int(16000 * 2 / 1000)
    step = max(1, int(chunk_ms)) * bytes_per_ms

    partial_ts = []
    last_chunk_sent_ts = 0.0
    final_recv_ts = 0.0
    final_text = ""
    last_text = ""

    t0 = time.perf_counter()
    async with websockets.connect(url, max_size=None) as ws:
        # Send an initial config/start message so the server knows our audio format
        # Keys are chosen to be broadly compatible across sherpa-onnx versions.
        start_cfg = {
            "type": "start",
            "config": {
                "sample_rate": 16000,
                "channels": 1,
                "bits_per_sample": 16,
                "format": "s16le",
                # Decoding hints (ignored if unsupported)
                "decoding_method": "greedy_search",
                "max_active_paths": 4,
            }
        }
        try:
            await ws.send(json.dumps(start_cfg))
            if debug:
                print(f"DEBUG: Sent start config: {start_cfg}")
        except Exception:
            # Older servers may not expect a start message; ignore failures
            if debug:
                print("DEBUG: Start config not accepted (ignored)")
        async def receiver():
            nonlocal final_text, final_recv_ts, last_text
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    if debug:
                        print(f"DEBUG: Received binary message (length: {len(msg)})")
                    continue  # Skip binary messages
                
                if debug:
                    print(f"DEBUG: Received message: {repr(msg)}")
                
                # Handle end signals (various formats Sherpa-ONNX might use)
                if msg.lower().strip() in ("done", "done!", "", "end"):
                    if debug:
                        print("DEBUG: Received end signal")
                    final_recv_ts = time.perf_counter()
                    return
                
                # Extract text from message (try multiple JSON formats)
                txt = ""
                try:
                    j = json.loads(msg)
                    # Try different possible text fields
                    txt = (j.get("text", "") or 
                           j.get("result", {}).get("text", "") if isinstance(j.get("result"), dict) else "" or
                           j.get("alternatives", [{}])[0].get("transcript", "") if j.get("alternatives") else "")
                    
                    if debug and j:
                        print(f"DEBUG: Parsed JSON: {j}")
                        print(f"DEBUG: Extracted text: '{txt}'")
                        
                except (json.JSONDecodeError, TypeError):
                    # Treat as plain text response
                    txt = msg.strip()
                    if debug:
                        print(f"DEBUG: Treating as plain text: '{txt}'")
                
                now = time.perf_counter()
                if txt and txt != last_text:
                    partial_ts.append(now - t0)
                    last_text = txt
                    if debug:
                        print(f"DEBUG: New partial text: '{txt}'")
                if txt:
                    final_text = txt

        recv_task = asyncio.create_task(receiver())

        if mode == "stream":
            for i in range(0, len(pcm_bytes), step):
                await ws.send(pcm_bytes[i:i+step])
                last_chunk_sent_ts = time.perf_counter()
                await asyncio.sleep(chunk_ms/1000.0)
        else:
            big = 64000
            for i in range(0, len(pcm_bytes), big):
                await ws.send(pcm_bytes[i:i+big])
                last_chunk_sent_ts = time.perf_counter()

        await ws.send("Done")
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
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Warmup via Sherpa-ONNX WebSocket streaming (realtime)")
    parser.add_argument("--server", type=str, default="localhost:8000", help="host:port or ws://host:port")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file. Absolute path or name in samples/")
    parser.add_argument("--chunk-ms", type=int, default=100, help="Chunk size in ms for streaming")
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

    pcm_bytes = file_to_pcm16_mono_16k(str(audio_path))
    duration = file_duration_seconds(str(audio_path))

    res = asyncio.run(_run(args.server, pcm_bytes, args.chunk_ms, args.mode, args.debug))

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
