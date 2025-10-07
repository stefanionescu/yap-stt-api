"""Benchmark client for load testing Yap STT API."""
from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from utils.messages import BenchMessageHandler
from utils.metrics import calculate_basic_metrics, calculate_detailed_metrics
from clients.base import QueryAuthClient


class CapacityRejected(Exception):
    """Raised when server rejects due to capacity."""
    pass


class BenchmarkClient(QueryAuthClient):
    """Client for benchmark testing with capacity handling."""
    
    async def run_single_session(self, pcm_bytes: bytes, rtf: float) -> Dict[str, float]:
        """Run a single benchmark session."""
        handler = BenchMessageHandler(debug=self.debug)
        file_duration_s = len(pcm_bytes) // 2 / 24000.0
        
        t0, last_signal_ts = await self.connect_and_process(pcm_bytes, rtf, handler)
        
        # Check for capacity rejection
        if handler.reject_reason == "capacity":
            raise CapacityRejected("no free channels")
        
        # Calculate metrics
        wall = time.perf_counter() - t0
        basic_metrics = calculate_basic_metrics(file_duration_s, wall, handler.ttfw_word, handler.ttfw_text)
        
        # Create a mock streamer for detailed metrics (since we don't have access to the real one)
        class MockStreamer:
            def __init__(self):
                self.last_chunk_sent_ts = t0 + 0.1  # Rough estimate
        
        streamer = MockStreamer()
        detailed_metrics = calculate_detailed_metrics(handler, streamer, t0, last_signal_ts, file_duration_s, rtf)
        
        return {**basic_metrics, **detailed_metrics}


class BenchmarkRunner:
    """Runs benchmark tests with concurrency control."""
    
    def __init__(self, server: str, secure: bool = False, debug: bool = False):
        self.server = server
        self.secure = secure
        self.debug = debug
        self.results_dir = Path("test/results")
        self.errors_file = self.results_dir / "bench_errors.txt"
    
    async def run_benchmark(self, pcm_bytes: bytes, total_reqs: int, concurrency: int, 
                          rtf: float) -> Tuple[List[Dict[str, float]], int, int]:
        """Run benchmark with specified parameters."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize error log
        try:
            with open(self.errors_file, "w", encoding="utf-8") as ef:
                ef.write(f"=== Benchmark Error Log Started at {datetime.utcnow().isoformat()}Z ===\n")
        except Exception:
            pass
        
        sem = asyncio.Semaphore(max(1, concurrency))
        results: List[Dict[str, float]] = []
        rejected = 0
        errors_total = 0
        
        async def worker(req_idx: int):
            nonlocal errors_total, rejected
            async with sem:
                # Stagger stream starts with jitter to avoid thundering-herd
                if req_idx > 0:
                    await asyncio.sleep((req_idx % 32) * 0.025)
                
                try:
                    client = BenchmarkClient(self.server, self.secure, self.debug)
                    
                    # Dynamic timeout
                    audio_seconds = len(pcm_bytes) // 2 / 24000.0
                    timeout = max(300.0, audio_seconds * 2 + 60.0)
                    
                    result = await asyncio.wait_for(
                        client.run_single_session(pcm_bytes, rtf), 
                        timeout=timeout
                    )
                    results.append(result)
                    
                except CapacityRejected as e:
                    rejected += 1
                    self._log_error(req_idx, f"REJECTED capacity: {e}")
                    
                except Exception as e:
                    errors_total += 1
                    self._log_error(req_idx, f"err={e}")
        
        # Run all workers
        tasks = [asyncio.create_task(worker(i)) for i in range(total_reqs)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results[:total_reqs], rejected, errors_total
    
    def _log_error(self, req_idx: int, message: str) -> None:
        """Log error to file."""
        try:
            with open(self.errors_file, "a", encoding="utf-8") as ef:
                ef.write(f"{datetime.utcnow().isoformat()}Z idx={req_idx} {message}\n")
        except Exception:
            pass
    
    def save_results(self, results: List[Dict[str, float]]) -> None:
        """Save benchmark results to file."""
        try:
            self.results_dir.mkdir(parents=True, exist_ok=True)
            metrics_path = self.results_dir / "bench_metrics.jsonl"
            with open(metrics_path, "w", encoding="utf-8") as f:
                for rec in results:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"Saved per-stream metrics to {metrics_path}")
        except Exception as e:
            print(f"Warning: could not write metrics JSONL: {e}")
