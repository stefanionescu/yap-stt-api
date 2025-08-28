from __future__ import annotations
import argparse
import asyncio
import contextlib
import json
import os
import time
from pathlib import Path
import websockets
import numpy as np
import msgpack

from utils import file_to_pcm16_mono_24k, file_duration_seconds, EOSDecider

SAMPLES_DIR = "samples"
RESULTS_DIR = Path("test/results")
RESULTS_FILE = RESULTS_DIR / "warmup.txt"

def _ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Moshi server ASR streaming endpoint"""
    if server.startswith(("ws://", "wss://")):
        return server
    scheme = "wss" if secure else "ws"
    # always add the path moshi-server exposes
    host = server.rstrip("/")
    return f"{scheme}://{host}/api/asr-streaming"

async def _run(server: str, pcm_bytes: bytes, rtf: float, mode: str, debug: bool = False) -> dict:
    url = _ws_url(server, secure=False)
    
    # Moshi uses 24kHz, 80ms chunks
    samples_per_chunk = int(24000 * 0.080)  # 1920 samples
    bytes_per_chunk = samples_per_chunk * 2  # 3840 bytes
    chunk_ms = 80.0
    # original audio duration (based on the 24k PCM16 you built)
    orig_samples = len(pcm_bytes) // 2
    file_duration_s = orig_samples / 24000.0

    partial_ts = []
    last_partial_ts = 0.0  # timestamp of last partial/word received
    last_chunk_sent_ts = 0.0
    last_signal_ts = 0.0
    final_recv_ts = 0.0
    final_text = ""
    last_text = ""
    words = []  # fallback transcript from Word events
    ready_event = asyncio.Event()
    done_event = asyncio.Event()
    ttfw = None
    
    # Dynamic EOS settle gate
    eos_decider = EOSDecider()

    # Moshi server authentication
    API_KEY = os.getenv("MOSHI_API_KEY", "public_token")
    ws_options = {
        "extra_headers": [("kyutai-api-key", API_KEY)],
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

        async def receiver():
            nonlocal final_text, final_recv_ts, last_text, ttfw, words
            try:
                async for raw in ws:
                    # moshi-server only sends binary frames
                    if isinstance(raw, (bytes, bytearray)):
                        if debug:
                            print(f"DEBUG: Received binary message (length: {len(raw)})")
                        data = msgpack.unpackb(raw, raw=False)
                        kind = data.get("type")
                        
                        if debug:
                            print(f"DEBUG: Received {kind}: {data}")
                        
                        now = time.perf_counter()
                        
                        if kind == "Ready":
                            ready_event.set()
                        elif kind in ("Partial", "Text"):
                            # Running transcript - prefer over Word assembly
                            txt = (data.get("text") or "").strip()
                            if txt:
                                if ttfw is None:
                                    ttfw = now - t0
                                if txt != last_text:
                                    partial_ts.append(now - t0)
                                    last_partial_ts = now  # track last partial timestamp
                                    eos_decider.update_partial(now)  # Update EOS state
                                    last_text = txt
                                    if debug:
                                        print(f"DEBUG: New partial text: '{txt}'")
                                final_text = txt  # prefer Partial/Text over Word assembly
                                # sync words array so later Words don't go backwards
                                words = final_text.split()
                                eos_decider.clear_pending_word()  # running text supersedes pending
                        elif kind == "Word":
                            w = (data.get("text") or data.get("word") or "").strip()
                            if w:
                                if ttfw is None:
                                    ttfw = now - t0  # strict TTFW on first word
                                words.append(w)  # accumulate words
                                final_text = " ".join(words).strip()  # ALWAYS assemble running text
                                if final_text != last_text:  # treat each new word as a partial
                                    partial_ts.append(now - t0)
                                    last_partial_ts = now  # track last partial timestamp
                                    eos_decider.update_partial(now)  # Update EOS state
                                    last_text = final_text
                                if debug:
                                    print(f"DEBUG: Word: {w!r}, assembled: {final_text!r}")
                        elif kind in ("Marker", "Final"):
                            # End-of-utterance - COMMIT any pending word before deciding final text
                            pending = eos_decider.get_pending_word()
                            if pending:
                                words.append(pending)
                                if debug:
                                    print(f"DEBUG: Added pending word on Final: {pending!r}")
                                # If running text doesn't include it, sync it
                                if (not final_text) or len(final_text.split()) < len(words):
                                    final_text = " ".join(words).strip()
                            
                            txt = (data.get("text") or "").strip()
                            if txt:
                                final_text = txt  # prefer server-provided final
                            final_recv_ts = now
                            done_event.set()
                            if debug:
                                print(f"DEBUG: Final message received, text: '{final_text}'")
                            break
                        elif kind == "Error":
                            done_event.set()
                            break
                        elif kind == "Step":
                            # Ignore server step messages
                            continue
                        elif kind == "EndWord":
                            # Word end event - track for EOS decisions and handle pending words
                            w = (data.get("text") or data.get("word") or "").strip()
                            if w:
                                eos_decider.set_pending_word(w)
                                if debug:
                                    print(f"DEBUG: EndWord pending: {w!r}")
                            eos_decider.set_end_word()
                            continue
                        else:
                            # Unknown message type, treat as potential text
                            txt = (data.get("text") or "").strip()
                            if txt:
                                if ttfw is None:
                                    ttfw = now - t0
                                if txt != last_text:
                                    partial_ts.append(now - t0)
                                    last_partial_ts = now  # track last partial timestamp
                                    last_text = txt
                                    if debug:
                                        print(f"DEBUG: Unknown message type '{kind}' with text: '{txt}'")
                                final_text = txt
                    else:
                        # Skip text messages
                        if debug:
                            print(f"DEBUG: Received text message: {repr(raw)}")
                        continue
            except websockets.exceptions.ConnectionClosedOK:
                # graceful close — okay
                if debug:
                    print("DEBUG: Connection closed gracefully")
                pass
            except websockets.exceptions.ConnectionClosedError as e:
                # server closed without a close frame — treat as final if we have content
                if debug:
                    print(f"DEBUG: Connection closed with error: {e}")
                if not done_event.is_set():
                    # Check for pending word from EndWord events
                    pending = eos_decider.get_pending_word()
                    if pending:
                        words.append(pending)
                        if debug:
                            print(f"DEBUG: Added pending word on close: {pending!r}")
                    
                    if words or final_text:
                        final_recv_ts = time.perf_counter()
                        if not final_text and words:
                            final_text = " ".join(words).strip()
                        done_event.set()
                        if debug:
                            print(f"DEBUG: Treating close as final, text: '{final_text}'")
                pass

        recv_task = asyncio.create_task(receiver())

        # Optional grace period for Ready (don't block if server doesn't send it)
        if debug:
            print("DEBUG: Waiting for Ready (with timeout)")
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=0.2)
            if debug:
                print("DEBUG: Ready received")
        except asyncio.TimeoutError:
            if debug:
                print("DEBUG: No Ready received, proceeding anyway")
            pass  # proceed to send anyway
        if debug:
            print("DEBUG: Starting audio stream")
        
        # Convert PCM16 bytes to float32 normalized [-1,1] (no pre-padding)
        pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        hop = 1920  # 80 ms @ 24k
        
        # right before the loop
        t_stream0 = time.perf_counter()
        samples_sent = 0
        sr = 24000

        if mode == "stream":
            # 80 ms @ 24k = 1920 samples - pace by wall-clock against audio timeline
            for i in range(0, len(pcm_int16), hop):
                pcm_chunk = pcm_int16[i:i+hop]
                if len(pcm_chunk) == 0:
                    break
                msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                                   use_bin_type=True, use_single_float=True)
                await ws.send(msg)
                last_chunk_sent_ts = time.perf_counter()

                # advance timeline by the *actual* chunk duration
                samples_sent += len(pcm_chunk)
                target = t_stream0 + (samples_sent / sr) / max(rtf, 1e-6)
                sleep_for = target - time.perf_counter()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
        else:
            # oneshot: larger chunks
            hop = int(24000 * 2.0)  # ~2 sec chunks
            for i in range(0, len(pcm_int16), hop):
                pcm_chunk = pcm_int16[i:i+hop]
                if len(pcm_chunk) == 0:
                    break
                msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                                   use_bin_type=True, use_single_float=True)
                await ws.send(msg)
                last_chunk_sent_ts = time.perf_counter()

        # Dynamic EOS settle gate - wait for evidence utterance is over
        if debug:
            print("DEBUG: Starting dynamic EOS settle gate")
        
        # Wait until we have enough evidence that the user finished
        await eos_decider.wait_for_settle(max_wait_ms=600)
        
        if debug:
            observed = eos_decider.observed_silence_ms()
            needed = eos_decider.needed_padding_ms()
            print(f"DEBUG: Settle complete - observed: {observed:.1f}ms, needed padding: {needed:.1f}ms")
        
        # Top up with just enough silence if needed
        needed_ms = eos_decider.needed_padding_ms()
        frames = int((needed_ms + 79) // 80)  # ceil to 80ms frames
        
        # Ensure at least one decoder step happens before Flush
        MIN_PAD_FRAMES = 1
        frames = max(frames, MIN_PAD_FRAMES)
        
        if frames > 0:
            if debug:
                print(f"DEBUG: Adding {frames} silence frames ({frames * 80:.0f}ms)")
            silence = np.zeros(1920, dtype=np.float32).tolist()
            for _ in range(frames):
                await ws.send(msgpack.packb({"type":"Audio","pcm":silence},
                                            use_bin_type=True, use_single_float=True))
        
        # Final flush
        await ws.send(msgpack.packb({"type": "Flush"}, use_bin_type=True))
        last_signal_ts = time.perf_counter()
        if debug:
            print("DEBUG: Sent final Flush")
        
        # Wait for server final with dynamic timeout
        timeout_s = max(10.0, file_duration_s / rtf + 3.0)
        if debug:
            print(f"DEBUG: Waiting for Final (timeout {timeout_s:.1f}s)")
        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            # Check for pending word from EndWord events before giving up
            pending = eos_decider.get_pending_word()
            if pending:
                words.append(pending)
                if debug:
                    print(f"DEBUG: Added pending word on timeout: {pending!r}")
            
            if words or final_text:
                final_recv_ts = time.perf_counter()
                if not final_text and words:
                    final_text = " ".join(words).strip()
                if debug:
                    print(f"DEBUG: Accepting timeout with text: '{final_text}'")
            else:
                if debug:
                    print("DEBUG: No text received, real timeout")
        
        # Proactively close; don't block main path on close handshake
        with contextlib.suppress(Exception):
            asyncio.create_task(ws.close(code=1000, reason="client done"))
        # Receiver may still be draining; don't await it if we're done

    elapsed_s = time.perf_counter() - t0
    finalize_ms = ((final_recv_ts - last_signal_ts) * 1000.0) if (final_recv_ts and last_signal_ts) else 0.0
    avg_gap_ms = 0.0
    if len(partial_ts) >= 2:
        gaps = [b - a for a, b in zip(partial_ts[:-1], partial_ts[1:])]
        avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0

    # Add wall_to_final (up to Final). No default tail; no forced pad in timing.
    wall_to_final = (final_recv_ts - t0) if final_recv_ts else elapsed_s

    # New derived metrics (honest taxonomy)
    send_duration_s = (last_chunk_sent_ts - t0) if last_chunk_sent_ts else 0.0
    post_send_final_s = (final_recv_ts - last_chunk_sent_ts) if (final_recv_ts and last_chunk_sent_ts) else 0.0
    delta_to_audio_s = wall_to_final - file_duration_s
    decode_tail_s = (final_recv_ts - last_partial_ts) if (final_recv_ts and last_partial_ts) else None

    return {
        "text": final_text,
        "elapsed_s": elapsed_s,              # includes close/cleanup
        "ttfw_s": ttfw,
        "partials": len(partial_ts) if mode == "stream" else 0,
        "avg_partial_gap_ms": avg_gap_ms if mode == "stream" else 0.0,
        "finalize_ms": finalize_ms if mode == "stream" else 0.0,
        "wall_to_final_s": wall_to_final,    # what users feel
        "audio_s": file_duration_s,          # original file duration at 24k
        "mode": mode,
        "rtf_target": rtf,                   # configured throttle
        "rtf_measured": (wall_to_final / file_duration_s) if file_duration_s > 0 else None,
        # New honest metrics
        "send_duration_s": send_duration_s,
        "post_send_final_s": post_send_final_s,
        "delta_to_audio_ms": delta_to_audio_s * 1000.0,
        "flush_to_final_ms": finalize_ms,
        "decode_tail_ms": (decode_tail_s * 1000.0) if decode_tail_s is not None else 0.0,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Warmup via Moshi WebSocket streaming")
    parser.add_argument("--server", type=str, default="127.0.0.1:8000", help="host:port or ws://host:port or full URL")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--file", type=str, default="mid.wav", help="Audio file. Absolute path or name in samples/")
    parser.add_argument("--rtf", type=float, default=1000.0, help="Real-time factor (1000=fast warmup, 1.0=realtime)")
    parser.add_argument("--mode", choices=["stream", "oneshot"], default="stream", help="Run streaming or one-shot ASR")
    parser.add_argument("--debug", action="store_true", help="Print debug info including raw server messages")
    args = parser.parse_args()

    # Resolve path: allow absolute path; otherwise look under samples/
    candidate = Path(args.file)
    if candidate.is_absolute() and candidate.exists():
        audio_path = candidate
    else:
        audio_path = Path(SAMPLES_DIR) / args.file
    if not audio_path.exists():
        print(f"Audio not found: {audio_path}")
        return 2

    pcm_bytes = file_to_pcm16_mono_24k(str(audio_path))
    duration = file_duration_seconds(str(audio_path))

    res = asyncio.run(_run(args.server, pcm_bytes, args.rtf, args.mode, args.debug))

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
    if args.mode == "stream":
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
