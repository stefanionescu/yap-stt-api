"""WebSocket message handling for Yap ASR protocol."""
from __future__ import annotations
import asyncio
import time

import msgpack
import websockets

from .audio import EOSDecider


class MessageHandler:
    """Base WebSocket message handler for Yap ASR protocol."""
    
    def __init__(self, debug: bool = False, track_word_ttfw: bool = False):
        self.debug = debug
        self.track_word_ttfw = track_word_ttfw
        self.partial_ts: list[float] = []
        self.last_partial_ts = 0.0
        self.final_recv_ts = 0.0
        self.final_text = ""
        self.last_text = ""
        self.words: list[str] = []
        self.ttfw = None
        self.ttfw_word = None if track_word_ttfw else None
        self.ttfw_text = None if track_word_ttfw else None
        self.ready_event = asyncio.Event()
        self.done_event = asyncio.Event()
        self.reject_reason = None
        self.eos_decider = EOSDecider()
        
    def handle_ready(self, now: float):
        """Handle Ready message."""
        self.ready_event.set()
        if self.debug:
            print("DEBUG: Ready received")
    
    def handle_partial_text(self, data: dict, now: float, t0: float):
        """Handle Partial/Text messages."""
        txt = (data.get("text") or "").strip()
        if txt:
            if self.ttfw is None:
                self.ttfw = now - t0
            if self.track_word_ttfw and self.ttfw_text is None:
                self.ttfw_text = now - t0
            if txt != self.last_text:
                self.partial_ts.append(now - t0)
                self.last_partial_ts = now
                self.eos_decider.update_partial(now)
                self.last_text = txt
                if self.debug:
                    print(f"DEBUG: New partial text: '{txt}'")
            self.final_text = txt
            self.words = self.final_text.split()
            self.eos_decider.clear_pending_word()
    
    def handle_word(self, data: dict, now: float, t0: float):
        """Handle Word messages."""
        w = (data.get("text") or data.get("word") or "").strip()
        if w:
            if self.ttfw is None:
                self.ttfw = now - t0
            if self.track_word_ttfw and self.ttfw_word is None:
                self.ttfw_word = now - t0
            self.words.append(w)
            self.final_text = " ".join(self.words).strip()
            if self.final_text != self.last_text:
                self.partial_ts.append(now - t0)
                self.last_partial_ts = now
                self.eos_decider.update_partial(now)
                self.last_text = self.final_text
            if self.debug:
                print(f"DEBUG: Word: {w!r}, assembled: {self.final_text!r}")
    
    def handle_final_marker(self, data: dict, now: float):
        """Handle Final/Marker messages."""
        pending = self.eos_decider.get_pending_word()
        if pending:
            self.words.append(pending)
            if self.debug:
                print(f"DEBUG: Added pending word on Final: {pending!r}")
            if (not self.final_text) or len(self.final_text.split()) < len(self.words):
                self.final_text = " ".join(self.words).strip()
        
        txt = (data.get("text") or "").strip()
        if txt:
            self.final_text = txt
        self.final_recv_ts = now
        self.done_event.set()
        if self.debug:
            print(f"DEBUG: Final message received, text: '{self.final_text}'")
    
    def handle_error(self, data: dict):
        """Handle Error messages."""
        msg_txt = (data.get("message") or data.get("error") or "").strip().lower()
        if "no free channels" in msg_txt:
            self.reject_reason = "capacity"
        self.done_event.set()
    
    def handle_end_word(self, data: dict):
        """Handle EndWord messages."""
        w = (data.get("text") or data.get("word") or "").strip()
        if w:
            self.eos_decider.set_pending_word(w)
            if self.debug:
                print(f"DEBUG: EndWord pending: {w!r}")
        self.eos_decider.set_end_word()
    
    def handle_connection_close(self):
        """Handle connection close with pending words."""
        if not self.done_event.is_set():
            pending = self.eos_decider.get_pending_word()
            if pending:
                self.words.append(pending)
                if self.debug:
                    print(f"DEBUG: Added pending word on close: {pending!r}")
            
            if self.words or self.final_text:
                self.final_recv_ts = time.perf_counter()
                if not self.final_text and self.words:
                    self.final_text = " ".join(self.words).strip()
                self.done_event.set()
                if self.debug:
                    print(f"DEBUG: Treating close as final, text: '{self.final_text}'")
    
    async def process_messages(self, ws, t0: float):
        """Main message processing loop."""
        try:
            async for raw in ws:
                if isinstance(raw, (bytes, bytearray)):
                    if self.debug:
                        print(f"DEBUG: Received binary message (length: {len(raw)})")
                    data = msgpack.unpackb(raw, raw=False)
                    kind = data.get("type")
                    
                    if self.debug:
                        print(f"DEBUG: Received {kind}: {data}")
                    
                    now = time.perf_counter()
                    
                    if kind == "Ready":
                        self.handle_ready(now)
                    elif kind in ("Partial", "Text"):
                        self.handle_partial_text(data, now, t0)
                    elif kind == "Word":
                        self.handle_word(data, now, t0)
                    elif kind in ("Marker", "Final"):
                        self.handle_final_marker(data, now)
                        break
                    elif kind == "Error":
                        self.handle_error(data)
                        break
                    elif kind == "Step":
                        continue
                    elif kind == "EndWord":
                        self.handle_end_word(data)
                        continue
                    else:
                        # Unknown message type, treat as potential text
                        txt = (data.get("text") or "").strip()
                        if txt:
                            if self.ttfw is None:
                                self.ttfw = now - t0
                            if txt != self.last_text:
                                self.partial_ts.append(now - t0)
                                self.last_partial_ts = now
                                self.last_text = txt
                                if self.debug:
                                    print(f"DEBUG: Unknown message type '{kind}' with text: '{txt}'")
                            self.final_text = txt
                else:
                    if self.debug:
                        print(f"DEBUG: Received text message: {repr(raw)}")
        except websockets.exceptions.ConnectionClosedOK:
            if self.debug:
                print("DEBUG: Connection closed gracefully")
        except websockets.exceptions.ConnectionClosedError as e:
            if self.debug:
                print(f"DEBUG: Connection closed with error: {e}")
            self.handle_connection_close()
        
        if self.final_recv_ts == 0.0:
            self.final_recv_ts = time.perf_counter()


class BenchMessageHandler(MessageHandler):
    """Bench-specific message handler that raises CapacityRejected."""
    
    def __init__(self, debug: bool = False):
        super().__init__(debug=debug, track_word_ttfw=True)
    
    def handle_error(self, data: dict):
        """Handle Error messages with capacity rejection."""
        msg_txt = (data.get("message") or data.get("error") or "").strip().lower()
        if "no free channels" in msg_txt:
            self.reject_reason = "capacity"
        self.done_event.set()


class ClientMessageHandler(MessageHandler):
    """Client-specific message handler with printing and first response tracking."""
    
    def __init__(self, debug: bool = False):
        super().__init__(debug=debug, track_word_ttfw=False)
        self.first_response_time = None
        self.first_audio_sent = None
    
    def set_first_audio_sent(self, timestamp: float):
        """Set the timestamp when first audio was sent."""
        if self.first_audio_sent is None:
            self.first_audio_sent = timestamp
    
    def handle_partial_text(self, data: dict, now: float, t0: float):
        """Handle Partial/Text messages with printing."""
        super().handle_partial_text(data, now, t0)
        txt = (data.get("text") or "").strip()
        if txt:
            # Track first response latency
            if self.first_response_time is None and self.first_audio_sent is not None:
                self.first_response_time = now - self.first_audio_sent
            if txt != self.last_text:
                print(f"PART: {txt}")
    
    def handle_word(self, data: dict, now: float, t0: float):
        """Handle Word messages with selective printing."""
        super().handle_word(data, now, t0)
        w = (data.get("text") or data.get("word") or "").strip()
        if w:
            # Track first response latency
            if self.first_response_time is None and self.first_audio_sent is not None:
                self.first_response_time = now - self.first_audio_sent
            # Print occasional words, not every single one
            if len(self.words) % 5 == 1 or len(self.words) <= 3:
                print(f"WORD: {w!r}, assembled: {self.final_text!r}")
    
    def handle_final_marker(self, data: dict, now: float):
        """Handle Final/Marker messages with printing."""
        pending = self.eos_decider.get_pending_word()
        if pending:
            self.words.append(pending)
            print(f"Added pending word on Final: {pending!r}")
            if (not self.final_text) or len(self.final_text.split()) < len(self.words):
                self.final_text = " ".join(self.words).strip()
        
        txt = (data.get("text") or "").strip()
        if txt:
            self.final_text = txt
        self.final_recv_ts = now
        self.done_event.set()
    
    def handle_end_word(self, data: dict):
        """Handle EndWord messages with printing."""
        super().handle_end_word(data)
        w = (data.get("text") or data.get("word") or "").strip()
        if w:
            print(f"EndWord pending: {w!r}")
    
    def handle_connection_close(self):
        """Handle connection close with printing."""
        if not self.done_event.is_set():
            pending = self.eos_decider.get_pending_word()
            if pending:
                self.words.append(pending)
                print(f"Added pending word on close: {pending!r}")
            
            if self.words or self.final_text:
                self.final_recv_ts = time.perf_counter()
                if not self.final_text and self.words:
                    self.final_text = " ".join(self.words).strip()
                self.done_event.set()
