#!/usr/bin/env python3
"""
Parakeet ASR gRPC streaming client (Riva-compatible).

Streams PCM16@16k from a file to simulate realtime voice and prints partials/final.
"""
import argparse
import os
from pathlib import Path

import riva.client  # type: ignore
import time
import json

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
    parser = argparse.ArgumentParser(description="gRPC Parakeet ASR client (Riva)")
    parser.add_argument("--server", default=os.getenv("RIVA_SERVER", "localhost:8000"))
    parser.add_argument("--secure", action="store_true", help="Use TLS")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    parser.add_argument("--chunk-ms", type=int, default=50, help="Chunk size in ms for streaming")
    parser.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot ASR")
    # Always stream in realtime
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    pcm = file_to_pcm16_mono_16k(file_path)
    duration = file_duration_seconds(file_path)

    auth = riva.client.Auth(ssl_cert=None, use_ssl=bool(args.secure), uri=args.server)
    asr = riva.client.ASRService(auth)

    cfg = riva.client.RecognitionConfig(
        encoding=riva.client.AudioEncoding.LINEAR_PCM,
        sample_rate_hertz=16000,
        language_code="en-US",
        max_alternatives=1,
        enable_automatic_punctuation=False,
    )
    scfg = riva.client.StreamingRecognitionConfig(config=cfg, interim_results=True)

    bytes_per_ms = int(16000 * 2 / 1000)
    step = max(1, int(args.chunk_ms)) * bytes_per_ms

    partial_ts: list[float] = []
    last_chunk_sent_ts = 0.0
    final_recv_ts = 0.0

    def audio_iter():
        yield riva.client.StreamingRecognizeRequest(streaming_config=scfg)
        import time as _t
        for i in range(0, len(pcm), step):
            chunk = pcm[i : i + step]
            yield riva.client.StreamingRecognizeRequest(audio_content=chunk)
            last_chunk_sent_ts = _t.perf_counter() if hasattr(_t, "perf_counter") else _t.time()
            _t.sleep(max(0.0, args.chunk_ms / 1000.0))

    print(f"Connecting to: {args.server}")
    print(f"File: {os.path.basename(file_path)} ({duration:.2f}s)")

    final_text = ""
    t0 = time.perf_counter()
    try:
        if args.mode == "stream":
            for resp in asr.streaming_response_generator(audio_chunks=audio_iter(), streaming_config=scfg):
                for r in resp.results:
                    if not r.alternatives:
                        continue
                    alt = r.alternatives[0]
                    if r.is_final:
                        final_text = alt.transcript
                        final_recv_ts = time.perf_counter()
                        print("FINAL:", final_text)
                    else:
                        partial_ts.append(time.perf_counter() - t0)
                        print("PART:", alt.transcript)
        else:
            # One-shot
            try:
                try:
                    resp = asr.offline_recognize(pcm, cfg)  # type: ignore[arg-type]
                except TypeError:
                    try:
                        resp = asr.offline_recognize(audio=pcm, config=cfg)  # type: ignore[call-arg]
                    except AttributeError:
                        resp = asr.recognize(pcm, cfg)  # type: ignore[arg-type]
                for r in getattr(resp, "results", []) or []:
                    if getattr(r, "alternatives", None):
                        alt = r.alternatives[0]
                        final_text = getattr(alt, "transcript", "") or ""
                        break
            finally:
                pass
    except Exception as e:
        print(f"Error: {e}")
        return

    if final_text:
        print("\n=== Transcription Result ===")
        print(final_text)
    else:
        print("No final text")

    # Metrics
    elapsed_s = time.perf_counter() - t0
    finalize_ms = ((final_recv_ts - last_chunk_sent_ts) * 1000.0) if (final_recv_ts and last_chunk_sent_ts) else 0.0
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0
    print(f"Elapsed: {elapsed_s:.3f}s  Partials: {len(partial_ts)}  Avg partial gap: {avg_gap_ms:.1f} ms  Finalize: {finalize_ms:.1f} ms")

    # Write single-record JSONL (overwrite each run)
    try:
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
    except Exception as e:
        print(f"Warning: could not write client metrics: {e}")


if __name__ == "__main__":
    main()
