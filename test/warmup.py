#!/usr/bin/env python3
"""
Warmup via Yap WebSocket streaming.

Quick health check for the Yap STT server.
"""
from __future__ import annotations
import argparse
import asyncio
import os
from pathlib import Path

from utils import file_to_pcm16_mono_24k, file_duration_seconds, SAMPLES_DIR
from clients.warmup import WarmupClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Warmup via Yap WebSocket streaming")
    parser.add_argument("--server", type=str, default="127.0.0.1:8000", help="host:port or ws://host:port or full URL")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file. Absolute path or name in samples/")
    parser.add_argument("--rtf", type=float, default=1000.0, help="Real-time factor (1000=fast warmup, 1.0=realtime)")
    parser.add_argument("--debug", action="store_true", help="Print debug info including raw server messages")
    parser.add_argument("--full-text", action="store_true", help="Print full transcribed text (default: truncate to 50 chars)")
    parser.add_argument("--kyutai-key", type=str, default=None, help="Kyutai API key (overrides KYUTAI_API_KEY env)")
    args = parser.parse_args()

    # Resolve path: allow absolute path; otherwise look under samples/
    candidate = Path(args.file)
    if candidate.is_absolute() and candidate.exists():
        audio_path = candidate
    else:
        audio_path = SAMPLES_DIR / args.file
    if not audio_path.exists():
        print(f"Audio not found: {audio_path}")
        return 2

    # Set API key if provided
    if args.kyutai_key:
        os.environ["KYUTAI_API_KEY"] = args.kyutai_key
    
    kyutai_key = os.getenv("KYUTAI_API_KEY")
    if not kyutai_key:
        print("Error: Kyutai API key missing. Use --kyutai-key or set KYUTAI_API_KEY env.")
        return 1

    # Load audio
    pcm_bytes = file_to_pcm16_mono_24k(str(audio_path))
    duration = file_duration_seconds(str(audio_path))

    # Run warmup
    client = WarmupClient(args.server, args.secure, debug=args.debug)
    res = asyncio.run(client.run_warmup(pcm_bytes, args.rtf, args.debug))

    # Print results
    if res.get("error"):
        print(f"Warmup error: {res['error']}")
    
    text = res.get('text', '')
    if args.full_text:
        print(f"Text: {text}")
    else:
        print(f"Text: {text[:50]}..." if len(text) > 50 else f"Text: {text}")
    print(f"Audio duration: {duration:.4f}s")
    print(f"Transcription time (to Final): {res.get('wall_to_final_s', 0.0):.4f}s")
    
    if duration > 0 and res.get('wall_to_final_s', 0.0) > 0:
        rtf = res["wall_to_final_s"] / duration
        xrt = (1.0/rtf) if rtf > 0 else 0.0
        print(f"RTF(measured): {rtf:.4f}  xRT: {xrt:.2f}x  (target={res.get('rtf_target')})")
    
    ttfw_ms = (res.get('ttfw_s', 0) * 1000.0) if res.get('ttfw_s') is not None else 0.0
    print(f"TTFW: {ttfw_ms:.1f}ms")
    print(f"Δ(audio): {res.get('delta_to_audio_ms', 0.0):.1f}ms")
    print(f"Partials: {res.get('partials', 0)}")
    print(f"Flush→Final: {res.get('finalize_ms', 0.0):.1f}ms")
    print(f"Decode tail: {res.get('decode_tail_ms', 0.0):.1f}ms")

    # Save results
    client.save_results(res, duration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())