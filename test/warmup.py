from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))
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
    parser.add_argument("--max-seconds", type=float, default=210.0, help="Threshold to note partial; still saves result")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000")
    parser.add_argument("--ws", action="store_true", help="Use WebSocket /v1/realtime instead of HTTP")
    parser.add_argument("--no-pcm", action="store_true", help="Send original file (disable PCM mode) for HTTP")
    parser.add_argument("--raw", action="store_true", help="HTTP: send raw body (single-shot) instead of multipart")
    parser.add_argument("--timestamps", action="store_true", help="Request word timestamps in the same transaction (HTTP only)")
    args = parser.parse_args()

    file_path = find_sample_file(SAMPLES_DIR, args.file)
    if not file_path:
        print(f"Audio file '{args.file}' not found in {SAMPLES_DIR}/")
        return 2

    if args.ws:
        # WS realtime using utils
        from utils import file_to_pcm16_mono_16k
        import asyncio
        pcm = file_to_pcm16_mono_16k(file_path)
        from utils import ws_realtime_transcribe, to_ws_url
        ws_url = to_ws_url(args.url)
        t0 = time.perf_counter()
        text = asyncio.run(ws_realtime_transcribe(ws_url, pcm))
        elapsed_s = time.perf_counter() - t0
        data = {"text": text}
    else:
        # HTTP multipart; optionally send audio/pcm
        url = args.url.rstrip("/") + "/v1/audio/transcribe"
        from utils import build_http_multipart
        use_pcm = not args.no_pcm
        fname, content, ctype = build_http_multipart(file_path, use_pcm)
        with httpx.Client(timeout=60) as client:
            try:
                t0 = time.perf_counter()
                # Optionally request words+timestamps in the same transaction
                q = "?timestamps=1" if args.timestamps else ""
                if args.raw:
                    headers = {"content-type": ctype}
                    r = client.post(url + q, content=content, headers=headers)
                else:
                    files = {"file": (fname, content, ctype)}
                    r = client.post(url + q, files=files)
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
    # Prefer server-provided duration; fallback to local file duration
    try:
        duration = float(data.get("duration")) if isinstance(data.get("duration"), (int, float, str)) else 0.0
    except Exception:
        duration = 0.0
    if not duration or duration <= 0:
        from utils import file_duration_seconds
        duration = file_duration_seconds(file_path)
    
    if text:
        snippet = text[:50]
        print(f"Text: {snippet}...")
    else:
        print("No speech found")
    
    print(f"Audio duration: {duration:.4f}s")
    print(f"Transcription time: {elapsed_s:.4f}s")
    if duration and duration > 0 and elapsed_s > 0:
        rtf = elapsed_s / float(duration)
        if rtf > 0:
            xrt = 1.0 / rtf
            print(f"RTF: {rtf:.4f}  xRT: {xrt:.2f}x")

    # If audio exceeds threshold, note but still save the (partial) result
    if duration > args.max_seconds:
        print(f"Note: audio longer than {args.max_seconds}s — saving partial result")

    # If timestamps were not requested, drop words from the saved JSON for consistency
    if not args.timestamps and isinstance(data, dict) and "words" in data:
        try:
            if data.get("words") is None:
                data.pop("words", None)
        except Exception:
            pass

    # Write result to test/results/warmup.txt (overwrite)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps(data, ensure_ascii=False))
        out.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
