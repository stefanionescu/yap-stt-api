"""Base client class for Yap STT API connections."""
from __future__ import annotations
import asyncio
import contextlib
import os
import time
from typing import Dict, Any

import websockets

from utils import ws_url, append_auth_query, AudioStreamer
from utils.messages import MessageHandler


class YapClient:
    """Base client for connecting to Yap STT API."""
    
    def __init__(self, server: str, secure: bool = False, debug: bool = False):
        self.server = server
        self.secure = secure
        self.debug = debug
        self.url = ws_url(server, secure)
        
    def get_auth_headers(self) -> list[tuple[str, str]]:
        """Get authentication headers. Override in subclasses."""
        kyutai_key = os.getenv("KYUTAI_API_KEY")
        if not kyutai_key:
            raise RuntimeError("KYUTAI_API_KEY is required")
        return [("kyutai-api-key", kyutai_key)]
    
    def get_ws_options(self) -> Dict[str, Any]:
        """Get WebSocket connection options."""
        return {
            "extra_headers": self.get_auth_headers(),
            "compression": None,
            "max_size": None,
            "ping_interval": 20,
            "ping_timeout": 20,
            "max_queue": None,
            "write_limit": 2**22,
            "open_timeout": 10,
            "close_timeout": 0.2,
        }
    
    async def connect_and_process(self, pcm_bytes: bytes, rtf: float, 
                                handler: MessageHandler) -> tuple[float, float]:
        """Connect to server and process audio. Returns (t0, last_signal_ts)."""
        streamer = AudioStreamer(pcm_bytes, rtf, debug=self.debug)
        ws_options = self.get_ws_options()
        
        t0 = time.perf_counter()
        async with websockets.connect(self.url, **ws_options) as ws:
            # Start message processing
            recv_task = asyncio.create_task(handler.process_messages(ws, t0))
            
            # Wait for Ready (optional)
            try:
                await asyncio.wait_for(handler.ready_event.wait(), timeout=0.2)
            except asyncio.TimeoutError:
                pass
            
            # Check for immediate errors
            if handler.done_event.is_set():
                return t0, time.perf_counter()
            
            # Stream audio and capture first-audio-sent timestamp
            first_audio_ts, last_signal_ts = await streamer.stream_audio(
                ws, handler.eos_decider,
                (handler.set_first_audio_sent if hasattr(handler, "set_first_audio_sent") else None)
            )
            
            # Wait for final response
            file_duration_s = len(pcm_bytes) // 2 / 24000.0
            timeout_s = max(10.0, file_duration_s / rtf + 3.0)
            try:
                await asyncio.wait_for(handler.done_event.wait(), timeout=timeout_s)
            except asyncio.TimeoutError:
                handler.handle_connection_close()
            
            # Clean close
            with contextlib.suppress(Exception):
                asyncio.create_task(ws.close(code=1000, reason="client done"))
        
        return t0, last_signal_ts


class QueryAuthClient(YapClient):
    """Client that uses query parameter authentication."""
    
    def __init__(self, server: str, secure: bool = False, debug: bool = False):
        super().__init__(server, secure, debug)
        # Add auth to URL
        kyutai_key = os.getenv("KYUTAI_API_KEY")
        if not kyutai_key:
            raise RuntimeError("KYUTAI_API_KEY is required")
        self.url = append_auth_query(self.url, kyutai_key, override=True)
    
    def get_auth_headers(self) -> list[tuple[str, str]]:
        """No headers needed - auth is in query."""
        return []
