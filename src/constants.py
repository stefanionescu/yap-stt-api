from __future__ import annotations

# Common protocol/constants used across server

# PCM16 mono sample size in bytes
PCM16_BYTES_PER_SAMPLE: int = 2

# Accepted Content-Types for raw PCM payloads
PCM_CONTENT_TYPES: tuple[str, ...] = ("audio/pcm", "audio/l16")

# WebSocket event emitted when stream cap is reached
WS_EVENT_LIMIT_REACHED: str = "input_audio_buffer.limit_reached"


