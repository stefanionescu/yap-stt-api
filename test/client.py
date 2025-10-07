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

# Load .env (repo root) to pick up RUNPOD_* and keys, with fallback if python-dotenv is absent
repo_root = Path(__file__).resolve().parents[1]

def _load_env_file_fallback(env_path: Path) -> None:
    try:
        if not env_path.exists():
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # Only set if not already defined in environment
                if k and (k not in os.environ):
                    os.environ[k] = v
    except Exception:
        # Silent fallback; do not crash on malformed lines
        pass

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(dotenv_path=repo_root / ".env", override=False)
except Exception:
    _load_env_file_fallback(repo_root / ".env")
else:
    # Ensure values exist even if python-dotenv wasn't installed or didn't override
    _load_env_file_fallback(repo_root / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocket Yap client")
    # Resolve server from env; prefer RunPod host, then YAP_SERVER, else localhost
    runpod_host = (
        os.getenv("RUNPOD_TCP_HOST")
        or os.getenv("RUNPOD_HOST")
        or os.getenv("RUNPOD_SERVER")
    )
    runpod_port = os.getenv("RUNPOD_TCP_PORT") or os.getenv("RUNPOD_PORT") or "8000"
    default_server = (
        f"{runpod_host}:{runpod_port}" if runpod_host else os.getenv("YAP_SERVER", "127.0.0.1:8000")
    )
    parser.add_argument(
        "--server",
        default=default_server,
        help="host:port or ws://host:port or full URL (env: RUNPOD_TCP_HOST/PORT or YAP_SERVER)",
    )
    parser.add_argument("--secure", action="store_true", help="Use WSS (requires cert on server)")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    parser.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    parser.add_argument("--kyutai-key", type=str, default=None, help="Kyutai API key (overrides KYUTAI_API_KEY env)")
    parser.add_argument("--runpod-key", type=str, default=None, help="RunPod API token (overrides RUNPOD_API_KEY env)")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    # Apply optional key overrides from flags to environment for downstream clients
    if args.kyutai_key:
        os.environ["KYUTAI_API_KEY"] = args.kyutai_key
    if args.runpod_key:
        os.environ["RUNPOD_API_KEY"] = args.runpod_key

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    pcm = file_to_pcm16_mono_24k(file_path)
    client = InteractiveClient(args.server, args.secure, debug=False, quiet=True, save_metrics=False)
    
    await client.run_session(pcm, args.rtf, file_path)


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()