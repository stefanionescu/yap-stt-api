#!/usr/bin/env python3
"""
Yap WebSocket streaming client.

Streams PCM16@24k from a file to simulate realtime voice and prints partials/final.
"""
from __future__ import annotations
import argparse
import asyncio
import os
from pathlib import Path

from utils import (
    file_to_pcm16_mono_24k, file_duration_seconds, SAMPLES_DIR,
    find_sample_files, find_sample_by_name
)
from clients.interactive import InteractiveClient

# Optionally load .env to pick up RUNPOD_* defaults if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(override=True)
except Exception:
    pass


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


async def run(args: argparse.Namespace) -> None:
    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    pcm = file_to_pcm16_mono_24k(file_path)
    client = InteractiveClient(args.server, args.secure, debug=False)
    
    await client.run_session(pcm, args.rtf, file_path)


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()