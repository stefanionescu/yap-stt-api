"""Test utilities for Yap STT API testing.

This package provides focused modules for different aspects of testing:

- files.py - File and audio processing utilities
- network.py - WebSocket and network utilities  
- audio.py - Audio streaming and EOS detection
- messages.py - Message handling classes

All commonly used items are re-exported here for convenience.
"""

# Re-export commonly used items for convenience
from .files import (
    file_to_pcm16_mono_24k, file_to_pcm16_mono_16k, file_duration_seconds,
    find_sample_files, find_sample_by_name, SAMPLES_DIR, EXTS
)
from .network import ws_url, append_auth_query, is_runpod_host
from .audio import (
    pcm16_to_float32, iter_chunks, average_gap_ms, 
    EOSDecider, AudioStreamer
)
from .messages import MessageHandler, BenchMessageHandler, ClientMessageHandler

__all__ = [
    # Files
    'file_to_pcm16_mono_24k', 'file_to_pcm16_mono_16k', 'file_duration_seconds',
    'find_sample_files', 'find_sample_by_name', 'SAMPLES_DIR', 'EXTS',
    # Network
    'ws_url', 'append_auth_query', 'is_runpod_host',
    # Audio
    'pcm16_to_float32', 'iter_chunks', 'average_gap_ms', 'EOSDecider', 'AudioStreamer',
    # Messages
    'MessageHandler', 'BenchMessageHandler', 'ClientMessageHandler',
]