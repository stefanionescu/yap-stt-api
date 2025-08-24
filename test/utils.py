from __future__ import annotations

import base64
from typing import Tuple
import shutil
import subprocess
from urllib.parse import urlparse, urlunparse

import numpy as np
import soundfile as sf
import soxr


TARGET_SR = 16000


def file_to_pcm16_mono_16k(file_path: str) -> bytes:
    """Load arbitrary audio file and convert to PCM16 mono 16 kHz bytes.

    Prefer ffmpeg for robust decoding and quiet logs; fall back to soundfile/soxr.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-v", "error",
                    "-nostdin",
                    "-hide_banner",
                    "-i", file_path,
                    "-f", "s16le",
                    "-ac", "1",
                    "-ar", str(TARGET_SR),
                    "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return proc.stdout
        except Exception:
            pass
    # Fallback: soundfile + soxr
    audio, sr = sf.read(file_path, dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) == 2:
        audio = audio.mean(axis=1)
    if sr != TARGET_SR:
        audio = soxr.resample(audio, sr, TARGET_SR)
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32768.0).astype(np.int16)
    return pcm16.tobytes()


def file_duration_seconds(file_path: str) -> float:
    """Return audio duration in seconds, preferring ffprobe to avoid decoder noise."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            s = proc.stdout.decode("utf-8", "ignore").strip()
            return float(s)
        except Exception:
            pass
    # Fallback: soundfile
    with sf.SoundFile(file_path) as snd:
        frames = len(snd)
        sr = snd.samplerate or TARGET_SR
        return float(frames) / float(sr)


def build_http_multipart(file_path: str, use_pcm: bool = True) -> Tuple[str, bytes, str]:
    """Return (filename, content_bytes, content_type) for HTTP multipart upload.

    If use_pcm is True, returns audio.pcm with audio/pcm content type.
    Otherwise returns original file bytes with application/octet-stream.
    """
    if use_pcm:
        pcm_bytes = file_to_pcm16_mono_16k(file_path)
        return ("audio.pcm", pcm_bytes, "audio/pcm")
    # as-is
    with open(file_path, "rb") as f:
        raw = f.read()
    import os
    return (os.path.basename(file_path), raw, "application/octet-stream")


async def ws_realtime_transcribe(url: str, pcm16_bytes: bytes, frame_ms: int = 40) -> str:
    """Stream PCM16 mono 16 kHz bytes to WS /v1/realtime and return concatenated text.

    Requires the `websockets` package.
    """
    try:
        import websockets
    except ImportError as e:
        raise RuntimeError("websockets package is required for WS tests: pip install websockets") from e

    bytes_per_sample = 2
    samples_per_frame = int(TARGET_SR * (frame_ms / 1000.0))
    bytes_per_frame = samples_per_frame * bytes_per_sample

    # Ensure ws/wss scheme
    if url.startswith("http://"):
        url = "ws://" + url[len("http://"):]
    elif url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    async with websockets.connect(url, max_size=None) as ws:
        # Best-effort consume session.created if sent
        try:
            greeting = await ws.recv()
            try:
                import json as _json
                obj = _json.loads(greeting)
                if not isinstance(obj, dict) or obj.get("type") != "session.created":
                    # Not a session.created; ignore
                    pass
            except Exception:
                pass
        except Exception:
            pass

        # Stream frames
        for i in range(0, len(pcm16_bytes), bytes_per_frame):
            chunk = pcm16_bytes[i:i + bytes_per_frame]
            if not chunk:
                break
            b64 = base64.b64encode(chunk).decode("ascii")
            await ws.send(f'{"{"}"type":"input_audio_buffer.append","audio":"{b64}"{"}"}')

        # Commit and request response
        await ws.send('{"type":"input_audio_buffer.commit"}')
        await ws.send('{"type":"response.create"}')

        # Aggregate deltas until completed
        text_parts: list[str] = []
        import json
        while True:
            msg = await ws.recv()
            try:
                obj = json.loads(msg)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "response.output_text.delta":
                text_parts.append(str(obj.get("delta", "")))
            elif isinstance(obj, dict) and obj.get("type") == "response.completed":
                break
            elif isinstance(obj, dict) and obj.get("type") == "error":
                # Stop on error
                break
        return "".join(text_parts).strip()


async def ws_realtime_transcribe_with_ttfw(url: str, pcm16_bytes: bytes, frame_ms: int = 40) -> tuple[str, float]:
    """Stream PCM16 mono 16 kHz bytes to WS /v1/realtime and return (text, ttfw_seconds).
    
    Returns both the transcribed text and time-to-first-word in seconds.
    Requires the `websockets` package.
    """
    try:
        import websockets
    except ImportError as e:
        raise RuntimeError("websockets package is required for WS tests: pip install websockets") from e
    import time
    
    bytes_per_sample = 2
    samples_per_frame = int(TARGET_SR * (frame_ms / 1000.0))
    bytes_per_frame = samples_per_frame * bytes_per_sample

    # Ensure ws/wss scheme
    if url.startswith("http://"):
        url = "ws://" + url[len("http://"):]
    elif url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    
    ttfw = 0.0  # Time to first word
    
    async with websockets.connect(url, max_size=None) as ws:
        # Best-effort consume session.created if sent
        try:
            greeting = await ws.recv()
            try:
                import json as _json
                obj = _json.loads(greeting)
                if not isinstance(obj, dict) or obj.get("type") != "session.created":
                    # Not a session.created; ignore
                    pass
            except Exception:
                pass
        except Exception:
            pass

        # Stream frames
        for i in range(0, len(pcm16_bytes), bytes_per_frame):
            chunk = pcm16_bytes[i:i + bytes_per_frame]
            if not chunk:
                break
            b64 = base64.b64encode(chunk).decode("ascii")
            await ws.send(f'{"{"}"type":"input_audio_buffer.append","audio":"{b64}"{"}"}')

        # Commit and request response
        await ws.send('{"type":"input_audio_buffer.commit"}')
        t_request = time.time()  # Mark when we request the response
        await ws.send('{"type":"response.create"}')

        # Aggregate deltas until completed
        text_parts: list[str] = []
        import json
        first_delta_received = False
        while True:
            msg = await ws.recv()
            try:
                obj = json.loads(msg)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "response.output_text.delta":
                if not first_delta_received:
                    ttfw = time.time() - t_request  # Record time to first delta
                    first_delta_received = True
                text_parts.append(str(obj.get("delta", "")))
            elif isinstance(obj, dict) and obj.get("type") == "response.completed":
                break
            elif isinstance(obj, dict) and obj.get("type") == "error":
                # Stop on error
                break
        
        return "".join(text_parts).strip(), ttfw


def to_ws_url(base_url: str, path: str = "/v1/realtime") -> str:
    """Convert an HTTP/HTTPS base URL to WS/WSS URL with the given path."""
    if not base_url:
        return "ws://127.0.0.1:8000" + path
    if "://" not in base_url:
        base_url = "http://" + base_url
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return urlunparse((scheme, netloc, path, "", "", ""))


