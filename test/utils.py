from __future__ import annotations
import asyncio
import os
import subprocess
import time
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
    Load arbitrary audio file and return PCM16 mono @24k bytes suitable for Yap WS streaming.
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


class EOSDecider:
    """
    Dynamic EOS "settle gate" that waits for evidence utterance is over.
    Replaces fixed padding with data-driven approach.
    """
    
    def __init__(self):
        # Configuration from environment variables
        self.target_eos_ms = int(os.getenv("EOS_TARGET_MS", "220"))   # total evidence you want
        self.quiet_ms = int(os.getenv("EOS_QUIET_MS", "140"))        # decoder quiet window
        self.vad_hangover_ms = int(os.getenv("EOS_VAD_HANGOVER_MS", "160"))  # VAD-off hangover
        
        # State tracking
        self.vad_off_since: float | None = None
        self.last_partial_ts: float | None = None
        self.pending_word: str | None = None
        self.has_end_word = False
        
    def update_vad(self, state: str):
        """Update VAD state. For file mode, we simulate VAD based on silence detection."""
        now = time.perf_counter()
        if state == "off":
            self.vad_off_since = self.vad_off_since or now
        else:
            self.vad_off_since = None
    
    def update_partial(self, timestamp: float):
        """Called when we receive any partial/word update."""
        self.last_partial_ts = timestamp
        # Reset VAD simulation - assume voice activity if we're getting partials
        self.vad_off_since = None
    
    def set_pending_word(self, word: str):
        """Set a pending word from EndWord event."""
        self.pending_word = word
    
    def set_end_word(self):
        """Mark that we received EndWord event."""
        self.has_end_word = True
        # Start VAD-off simulation when we get EndWord
        if self.vad_off_since is None:
            self.vad_off_since = time.perf_counter()
    
    def get_pending_word(self) -> str | None:
        """Get and clear any pending word."""
        word = self.pending_word
        self.pending_word = None
        return word
    
    def clear_pending_word(self):
        """Clear any pending word (when superseded by newer text)."""
        self.pending_word = None
    
    def observed_silence_ms(self) -> float:
        """Calculate how much silence/quiet we've observed."""
        now = time.perf_counter()
        
        # VAD-off hangover
        vad_silence = (now - self.vad_off_since) * 1000 if self.vad_off_since else 0.0
        
        # Decoder quiet time (no partials)
        decoder_quiet = (now - self.last_partial_ts) * 1000 if self.last_partial_ts else 0.0
        
        return max(vad_silence, decoder_quiet)
    
    def should_flush(self) -> bool:
        """Check if we have enough evidence that the utterance is over."""
        silence_ms = self.observed_silence_ms()
        
        # Basic quiet threshold
        if silence_ms >= self.quiet_ms:
            return True
            
        # If we have EndWord + some silence, be more aggressive
        if self.has_end_word and silence_ms >= max(80, self.quiet_ms // 2):
            return True
            
        return False
    
    def needed_padding_ms(self) -> float:
        """Calculate how much additional padding we need to reach target."""
        observed = self.observed_silence_ms()
        needed = self.target_eos_ms - observed
        return max(0, needed)
    
    async def wait_for_settle(self, max_wait_ms: float = 600) -> None:
        """
        Wait until we have enough evidence that the user finished speaking.
        Uses whichever comes first:
        - VAD-off hangover for ≥ quiet_ms
        - Decoder quiet for ≥ quiet_ms  
        - EndWord + shorter quiet period
        """
        deadline = time.perf_counter() + (max_wait_ms / 1000.0)
        
        while time.perf_counter() < deadline:
            if self.should_flush():
                return
            await asyncio.sleep(0.010)  # Check every 10ms


