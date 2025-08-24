from __future__ import annotations

import base64
from typing import Tuple

import numpy as np
import soundfile as sf
import soxr


TARGET_SR = 16000


def file_to_pcm16_mono_16k(file_path: str) -> bytes:
    """Load arbitrary audio file and convert to PCM16 mono 16 kHz bytes."""
    audio, sr = sf.read(file_path, dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if sr != TARGET_SR:
        audio = soxr.resample(audio, sr, TARGET_SR)
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32768.0).astype(np.int16)
    return pcm16.tobytes()


def file_duration_seconds(file_path: str) -> float:
    """Return audio duration in seconds by reading the file header/frames."""
    data, sr = sf.read(file_path, dtype="float32", always_2d=False)
    if data.ndim == 2:
        n = data.shape[0]
    else:
        n = data.shape[0]
    return float(n) / float(sr if sr else TARGET_SR)


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


