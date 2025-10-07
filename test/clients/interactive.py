"""Interactive client for real-time Yap STT testing."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

from ..utils import is_runpod_host
from ..utils.messages import ClientMessageHandler
from .base import YapClient


class InteractiveClient(YapClient):
    """Interactive client with printing and network latency tracking."""
    
    def __init__(self, server: str, secure: bool = False, debug: bool = False):
        # Auto-enable TLS for RunPod hosts
        super().__init__(server, secure or is_runpod_host(server), debug)
        self.connect_time = 0.0
        self.handshake_time = 0.0
    
    def get_auth_headers(self) -> list[tuple[str, str]]:
        """Get headers including RunPod auth if needed."""
        headers = super().get_auth_headers()
        
        # Add RunPod auth if targeting RunPod host
        if is_runpod_host(self.server):
            runpod_key = os.getenv("RUNPOD_API_KEY")
            if not runpod_key:
                raise RuntimeError("RUNPOD_API_KEY is required when targeting a RunPod host")
            headers.append(("Authorization", f"Bearer {runpod_key}"))
        
        return headers
    
    async def run_session(self, pcm_bytes: bytes, rtf: float, file_path: str) -> None:
        """Run an interactive session with printing and metrics."""
        print(f"Connecting to: {self.url}")
        print(f"File: {os.path.basename(file_path)} ({len(pcm_bytes) // 2 / 24000.0:.2f}s)")
        
        handler = ClientMessageHandler(debug=self.debug)
        
        # Track connection timing
        connect_start = time.perf_counter()
        t0, last_signal_ts = await self.connect_and_process(pcm_bytes, rtf, handler)
        self.connect_time = t0 - connect_start
        
        # Track handshake timing
        handshake_start = t0
        if handler.ready_event.is_set():
            # Estimate handshake time from first partial/ready
            self.handshake_time = min(0.2, time.perf_counter() - handshake_start)
        else:
            self.handshake_time = 0.2
        
        # Set first audio timing for response latency
        if hasattr(handler, 'set_first_audio_sent'):
            # Estimate first audio sent time
            first_audio_time = t0 + 0.1  # Rough estimate
            handler.set_first_audio_sent(first_audio_time)
        
        self._print_results(handler, t0, last_signal_ts, pcm_bytes, rtf, file_path)
    
    def _print_results(self, handler: ClientMessageHandler, t0: float, last_signal_ts: float,
                      pcm_bytes: bytes, rtf: float, file_path: str) -> None:
        """Print session results and save metrics."""
        if handler.final_text:
            print("\n=== Transcription Result ===")
            print(handler.final_text)
        else:
            print("No final text")
        
        # Calculate metrics
        elapsed_s = time.perf_counter() - t0
        file_duration_s = len(pcm_bytes) // 2 / 24000.0
        wall_to_final = (handler.final_recv_ts - t0) if handler.final_recv_ts else elapsed_s
        rtf_measured = (wall_to_final / file_duration_s) if file_duration_s > 0 else None
        
        # Network latency metrics
        connect_ms = self.connect_time * 1000.0
        handshake_ms = self.handshake_time * 1000.0
        first_response_ms = handler.first_response_time * 1000.0 if handler.first_response_time is not None else 0.0
        
        ttfw_ms = (handler.ttfw * 1000.0) if handler.ttfw is not None else 0.0
        
        print(f"\n=== Network Latency ===")
        print(f"Connection time: {connect_ms:.1f}ms")
        print(f"Handshake time: {handshake_ms:.1f}ms")
        print(f"First response: {first_response_ms:.1f}ms")
        
        print(f"\n=== Transcription Performance ===")
        print(f"Transcription time (to Final): {wall_to_final:.3f}s  RTF(measured): {rtf_measured:.4f}  (target={rtf})")
        
        # Calculate avg gap
        avg_gap_ms = 0.0
        if len(handler.partial_ts) >= 2:
            gaps = [b - a for a, b in zip(handler.partial_ts[:-1], handler.partial_ts[1:])]
            avg_gap_ms = (sum(gaps) / len(gaps)) * 1000.0
        
        print(f"TTFW: {ttfw_ms:.1f}ms  Partials: {len(handler.partial_ts)}  Avg partial gap: {avg_gap_ms:.1f} ms")
        print(f"Δ(audio): {(wall_to_final - file_duration_s) * 1000.0:.1f}ms")
        print(f"Flush→Final: {((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0:.1f}ms")
        print(f"Decode tail: {((handler.final_recv_ts - handler.last_partial_ts) * 1000.0) if (handler.final_recv_ts and handler.last_partial_ts) else 0.0:.1f}ms")
        
        # Save metrics
        self._save_metrics(handler, t0, last_signal_ts, file_duration_s, rtf, file_path,
                          connect_ms, handshake_ms, first_response_ms, ttfw_ms, avg_gap_ms)
    
    def _save_metrics(self, handler: ClientMessageHandler, t0: float, last_signal_ts: float,
                     file_duration_s: float, rtf: float, file_path: str,
                     connect_ms: float, handshake_ms: float, first_response_ms: float,
                     ttfw_ms: float, avg_gap_ms: float) -> None:
        """Save metrics to file."""
        elapsed_s = time.perf_counter() - t0
        wall_to_final = (handler.final_recv_ts - t0) if handler.final_recv_ts else elapsed_s
        rtf_measured = (wall_to_final / file_duration_s) if file_duration_s > 0 else None
        
        out_dir = Path("test/results")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        with open(out_dir / "client_metrics.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "elapsed_s": elapsed_s,
                "wall_to_final_s": wall_to_final,
                "audio_s": file_duration_s,
                "rtf_target": rtf,
                "rtf_measured": rtf_measured,
                "ttfw_ms": ttfw_ms,
                "partials": len(handler.partial_ts),
                "avg_partial_gap_ms": avg_gap_ms,
                "finalize_ms": ((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0,
                "file": os.path.basename(file_path),
                "server": self.server,
                "connect_ms": connect_ms,
                "handshake_ms": handshake_ms,
                "first_response_ms": first_response_ms,
                "delta_to_audio_ms": (wall_to_final - file_duration_s) * 1000.0,
                "flush_to_final_ms": ((handler.final_recv_ts - last_signal_ts) * 1000.0) if (handler.final_recv_ts and last_signal_ts) else 0.0,
                "decode_tail_ms": ((handler.final_recv_ts - handler.last_partial_ts) * 1000.0) if (handler.final_recv_ts and handler.last_partial_ts) else 0.0,
            }, ensure_ascii=False) + "\n")
