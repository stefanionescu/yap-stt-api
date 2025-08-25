from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import riva.client  # type: ignore
import json

from utils import file_to_pcm16_mono_16k, file_duration_seconds


SAMPLES_DIR = "samples"
RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description="Warmup via Riva gRPC streaming (realtime)")
    parser.add_argument("--server", type=str, default="localhost:8000")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--file", type=str, default="mid.wav", help="Filename in samples/ directory")
    parser.add_argument("--chunk-ms", type=int, default=50, help="Chunk size in ms for streaming")
    parser.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot ASR")
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
        # Always simulate realtime by sleeping per chunk duration
        import time as _t
        for i in range(0, len(pcm_bytes), step):
            chunk = pcm_bytes[i : i + step]
            yield riva.client.StreamingRecognizeRequest(audio_content=chunk)
            last_chunk_sent_ts = _t.perf_counter() if hasattr(_t, "perf_counter") else _t.time()
            _t.sleep(max(0.0, args.chunk_ms / 1000.0))

    t0 = time.perf_counter()
    first_partial_ts = 0.0
    got_first_partial = False
    final_text = ""
    if args.mode == "stream":
        for resp in asr.streaming_response_generator(audio_chunks=audio_iter(), streaming_config=scfg):
            for r in resp.results:
                if not r.alternatives:
                    continue
                alt = r.alternatives[0]
                if not r.is_final and alt.transcript:
                    partial_ts.append(time.perf_counter() - t0)
                if not got_first_partial and not r.is_final and alt.transcript:
                    got_first_partial = True
                    first_partial_ts = time.perf_counter()
                if r.is_final:
                    final_text = alt.transcript
                    final_recv_ts = time.perf_counter()
    else:
        # One-shot
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

    elapsed_s = time.perf_counter() - t0
    ttfw_s = (first_partial_ts - t0) if got_first_partial else 0.0

    print(f"Text: {final_text[:50]}...")
    print(f"Audio duration: {duration:.4f}s")
    print(f"Transcription time: {elapsed_s:.4f}s")
    if ttfw_s:
        print(f"Time to first word: {ttfw_s:.4f}s")
    if duration > 0:
        rtf = elapsed_s / duration
        if rtf > 0:
            print(f"RTF: {rtf:.4f}  xRT: {1.0/rtf:.2f}x")

    # Derived metrics
    finalize_ms = ((final_recv_ts - last_chunk_sent_ts) * 1000.0) if (final_recv_ts and last_chunk_sent_ts) else 0.0
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
    else:
        avg_gap_ms = 0.0
    partials = len(partial_ts)
    if args.mode == "stream":
        print(f"Partials: {partials}  Avg partial gap: {avg_gap_ms:.1f} ms  Finalize: {finalize_ms:.1f} ms")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps({
            "text": final_text,
            "duration": duration,
            "elapsed_s": elapsed_s,
            "ttfw_s": ttfw_s,
            "partials": partials if args.mode == "stream" else 0,
            "avg_partial_gap_ms": avg_gap_ms if args.mode == "stream" else 0.0,
            "finalize_ms": finalize_ms if args.mode == "stream" else 0.0,
            "mode": args.mode,
        }, ensure_ascii=False))
        out.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
