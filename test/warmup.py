from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import riva.client  # type: ignore

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

    def audio_iter():
        yield riva.client.StreamingRecognizeRequest(streaming_config=scfg)
        # Always simulate realtime by sleeping per chunk duration
        import time as _t
        for i in range(0, len(pcm_bytes), step):
            chunk = pcm_bytes[i : i + step]
            yield riva.client.StreamingRecognizeRequest(audio_content=chunk)
            _t.sleep(max(0.0, args.chunk_ms / 1000.0))

    t0 = time.perf_counter()
    first_partial_ts = 0.0
    got_first_partial = False
    final_text = ""
    for resp in asr.streaming_response_generator(audio_chunks=audio_iter(), streaming_config=scfg):
        for r in resp.results:
            if not r.alternatives:
                continue
            alt = r.alternatives[0]
            if not got_first_partial and not r.is_final and alt.transcript:
                got_first_partial = True
                first_partial_ts = time.perf_counter()
            if r.is_final:
                final_text = alt.transcript

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

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps({"text": final_text, "duration": duration, "elapsed_s": elapsed_s, "ttfw_s": ttfw_s}, ensure_ascii=False))
        out.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
