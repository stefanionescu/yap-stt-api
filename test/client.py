#!/usr/bin/env python3
"""
Parakeet ASR WebSocket streaming client (sherpa-onnx).

Streams PCM16@16k from a file to simulate realtime voice and prints partials/final.
"""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path
import websockets

from utils import file_to_pcm16_mono_16k, file_duration_seconds

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
    parser = argparse.ArgumentParser(description="WebSocket sherpa-onnx client")
    parser.add_argument("--server", default=os.getenv("RIVA_SERVER", "localhost:8000"),
                        help="host:port or ws://host:port")
    parser.add_argument("--secure", action="store_true", help="Use WSS (requires cert on server)")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    parser.add_argument("--chunk-ms", type=int, default=120, help="Chunk size in ms for streaming")
    parser.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot ASR")
    return parser.parse_args()

def _ws_url(server: str, secure: bool) -> str:
    if server.startswith("ws://") or server.startswith("wss://"):
        return server
    scheme = "wss" if secure else "ws"
    return f"{scheme}://{server}"

async def run(args: argparse.Namespace) -> None:
    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    pcm = file_to_pcm16_mono_16k(file_path)
    duration = file_duration_seconds(file_path)

    url = _ws_url(args.server, args.secure)
    print(f"Connecting to: {url}")
    print(f"File: {os.path.basename(file_path)} ({duration:.2f}s)")

    bytes_per_ms = int(16000 * 2 / 1000)
    step = max(1, int(args.chunk_ms)) * bytes_per_ms

    partial_ts: list[float] = []
    last_chunk_sent_ts = 0.0
    final_recv_ts = 0.0
    final_text = ""
    last_text = ""

    t0 = time.perf_counter()
    async with websockets.connect(url, max_size=None) as ws:
        async def receiver():
            nonlocal final_text, final_recv_ts, last_text
            async for msg in ws:
                if msg == "Done!":
                    final_recv_ts = time.perf_counter()
                    return
                try:
                    j = json.loads(msg)
                    txt = j.get("text", "")
                except Exception:
                    continue
                now = time.perf_counter()
                if txt and txt != last_text:
                    partial_ts.append(now - t0)
                    print("PART:", txt)
                    last_text = txt
                if txt:
                    final_text = txt

        recv_task = asyncio.create_task(receiver())

        if args.mode == "stream":
            for i in range(0, len(pcm), step):
                await ws.send(pcm[i : i + step])
                last_chunk_sent_ts = time.perf_counter()
                await asyncio.sleep(args.chunk_ms / 1000.0)
        else:
            big = 64000
            for i in range(0, len(pcm), big):
                await ws.send(pcm[i : i + big])
                last_chunk_sent_ts = time.perf_counter()

        await ws.send("Done")
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
