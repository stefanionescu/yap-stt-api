"""File and audio processing utilities."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf

SAMPLES_DIR = Path("samples")
EXTS = {".wav", ".flac", ".ogg", ".mp3"}


def find_sample_files() -> list[str]:
    """Find all audio files in samples directory."""
    if not SAMPLES_DIR.exists():
        return []
    files = []
    for root, _, filenames in os.walk(SAMPLES_DIR):
        for f in filenames:
            if Path(f).suffix.lower() in EXTS:
                files.append(str(Path(root) / f))
    return files


def find_sample_by_name(filename: str) -> str | None:
    """Find audio file by name in samples directory."""
    target = SAMPLES_DIR / filename
    if target.exists() and target.suffix.lower() in EXTS:
        return str(target)
    return None


def _ffmpeg_decode_to_pcm16_mono_16k(path: str) -> Tuple[np.ndarray, int]:
    """Decode any audio via ffmpeg to PCM16 mono 16 kHz."""
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
    """Decode any audio via ffmpeg to PCM16 mono 24 kHz."""
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
    """Load arbitrary audio file and return PCM16 mono @16k bytes."""
    try:
        x, sr = sf.read(path, dtype="int16", always_2d=False)
        if x.ndim > 1:
            x = x[:, 0]
        if sr != 16000:
            pcm, _ = _ffmpeg_decode_to_pcm16_mono_16k(path)
            return pcm.tobytes()
        return x.tobytes()
    except Exception:
        pcm, _ = _ffmpeg_decode_to_pcm16_mono_16k(path)
        return pcm.tobytes()


def file_to_pcm16_mono_24k(path: str) -> bytes:
    """Load arbitrary audio file and return PCM16 mono @24k bytes for Yap."""
    try:
        x, sr = sf.read(path, dtype="int16", always_2d=False)
        if x.ndim > 1:
            x = x[:, 0]
        if sr != 24000:
            pcm, _ = _ffmpeg_decode_to_pcm16_mono_24k(path)
            return pcm.tobytes()
        return x.tobytes()
    except Exception:
        pcm, _ = _ffmpeg_decode_to_pcm16_mono_24k(path)
        return pcm.tobytes()


def file_duration_seconds(path: str) -> float:
    """Get audio file duration in seconds."""
    try:
        f = sf.SoundFile(path)
        return float(len(f) / f.samplerate)
    except Exception:
        # fallback: decode to find length (can be expensive, but ok for tests)
        pcm, sr = _ffmpeg_decode_to_pcm16_mono_16k(path)
        return float(len(pcm) / sr)
