from __future__ import annotations

import shutil
import subprocess

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
