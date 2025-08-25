#!/usr/bin/env python3
"""
Parakeet ASR gRPC client (Riva-compatible) — segmented one-shot or plain one-shot.

Runs PCM16@16k from a file in 2.2s segments with 200ms overlap and prints finals,
or runs a single one-shot request for the whole file.
"""
import argparse
import os
from pathlib import Path

import riva.client  # type: ignore
import time
import json
from segmentation import build_segments
from merge import merge_segment

from utils import file_to_pcm16_mono_16k, file_duration_seconds
import numpy as np


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
    parser.add_argument("--mode", choices=["segmented", "oneshot"], default="segmented", help="Run segmented one-shot or plain one-shot")
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
        enable_automatic_punctuation=True,
    )
    
    print(f"Connecting to: {args.server}")
    print(f"File: {os.path.basename(file_path)} ({duration:.2f}s)")

    final_text = ""
    t0 = time.perf_counter()
    try:
        if args.mode == "oneshot":
            # Plain one-shot for the entire file
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
        else:
            # Segmented one-shot with silence-aware cuts and token-overlap merge
            wav = np.frombuffer(pcm, dtype=np.int16)
            sr = 16000
            edges = build_segments(
                wav,
                sr=sr,
                seg_ms=2200,
                min_ms=1200,
                overlap_ms=200,
                vad_window_ms=400,
                vad_thr=1.2e-3,
                vad_frame_ms=20,
            )

            merged_tokens: list[str] = []
            t_start = time.perf_counter()
            last_resp_ts = t_start
            for (s, e, ovl) in edges:
                # Pace to real-time boundary for the cut
                cut_time = t_start + (e / float(sr))
                now = time.perf_counter()
                if cut_time > now:
                    time.sleep(cut_time - now)
                seg = wav[s:min(e + ovl, len(wav))]
                pcm_seg = seg.astype(np.int16).tobytes()
                try:
                    try:
                        resp = asr.offline_recognize(pcm_seg, cfg)  # type: ignore[arg-type]
                    except TypeError:
                        try:
                            resp = asr.offline_recognize(audio=pcm_seg, config=cfg)  # type: ignore[call-arg]
                        except AttributeError:
                            resp = asr.recognize(pcm_seg, cfg)  # type: ignore[arg-type]
                    seg_txt = ""
                    for r in getattr(resp, "results", []) or []:
                        if getattr(r, "alternatives", None):
                            seg_txt = getattr(r.alternatives[0], "transcript", "") or ""
                            break
                    if seg_txt:
                        final_text = merge_segment(merged_tokens, seg_txt, max_overlap_tokens=10)
                        print("FINAL(seg):", seg_txt.strip())
                finally:
                    last_resp_ts = time.perf_counter()
            final_recv_ts = last_resp_ts
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
    if args.mode == "segmented":
        last_audio_ts = t0 + duration
        finalize_ms = max(0.0, (final_recv_ts - last_audio_ts) * 1000.0)
        print(f"Elapsed: {elapsed_s:.3f}s  Finalize: {finalize_ms:.1f} ms")
        rtf = elapsed_s / duration if duration > 0 else 0.0
        xrt = (duration / elapsed_s) if elapsed_s > 0 else 0.0
    else:
        finalize_ms = 0.0
        rtf = elapsed_s / duration if duration > 0 else 0.0
        xrt = (duration / elapsed_s) if elapsed_s > 0 else 0.0
        print(f"Elapsed: {elapsed_s:.3f}s  RTF: {rtf:.4f}  xRT: {xrt:.2f}x")

    # Write single-record JSONL (overwrite each run)
    try:
        out_dir = Path("test/results")
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "client_metrics.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "elapsed_s": elapsed_s,
                "finalize_ms": finalize_ms,
                "file": os.path.basename(file_path),
                "server": args.server,
                "mode": args.mode,
                "rtf": rtf,
                "xrt": xrt,
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Warning: could not write client metrics: {e}")


if __name__ == "__main__":
    main()
