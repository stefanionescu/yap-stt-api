from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx


def find_sample_file(samples_dir: str) -> str | None:
    exts = {".wav", ".flac", ".ogg", ".mp3"}
    p = Path(samples_dir)
    if not p.exists():
        return None
    for root, _, files in os.walk(p):
        for f in files:
            if Path(f).suffix.lower() in exts:
                return str(Path(root) / f)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default="")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000")
    args = parser.parse_args()

    file_path = args.file
    if not file_path:
        file_path = find_sample_file("samples") or ""
        if not file_path:
            print("No audio file provided and no samples found.")
            return 2

    url = args.url.rstrip("/") + "/v1/transcribe"
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
        with httpx.Client(timeout=60) as client:
            r = client.post(url, files=files)
            r.raise_for_status()
            print(r.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
