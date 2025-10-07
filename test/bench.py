#!/usr/bin/env python3
"""
Benchmark WebSocket streaming for Yap ASR server.

Streams PCM16@24k from audio files in JSON frames to simulate realtime voice.
Measures latency (wall), time-to-first-word, and throughput under concurrency.
"""
from __future__ import annotations
import argparse
import asyncio
import os
import time

from utils import (
    file_to_pcm16_mono_24k, file_duration_seconds, SAMPLES_DIR,
    find_sample_files, find_sample_by_name
)
from utils.metrics import summarize_results
from clients.benchmark import BenchmarkRunner


def main() -> None:
    ap = argparse.ArgumentParser(description="WebSocket streaming benchmark (Yap)")
    ap.add_argument("--server", default="127.0.0.1:8000", help="host:port or ws://host:port or full URL")
    ap.add_argument("--secure", action="store_true", help="(ignored unless you run wss)")
    ap.add_argument("--n", type=int, default=20, help="Total sessions")
    ap.add_argument("--concurrency", type=int, default=5, help="Max concurrent sessions")
    ap.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    ap.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    ap.add_argument("--kyutai-key", type=str, default=None, help="Kyutai API key (overrides KYUTAI_API_KEY env)")
    args = ap.parse_args()

    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    # Set API key if provided
    if args.kyutai_key:
        os.environ["KYUTAI_API_KEY"] = args.kyutai_key
    
    kyutai_key = os.getenv("KYUTAI_API_KEY")
    if not kyutai_key:
        print("Error: Kyutai API key missing. Use --kyutai-key or set KYUTAI_API_KEY env.")
        return

    print(f"Benchmark → WS (streaming) | n={args.n} | concurrency={args.concurrency} | rtf={args.rtf} | server={args.server}")
    print(f"File: {os.path.basename(file_path)}")

    # Load audio
    pcm = file_to_pcm16_mono_24k(file_path)
    
    # Run benchmark
    runner = BenchmarkRunner(args.server, args.secure, debug=False)
    
    t0 = time.time()
    results, rejected, errors = asyncio.run(
        runner.run_benchmark(pcm, args.n, args.concurrency, args.rtf)
    )
    elapsed = time.time() - t0

    # Print results
    summarize_results("WebSocket Streaming", results)
    print(f"Rejected: {rejected}")
    print(f"Errors: {errors}")
    print(f"Total elapsed: {elapsed:.4f}s")
    
    if results:
        total_audio = sum(r["audio_s"] for r in results)
        print(f"Total audio processed: {total_audio:.2f}s")
        print(f"Overall throughput: {total_audio/elapsed*60:.2f} sec/min = {total_audio/elapsed:.2f} min/min")

    # Save results
    runner.save_results(results)


if __name__ == "__main__":
    main()