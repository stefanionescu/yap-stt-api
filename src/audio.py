from __future__ import annotations

import io
import shutil
import subprocess
from dataclasses import dataclass
from typing import Tuple

import numpy as np
import soundfile as sf
import soxr

TARGET_SR = 16000

@dataclass
class DecodedAudio:
    waveform: np.ndarray  # shape [T]
    sample_rate: int
    duration_seconds: float


def decode_audio_bytes(data: bytes) -> Tuple[np.ndarray, int]:
    """Decode arbitrary audio bytes into mono float32 PCM and return (audio, sr).

    Prefer ffmpeg for robust, quiet decoding; fall back to soundfile if ffmpeg
    is unavailable.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    "pipe:0",
                    "-f",
                    "f32le",
                    "-ac",
                    "1",
                    "-ar",
                    str(TARGET_SR),
                    "pipe:1",
                ],
                input=data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            pcm = np.frombuffer(proc.stdout, dtype=np.float32)
            return pcm, TARGET_SR
        except Exception:
            # fall through to soundfile
            pass

    # Fallback: soundfile (may emit decoder warnings on some MP3s)
    with io.BytesIO(data) as bio:
        audio, sr = sf.read(bio, dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) == 2:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32, copy=False), int(sr)


def resample_if_needed(audio: np.ndarray, sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    if sr == target_sr:
        return audio
    # Use high-quality band-limited sinc resampler
    return soxr.resample(audio, sr, target_sr, quality="HQ")


def decode_and_resample(data: bytes) -> DecodedAudio:
    waveform, sr = decode_audio_bytes(data)
    waveform = resample_if_needed(waveform, sr, TARGET_SR)
    duration_seconds = float(len(waveform) / TARGET_SR)
    return DecodedAudio(waveform=waveform, sample_rate=TARGET_SR, duration_seconds=duration_seconds)
