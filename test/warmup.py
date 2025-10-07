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
    file_to_pcm16_mono_24k, file_duration_seconds, SAMPLES_DIR,
    ws_url, append_auth_query, average_gap_ms, AudioStreamer, MessageHandler
)

RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"


async def _run(server: str, pcm_bytes: bytes, rtf: float, debug: bool = False, kyutai_key: str | None = None) -> dict:
    """Run warmup test against Yap ASR server."""
    # Setup
    api_key = kyutai_key or os.getenv("KYUTAI_API_KEY")
    if not api_key:
        raise RuntimeError("KYUTAI_API_KEY is required for internal calls (warmup).")
    
    url = ws_url(server, secure=False)
    url = append_auth_query(url, api_key, override=False)
    
    file_duration_s = len(pcm_bytes) // 2 / 24000.0
    
    # Initialize handlers
    handler = MessageHandler(debug=debug)
    streamer = AudioStreamer(pcm_bytes, rtf, debug=debug)
    
    ws_options = {
        "compression": None,
        "max_size": None,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_queue": None,
        "write_limit": 2**22,
        "open_timeout": 10,
        "close_timeout": 0.2,
    }
    
    t0 = time.perf_counter()
    async with websockets.connect(url, **ws_options) as ws:
        # Start message processing
        recv_task = asyncio.create_task(handler.process_messages(ws, t0))
        
        # Wait for Ready (optional)
        try:
            await asyncio.wait_for(handler.ready_event.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass
        
        # Stream audio and get final signal timestamp
        last_signal_ts = await streamer.stream_audio(ws, handler.eos_decider)
        
        # Wait for final response
        timeout_s = max(10.0, file_duration_s / rtf + 3.0)
        if debug:
            print(f"DEBUG: Waiting for Final (timeout {timeout_s:.1f}s)")
        
        try:
            await asyncio.wait_for(handler.done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            handler.handle_connection_close()
        
        # Clean close
        with contextlib.suppress(Exception):
            asyncio.create_task(ws.close(code=1000, reason="client done"))
    
    # Calculate metrics
    elapsed_s = time.perf_counter() - t0
    wall_to_final = (handler.final_recv_ts - t0) if handler.final_recv_ts else elapsed_s
    
    return {
        "text": handler.final_text,
        "elapsed_s": elapsed_s,
        "ttfw_s": handler.ttfw,
        "partials": len(handler.partial_ts),
        "avg_partial_gap_ms": average_gap_ms(handler.partial_ts),
        "finalize_ms": ((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0,
        "wall_to_final_s": wall_to_final,
        "audio_s": file_duration_s,
        "rtf_target": rtf,
        "rtf_measured": (wall_to_final / file_duration_s) if file_duration_s > 0 else None,
        "send_duration_s": (streamer.last_chunk_sent_ts - t0) if streamer.last_chunk_sent_ts else 0.0,
        "post_send_final_s": (handler.final_recv_ts - streamer.last_chunk_sent_ts) if (handler.final_recv_ts and streamer.last_chunk_sent_ts) else 0.0,
        "delta_to_audio_ms": (wall_to_final - file_duration_s) * 1000.0,
        "flush_to_final_ms": ((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0,
        "decode_tail_ms": ((handler.final_recv_ts - handler.last_partial_ts) * 1000.0) if (handler.final_recv_ts and handler.last_partial_ts) else 0.0,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Warmup via Yap WebSocket streaming")
    parser.add_argument("--server", type=str, default="127.0.0.1:8000", help="host:port or ws://host:port or full URL")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file. Absolute path or name in samples/")
    parser.add_argument("--rtf", type=float, default=1000.0, help="Real-time factor (1000=fast warmup, 1.0=realtime)")
    parser.add_argument("--debug", action="store_true", help="Print debug info including raw server messages")
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

    pcm_bytes = file_to_pcm16_mono_24k(str(audio_path))
    duration = file_duration_seconds(str(audio_path))

    kyutai_key = args.kyutai_key or os.getenv("KYUTAI_API_KEY")
    if not kyutai_key:
        print("Error: Kyutai API key missing. Use --kyutai-key or set KYUTAI_API_KEY env.")
        return 1

    res = asyncio.run(_run(args.server, pcm_bytes, args.rtf, args.debug, kyutai_key))

    if res.get("error"):
        print(f"Warmup error: {res['error']}")
    print(f"Text: {res.get('text', '')[:50]}...")
    print(f"Audio duration: {duration:.4f}s")
    print(f"Transcription time (to Final): {res.get('wall_to_final_s', 0.0):.4f}s")
    if duration > 0 and res.get('wall_to_final_s', 0.0) > 0:
        rtf = res["wall_to_final_s"] / duration
        xrt = (1.0/rtf) if rtf > 0 else 0.0
        print(f"RTF(measured): {rtf:.4f}  xRT: {xrt:.2f}x  (target={res.get('rtf_target')})")
    ttfw_ms = (res.get('ttfw_s', 0) * 1000.0) if res.get('ttfw_s') is not None else 0.0
    print(f"TTFW: {ttfw_ms:.1f}ms")
    print(f"Δ(audio): {res.get('delta_to_audio_ms', 0.0):.1f}ms  Send dur: {res.get('send_duration_s', 0.0):.3f}s  Post-send→Final: {res.get('post_send_final_s', 0.0):.3f}s")
    print(f"Partials: {res.get('partials', 0)}  Avg partial gap: {res.get('avg_partial_gap_ms', 0.0):.1f} ms")
    print(f"Flush→Final: {res.get('finalize_ms', 0.0):.1f}ms  Decode tail: {res.get('decode_tail_ms', 0.0):.1f}ms")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as out:
        out.write(json.dumps({
            **res,
            "duration": duration,
        }, ensure_ascii=False))
        out.write("\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
