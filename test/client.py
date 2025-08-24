#!/usr/bin/env python3
"""
Parakeet ASR HTTP client for transcribing audio files via TCP endpoint.

Examples:
  # Default: transcribe samples/mid.wav using TCP endpoint from .env
  python test/client.py

  # Specific file from samples/
  python test/client.py --file long.mp3

  # Custom host/port (overrides .env)
  python test/client.py --host <RUNPOD_PUBLIC_IP> --port 8000 --file short-noisy.wav

Reads RUNPOD_TCP_HOST and RUNPOD_TCP_PORT from .env by default.
Prints the full transcribed text to console.
"""
import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    # dotenv is optional; just use env vars directly
    pass


SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}


def find_sample_files() -> list[str]:
    """Find all audio files in samples/ directory."""
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
    """Find specific file in samples/ directory."""
    target = Path(SAMPLES_DIR) / filename
    if target.exists() and target.suffix.lower() in EXTS:
        return str(target)
    return None


def _sanitize_host(host: str) -> tuple[str, bool]:
    """Strip scheme and return (host, use_https)."""
    if not host:
        return "", False
    
    # Parse URL to extract scheme and host
    if "://" not in host:
        host = f"http://{host}"
    
    parsed = urlparse(host)
    use_https = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path.strip("/")
    
    return netloc, use_https


def _is_runpod_proxy_host(host: str) -> bool:
    """Check if this looks like a RunPod proxy URL."""
    h = host.lower()
    return ("proxy.runpod.net" in h) or h.endswith("runpod.net")


async def transcribe_file(host: str, port: int, file_path: str, use_https: bool = False, timestamps: bool = False) -> dict:
    """Send file to transcription API and return response."""
    # Build URL
    scheme = "https" if use_https else "http"
    
    # Handle RunPod proxy (no explicit port) vs direct TCP
    if _is_runpod_proxy_host(host):
        url = f"https://{host}/v1/transcribe"
    else:
        # Direct TCP endpoint
        if ":" in host:
            url = f"{scheme}://{host}/v1/transcribe"
        else:
            url = f"{scheme}://{host}:{port}/v1/transcribe"
    
    print(f"Connecting to: {url}")
    print(f"File: {file_path} ({Path(file_path).stat().st_size / 1024 / 1024:.2f} MB)")
    
    # Prepare headers with API key if available
    headers = {}
    api_key = os.getenv("RUNPOD_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    t0 = time.time()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
            q = "?timestamps=1" if timestamps else ""
            response = await client.post(url + q, files=files)
        
        elapsed = time.time() - t0
        
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
            return {}
        
        data = response.json()
        
        print(f"\n=== Transcription Result ===")
        print(f"Text: {data.get('text', '')}")
        print(f"Audio duration: {data.get('duration', 0.0):.4f}s")
        print(f"Processing time: {elapsed:.4f}s")
        print(f"Real-time factor: {elapsed / data.get('duration', 1.0):.4f}")
        print(f"Model: {data.get('model', 'unknown')}")
        
        return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HTTP Parakeet ASR client")
    parser.add_argument(
        "--host",
        default=os.getenv("RUNPOD_TCP_HOST", "localhost"),
        help="API host (defaults to RUNPOD_TCP_HOST or localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("RUNPOD_TCP_PORT", "8000")),
        help="API port (defaults to RUNPOD_TCP_PORT or 8000)",
    )
    parser.add_argument(
        "--file", 
        type=str, 
        default="mid.wav", 
        help="Audio file from samples/ directory (default: mid.wav)"
    )
    parser.add_argument(
        "--https", 
        action="store_true", 
        help="Use HTTPS (auto-detected for RunPod proxy)"
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Request word timestamps in the same transaction (HTTP)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    # Find the audio file
    if args.file:
        file_path = find_sample_by_name(args.file)
        if not file_path:
            print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
            available = find_sample_files()
            if available:
                print(f"Available files: {[os.path.basename(f) for f in available]}")
            return
    else:
        available = find_sample_files()
        if not available:
            print(f"No audio files found in {SAMPLES_DIR}/")
            return
        file_path = available[0]
        print(f"Using first available file: {os.path.basename(file_path)}")
    
    # Determine host and HTTPS usage
    clean_host, use_https_from_scheme = _sanitize_host(args.host)
    use_https = args.https or use_https_from_scheme or _is_runpod_proxy_host(clean_host)
    
    try:
        result = asyncio.run(transcribe_file(clean_host, args.port, file_path, use_https, args.timestamps))
        if not result:
            sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
