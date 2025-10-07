#!/usr/bin/env python3
"""
Yap WebSocket streaming client.

Streams PCM16@24k from a file to simulate realtime voice and prints partials/final.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import json
import os
import time
from pathlib import Path
import websockets

from utils import (
    file_to_pcm16_mono_24k, file_duration_seconds, SAMPLES_DIR, EXTS,
    find_sample_files, find_sample_by_name, ws_url, is_runpod_host,
    AudioStreamer, ClientMessageHandler
)

# Optionally load .env to pick up RUNPOD_* defaults if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(override=True)
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocket Yap client")
    # Prefer RUNPOD_TCP_HOST/PORT when available, else fall back to YAP_SERVER or localhost
    runpod_host = os.getenv("RUNPOD_TCP_HOST")
    runpod_port = os.getenv("RUNPOD_TCP_PORT") or "8000"
    if runpod_host:
        default_server = f"{runpod_host}:{runpod_port}"
    else:
        default_server = os.getenv("YAP_SERVER", "127.0.0.1:8000")
    parser.add_argument("--server", default=default_server,
                        help="host:port or ws://host:port or full URL (uses RUNPOD_TCP_HOST/PORT if set)")
    parser.add_argument("--secure", action="store_true", help="Use WSS (requires cert on server)")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file from samples/")
    parser.add_argument("--rtf", type=float, default=1.0, help="Real-time factor (1.0=realtime, higher=faster)")
    return parser.parse_args()



async def run(args: argparse.Namespace) -> None:
    file_path = find_sample_by_name(args.file)
    if not file_path:
        print(f"File '{args.file}' not found in {SAMPLES_DIR}/")
        available = find_sample_files()
        if available:
            print(f"Available files: {[os.path.basename(f) for f in available]}")
        return

    pcm = file_to_pcm16_mono_24k(file_path)
    duration = file_duration_seconds(file_path)

    # Auto-enable TLS when targeting RunPod hosts unless explicitly overridden by scheme
    url = ws_url(args.server, args.secure or is_runpod_host(args.server))
    print(f"Connecting to: {url}")
    print(f"File: {os.path.basename(file_path)} ({duration:.2f}s)")

    file_duration_s = len(pcm) // 2 / 24000.0
    
    # Initialize handlers
    handler = ClientMessageHandler(debug=False)
    streamer = AudioStreamer(pcm, 1.0, debug=False)  # Will be updated with args.rtf

    # Authentication: always send Kyutai key to the model, and if routing through RunPod,
    # include the RunPod API key for the upstream gateway.
    KYUTAI_KEY = os.getenv("KYUTAI_API_KEY")
    if not KYUTAI_KEY:
        raise RuntimeError("KYUTAI_API_KEY is required (client)")
    extra_headers = [("kyutai-api-key", KYUTAI_KEY)]
    RUNPOD_KEY = os.getenv("RUNPOD_API_KEY")
    if is_runpod_host(args.server):
        if not RUNPOD_KEY:
            raise RuntimeError("RUNPOD_API_KEY is required when targeting a RunPod host")
        # Common RunPod pattern is Authorization: Bearer <token>
        extra_headers.append(("Authorization", f"Bearer {RUNPOD_KEY}"))
    ws_options = {
        "extra_headers": extra_headers,
        "compression": None,
        "max_size": None,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_queue": None,
        "write_limit": 2**22,
        "open_timeout": 10,
        "close_timeout": 0.2,
    }

    # Network latency measurements
    connect_start = time.perf_counter()
    t0 = time.perf_counter()
    
    # Update streamer RTF
    streamer.rtf = args.rtf
    
    async with websockets.connect(url, **ws_options) as ws:
        connect_time = time.perf_counter() - connect_start
        
        # Start message processing
        recv_task = asyncio.create_task(handler.process_messages(ws, t0))
        
        # Measure handshake latency (connection to Ready message)
        handshake_start = time.perf_counter()
        handshake_time = None
        try:
            await asyncio.wait_for(handler.ready_event.wait(), timeout=0.2)
            handshake_time = time.perf_counter() - handshake_start
        except asyncio.TimeoutError:
            handshake_time = 0.2  # timeout duration
        
        # Stream audio with first audio tracking
        print("Starting dynamic EOS settle gate")
        last_signal_ts = await streamer.stream_audio(ws, handler.eos_decider)
        
        # Set first audio sent for response latency calculation
        if streamer.last_chunk_sent_ts:
            handler.set_first_audio_sent(streamer.last_chunk_sent_ts)
        
        observed = handler.eos_decider.observed_silence_ms()
        needed = handler.eos_decider.needed_padding_ms()
        print(f"Settle complete - observed: {observed:.1f}ms, needed padding: {needed:.1f}ms")
        print("Sent final Flush")
        
        # Wait for server final with dynamic timeout
        timeout_s = max(10.0, file_duration_s / args.rtf + 3.0)
        print(f"Waiting for Final (timeout {timeout_s:.1f}s)")
        try:
            await asyncio.wait_for(handler.done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            handler.handle_connection_close()
            if handler.final_text:
                print(f"Accepting timeout with text: '{handler.final_text}'")
            else:
                print("Warning: Timeout waiting for final response and no text received")
        
        # Clean close
        with contextlib.suppress(Exception):
            asyncio.create_task(ws.close(code=1000, reason="client done"))

    if handler.final_text:
        print("\n=== Transcription Result ===")
        print(handler.final_text)
    else:
        print("No final text")

    elapsed_s = time.perf_counter() - t0
    wall_to_final = (handler.final_recv_ts - t0) if handler.final_recv_ts else elapsed_s
    rtf_measured = (wall_to_final / file_duration_s) if file_duration_s > 0 else None
    
    # Network latency metrics
    connect_ms = connect_time * 1000.0
    handshake_ms = handshake_time * 1000.0 if handshake_time is not None else 0.0
    first_response_ms = handler.first_response_time * 1000.0 if handler.first_response_time is not None else 0.0
    
    ttfw_ms = (handler.ttfw * 1000.0) if handler.ttfw is not None else 0.0
    
    print(f"\n=== Network Latency ===")
    print(f"Connection time: {connect_ms:.1f}ms")
    print(f"Handshake time: {handshake_ms:.1f}ms")
    print(f"First response: {first_response_ms:.1f}ms")
    
    print(f"\n=== Transcription Performance ===")
    print(f"Transcription time (to Final): {wall_to_final:.3f}s  RTF(measured): {rtf_measured:.4f}  (target={args.rtf})")
    print(f"TTFW: {ttfw_ms:.1f}ms  Partials: {len(handler.partial_ts)}  Avg partial gap: {(sum(b - a for a, b in zip(handler.partial_ts[:-1], handler.partial_ts[1:])) / len(handler.partial_ts[:-1])) * 1000.0 if len(handler.partial_ts) >= 2 else 0.0:.1f} ms")
    print(f"Δ(audio): {(wall_to_final - file_duration_s) * 1000.0:.1f}ms  Send dur: {(streamer.last_chunk_sent_ts - t0) if streamer.last_chunk_sent_ts else 0.0:.3f}s  Post-send→Final: {(handler.final_recv_ts - streamer.last_chunk_sent_ts) if (handler.final_recv_ts and streamer.last_chunk_sent_ts) else 0.0:.3f}s")
    print(f"Flush→Final: {((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0:.1f}ms  Decode tail: {((handler.final_recv_ts - handler.last_partial_ts) * 1000.0) if (handler.final_recv_ts and handler.last_partial_ts) else 0.0:.1f}ms")

    # metrics out
    out_dir = Path("test/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "client_metrics.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "elapsed_s": elapsed_s,
            "wall_to_final_s": wall_to_final,
            "audio_s": file_duration_s,
            "rtf_target": args.rtf,
            "rtf_measured": rtf_measured,
            "ttfw_ms": ttfw_ms,
            "partials": len(handler.partial_ts),
            "avg_partial_gap_ms": (sum(b - a for a, b in zip(handler.partial_ts[:-1], handler.partial_ts[1:])) / len(handler.partial_ts[:-1])) * 1000.0 if len(handler.partial_ts) >= 2 else 0.0,
            "finalize_ms": ((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0,
            "file": os.path.basename(file_path),
            "server": args.server,
            "connect_ms": connect_ms,
            "handshake_ms": handshake_ms,
            "first_response_ms": first_response_ms,
            "send_duration_s": (streamer.last_chunk_sent_ts - t0) if streamer.last_chunk_sent_ts else 0.0,
            "post_send_final_s": (handler.final_recv_ts - streamer.last_chunk_sent_ts) if (handler.final_recv_ts and streamer.last_chunk_sent_ts) else 0.0,
            "delta_to_audio_ms": (wall_to_final - file_duration_s) * 1000.0,
            "flush_to_final_ms": ((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0,
            "decode_tail_ms": ((handler.final_recv_ts - handler.last_partial_ts) * 1000.0) if (handler.final_recv_ts and handler.last_partial_ts) else 0.0,
        }, ensure_ascii=False) + "\n")

def main() -> None:
    import asyncio
    asyncio.run(run(parse_args()))

if __name__ == "__main__":
    main()
