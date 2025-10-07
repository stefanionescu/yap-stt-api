"""Audio processing and streaming utilities."""
from __future__ import annotations
import asyncio
import os
import time

import numpy as np
import msgpack


def pcm16_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert PCM16 bytes to float32 in [-1, 1]."""
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def iter_chunks(arr: np.ndarray, hop: int):
    """Yield contiguous chunks of size hop from a 1-D numpy array."""
    for i in range(0, len(arr), hop):
        chunk = arr[i:i + hop]
        if len(chunk) == 0:
            break
        yield chunk


def average_gap_ms(partial_timestamps: list[float]) -> float:
    """Compute average gap between consecutive partial timestamps in ms."""
    if len(partial_timestamps) < 2:
        return 0.0
    gaps = [b - a for a, b in zip(partial_timestamps[:-1], partial_timestamps[1:])]
    return (sum(gaps) / len(gaps)) * 1000.0


class EOSDecider:
    """Dynamic EOS 'settle gate' that waits for evidence utterance is over."""
    
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
        """Wait until we have enough evidence that the user finished speaking."""
        deadline = time.perf_counter() + (max_wait_ms / 1000.0)
        
        while time.perf_counter() < deadline:
            if self.should_flush():
                return
            await asyncio.sleep(0.010)  # Check every 10ms


class AudioStreamer:
    """Handles audio streaming with RTF control."""
    
    def __init__(self, pcm_bytes: bytes, rtf: float, debug: bool = False):
        self.pcm_int16 = pcm16_to_float32(pcm_bytes)
        self.rtf = rtf
        self.debug = debug
        self.hop = 1920  # 80 ms @ 24k
        self.sr = 24000
        self.last_chunk_sent_ts = 0.0
        
    async def stream_audio(self, ws, eos_decider: EOSDecider):
        """Stream audio chunks with RTF control."""
        if self.debug:
            print("DEBUG: Starting audio stream")
        
        t_stream0 = time.perf_counter()
        samples_sent = 0
        
        for pcm_chunk in iter_chunks(self.pcm_int16, self.hop):
            msg = msgpack.packb({"type": "Audio", "pcm": pcm_chunk.tolist()},
                               use_bin_type=True, use_single_float=True)
            await ws.send(msg)
            self.last_chunk_sent_ts = time.perf_counter()
            
            samples_sent += len(pcm_chunk)
            target = t_stream0 + (samples_sent / self.sr) / max(self.rtf, 1e-6)
            sleep_for = target - time.perf_counter()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        
        # Dynamic EOS settle gate
        if self.debug:
            print("DEBUG: Starting dynamic EOS settle gate")
        
        await eos_decider.wait_for_settle(max_wait_ms=600)
        
        if self.debug:
            observed = eos_decider.observed_silence_ms()
            needed = eos_decider.needed_padding_ms()
            print(f"DEBUG: Settle complete - observed: {observed:.1f}ms, needed padding: {needed:.1f}ms")
        
        # Add silence padding
        needed_ms = eos_decider.needed_padding_ms()
        frames = max(1, int((needed_ms + 79) // 80))  # At least 1 frame
        
        if frames > 0:
            if self.debug:
                print(f"DEBUG: Adding {frames} silence frames ({frames * 80:.0f}ms)")
            silence = np.zeros(1920, dtype=np.float32).tolist()
            for _ in range(frames):
                await ws.send(msgpack.packb({"type": "Audio", "pcm": silence},
                                            use_bin_type=True, use_single_float=True))
        
        # Final flush
        await ws.send(msgpack.packb({"type": "Flush"}, use_bin_type=True))
        if self.debug:
            print("DEBUG: Sent final Flush")
        
        return time.perf_counter()
