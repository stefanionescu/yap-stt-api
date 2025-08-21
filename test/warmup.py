from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
import time

SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}
RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"


def find_sample_file(samples_dir: str, filename: str = "") -> str | None:
    p = Path(samples_dir)
    if not p.exists():
        return None
    
    # If specific filename provided, look for exact match
    if filename:
        target = p / filename
        if target.exists() and target.suffix.lower() in EXTS:
            return str(target)
        return None
    
    # Otherwise find first audio file
    for root, _, files in os.walk(p):
        for f in files:
            if Path(f).suffix.lower() in EXTS:
                return str(Path(root) / f)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default="mid.wav", help="Filename in samples/ directory (e.g., mid.wav, long.mp3)")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000")
    args = parser.parse_args()

    file_path = find_sample_file(SAMPLES_DIR, args.file)
    if not file_path:
        print(f"Audio file '{args.file}' not found in {SAMPLES_DIR}/")
        return 2

    url = args.url.rstrip("/") + "/v1/transcribe"
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
        with httpx.Client(timeout=60) as client:
            try:
                t0 = time.perf_counter()
                r = client.post(url, files=files)
                r.raise_for_status()
                data = r.json()
                elapsed_s = time.perf_counter() - t0
            except httpx.HTTPStatusError as e:
                resp = e.response
                ct = resp.headers.get("content-type", "")
                body = resp.text
                print(f"HTTP {resp.status_code} error from server")
                if "application/json" in ct:
                    try:
                        print(resp.json())
                    except Exception:
                        print(body[:500])
                else:
                    print(body[:500])
                return 1

    # Console print: first 50 characters or fallback message
    text = str((data.get("text") or "")).strip()
    duration = data.get("duration", 0.0)
    
    if text:
        print(f"Text: {text[:50]}")
    else:
        print("No speech found")
    
    print(f"Audio duration: {duration:.4f}s")
    try:
        print(f"Transcription time: {elapsed_s:.4f}s")
    except NameError:
        pass

    # Write result to test/results/warmup.txt (overwrite)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps(data, ensure_ascii=False))
        out.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
