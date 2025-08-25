from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import riva.client  # type: ignore
import numpy as np
from segmentation import build_segments
from merge import merge_segment

from utils import file_to_pcm16_mono_16k, file_duration_seconds


SAMPLES_DIR = "samples"
RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description="Warmup via Riva gRPC (segmented or oneshot)")
    parser.add_argument("--server", type=str, default="localhost:8000")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--file", type=str, default="mid.wav", help="Filename in samples/ directory")
    parser.add_argument("--mode", choices=["segmented", "oneshot"], default="segmented")
    args = parser.parse_args()

    audio_path = Path(SAMPLES_DIR) / args.file
    if not audio_path.exists():
        print(f"Audio not found: {audio_path}")
        return 2

    pcm_bytes = file_to_pcm16_mono_16k(str(audio_path))
    duration = file_duration_seconds(str(audio_path))

    auth = riva.client.Auth(ssl_cert=None, use_ssl=bool(args.secure), uri=args.server)
    asr = riva.client.ASRService(auth)

    cfg = riva.client.RecognitionConfig(
        encoding=riva.client.AudioEncoding.LINEAR_PCM,
        sample_rate_hertz=16000,
        language_code="en-US",
        max_alternatives=1,
        enable_automatic_punctuation=True,
    )

    t0 = time.perf_counter()
    final_text = ""
    if args.mode == "oneshot":
        try:
            try:
                resp = asr.offline_recognize(pcm_bytes, cfg)  # type: ignore[arg-type]
            except TypeError:
                try:
                    resp = asr.offline_recognize(audio=pcm_bytes, config=cfg)  # type: ignore[call-arg]
                except AttributeError:
                    resp = asr.recognize(pcm_bytes, cfg)  # type: ignore[arg-type]
            for r in getattr(resp, "results", []) or []:
                if getattr(r, "alternatives", None):
                    alt = r.alternatives[0]
                    final_text = getattr(alt, "transcript", "") or ""
                    break
        finally:
            pass
        final_recv_ts = time.perf_counter()
    else:
        # Segmented path with silence-aware cuts and token-overlap merge
        wav = np.frombuffer(pcm_bytes, dtype=np.int16)
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
                else:
                    final_text = "".join(merged_tokens)
            finally:
                last_resp_ts = time.perf_counter()
        final_recv_ts = last_resp_ts

    elapsed_s = time.perf_counter() - t0
    print(f"Text: {final_text[:50]}...")
    print(f"Audio duration: {duration:.4f}s")
    print(f"Transcription time: {elapsed_s:.4f}s")
    last_audio_ts = t0 + duration
    finalize_ms = max(0.0, (final_recv_ts - last_audio_ts) * 1000.0)
    print(f"Finalize: {finalize_ms:.1f} ms")
    rtf = elapsed_s / duration if duration > 0 else 0.0
    xrt = (duration / elapsed_s) if elapsed_s > 0 else 0.0
    if args.mode == "oneshot":
        print(f"RTF: {rtf:.4f}  xRT: {xrt:.2f}x")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps({
            "text": final_text,
            "duration": duration,
            "elapsed_s": elapsed_s,
            "finalize_ms": finalize_ms,
            "mode": args.mode,
            "rtf": rtf,
            "xrt": xrt,
        }, ensure_ascii=False))
        out.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
