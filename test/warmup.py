from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

SAMPLES_DIR = "samples"
EXTS = {".wav", ".flac", ".ogg", ".mp3"}
RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"


def find_sample_file(samples_dir: str) -> str | None:
    p = Path(samples_dir)
    if not p.exists():
        return None
    for root, _, files in os.walk(p):
        for f in files:
            if Path(f).suffix.lower() in EXTS:
                return str(Path(root) / f)
    return None


def find_sample_by_name(name: str, samples_dir: str) -> str | None:
    if not name:
        return None
    p = Path(samples_dir)
    if not p.exists():
        return None
    # Prefer exact basename match; if multiple, prefer .wav
    candidates: list[Path] = []
    for root, _, files in os.walk(p):
        for f in files:
            fp = Path(root) / f
            if fp.suffix.lower() in EXTS and fp.stem.lower() == name.lower():
                candidates.append(fp)
    if not candidates:
        return None
    candidates_sorted = sorted(candidates, key=lambda x: (x.suffix.lower() != ".wav", str(x)))
    return str(candidates_sorted[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default="", help="Absolute path to audio file")
    parser.add_argument("--name", type=str, default="mid", help="Sample base name in samples/ (auto-detect extension)")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000")
    args = parser.parse_args()

    file_path = args.file
    if not file_path:
        # If a name is provided (default: mid), prefer that inside samples/
        by_name = find_sample_by_name(args.name, SAMPLES_DIR)
        if by_name:
            file_path = by_name
        else:
            # Fallback: first audio in samples/
            file_path = find_sample_file(SAMPLES_DIR) or ""
            if not file_path:
                print("No audio file provided and no samples found.")
                return 2

    url = args.url.rstrip("/") + "/v1/transcribe"
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
        with httpx.Client(timeout=60) as client:
            r = client.post(url, files=files)
            r.raise_for_status()
            data = r.json()

    # Console print: first 50 characters or fallback message
    text = str((data.get("text") or "")).strip()
    if text:
        print(text[:50])
    else:
        print("No speech found")

    # Write result to test/results/warmup.txt (overwrite)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps(data, ensure_ascii=False))
        out.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
