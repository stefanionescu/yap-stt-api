from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf

SAMPLES_DIR = Path("samples")


def _ffmpeg_decode_to_pcm16_mono_16k(path: str) -> Tuple[np.ndarray, int]:
    """
    Decode any audio via ffmpeg to PCM16 mono 16 kHz and return bytes + duration samples.
    """
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", path,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", "16000",
        "pipe:1",
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    pcm = np.frombuffer(p.stdout, dtype=np.int16)
    return pcm, 16000


def _ffmpeg_decode_to_pcm16_mono_24k(path: str) -> Tuple[np.ndarray, int]:
    """
    Decode any audio via ffmpeg to PCM16 mono 24 kHz and return bytes + duration samples.
    """
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", path,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", "24000",
        "pipe:1",
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    pcm = np.frombuffer(p.stdout, dtype=np.int16)
    return pcm, 24000


def file_to_pcm16_mono_16k(path: str) -> bytes:
    """
    Load arbitrary audio file and return PCM16 mono @16k bytes suitable for WS streaming.
    Prefers soundfile; falls back to ffmpeg for MP3/others if needed.
    """
    try:
        x, sr = sf.read(path, dtype="int16", always_2d=False)
        if x.ndim > 1:
            x = x[:, 0]
        if sr != 16000:
            # simple resample via ffmpeg for reliability across formats
            pcm, _ = _ffmpeg_decode_to_pcm16_mono_16k(path)
            return pcm.tobytes()
        return x.tobytes()
    except Exception:
        pcm, _ = _ffmpeg_decode_to_pcm16_mono_16k(path)
        return pcm.tobytes()


def file_to_pcm16_mono_24k(path: str) -> bytes:
    """
    Load arbitrary audio file and return PCM16 mono @24k bytes suitable for Moshi WS streaming.
    Prefers soundfile; falls back to ffmpeg for MP3/others if needed.
    """
    try:
        x, sr = sf.read(path, dtype="int16", always_2d=False)
        if x.ndim > 1:
            x = x[:, 0]
        if sr != 24000:
            # simple resample via ffmpeg for reliability across formats
            pcm, _ = _ffmpeg_decode_to_pcm16_mono_24k(path)
            return pcm.tobytes()
        return x.tobytes()
    except Exception:
        pcm, _ = _ffmpeg_decode_to_pcm16_mono_24k(path)
        return pcm.tobytes()


def file_duration_seconds(path: str) -> float:
    try:
        f = sf.SoundFile(path)
        return float(len(f) / f.samplerate)
    except Exception:
        # fallback: decode to find length (can be expensive, but ok for tests)
        pcm, sr = _ffmpeg_decode_to_pcm16_mono_16k(path)
        return float(len(pcm) / sr)


