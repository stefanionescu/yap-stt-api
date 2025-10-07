"""Warmup client for health checking Yap STT API."""
from __future__ import annotations
import json
from pathlib import Path

from utils.messages import MessageHandler
from utils.metrics import calculate_detailed_metrics
from clients.base import QueryAuthClient


class WarmupClient(QueryAuthClient):
    """Simple client for warmup/health check operations."""
    
    async def run_warmup(self, pcm_bytes: bytes, rtf: float, debug: bool = False) -> dict:
        """Run warmup test and return metrics."""
        handler = MessageHandler(debug=debug, track_word_ttfw=False)
        file_duration_s = len(pcm_bytes) // 2 / 24000.0
        
        t0, last_signal_ts = await self.connect_and_process(pcm_bytes, rtf, handler)
        
        # Create a mock streamer for metrics calculation
        class MockStreamer:
            def __init__(self):
                self.last_chunk_sent_ts = t0 + 0.1  # Rough estimate
        
        streamer = MockStreamer()
        metrics = calculate_detailed_metrics(handler, streamer, t0, last_signal_ts, file_duration_s, rtf)
        
        return {
            "text": handler.final_text,
            "elapsed_s": last_signal_ts - t0,
            "ttfw_s": handler.ttfw,
            "partials": len(handler.partial_ts),
            "audio_s": file_duration_s,
            **metrics
        }
    
    def save_results(self, results: dict, duration: float) -> None:
        """Save warmup results to file."""
        results_dir = Path("test/results")
        results_file = results_dir / "warmup.txt"
        
        results_dir.mkdir(parents=True, exist_ok=True)
        with open(results_file, "w", encoding="utf-8") as out:
            out.write(json.dumps({
                **results,
                "duration": duration,
            }, ensure_ascii=False))
            out.write("\n")
