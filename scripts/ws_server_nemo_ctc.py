#!/usr/bin/env python3
# WebSocket ASR server for NeMo FastConformer-CTC (streaming, 80 ms).
# Batching across clients, CUDA/TRT via ORT provider list in sherpa-onnx.
import argparse, asyncio, json, signal, time
from collections import deque
from typing import Dict, List, Optional
import numpy as np
import websockets

import sherpa_onnx as so  # pip install sherpa-onnx==1.12.10

# ---- Connection state -------------------------------------------------
class Conn:
    __slots__ = ("ws", "sid", "stream", "pcm_q", "last_emit", "finalized")
    def __init__(self, ws, sid, stream):
        self.ws = ws
        self.sid = sid
        self.stream = stream
        self.pcm_q: deque[np.ndarray] = deque()
        self.last_emit = 0.0
        self.finalized = False

# ---- Server -----------------------------------------------------------
class NemoCtcServer:
    def __init__(self, model_path: str, tokens: str, provider: str, num_threads: int,
                 max_batch: int, loop_ms: int):
        # Build recognizer config for NeMo CTC
        self.rec = so.OnlineRecognizer(
            config=so.OnlineRecognizerConfig(
                feat_config=so.FeatureConfig(sample_rate=16000, feature_dim=80),
                model=so.OnlineModelConfig(
                    nemo_ctc=so.OnlineNemoCtcModelConfig(
                        model=model_path, tokens=tokens,
                        num_threads=num_threads, provider=provider
                    )
                ),
                decoding_method="greedy_search",
            )
        )
        self.max_batch = max(1, int(max_batch))
        self.loop_ms = max(1, int(loop_ms))

        self.conns: Dict[str, Conn] = {}
        self._sid_counter = 0
        self._shutdown = asyncio.Event()

    def _sid(self) -> str:
        self._sid_counter += 1
        return f"c{self._sid_counter}"

    async def ws_handler(self, ws):
        sid = self._sid()
        stream = self.rec.create_stream()
        conn = Conn(ws, sid, stream)
        self.conns[sid] = conn
        try:
            await ws.send(json.dumps({"type": "hello", "sid": sid}))
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    # Expect PCM16 mono @16k. Convert to float32 [-1,1].
                    b = np.frombuffer(msg, dtype=np.int16).astype(np.float32) / 32768.0
                    conn.pcm_q.append(b)
                else:
                    # Control messages
                    try:
                        obj = json.loads(msg)
                    except Exception:
                        obj = {}
                    typ = obj.get("type")
                    if typ == "eos":
                        self.rec.input_finished(conn.stream)
                    elif typ == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
        except Exception:
            pass
        finally:
            self.conns.pop(sid, None)

    async def decode_loop(self):
        # Main micro-batching loop
        tick = self.loop_ms / 1000.0
        while not self._shutdown.is_set():
            # Feed audio to streams
            now = time.perf_counter()
            ready_streams: List[so.OnlineStream] = []
            batch: List[Conn] = []

            for conn in list(self.conns.values()):
                # Drain queued PCM into the stream
                while conn.pcm_q:
                    chunk = conn.pcm_q.popleft()
                    self.rec.accept_waveform(conn.stream, 16000, chunk)

                # Collect streams that are decode-ready
                if self.rec.is_ready(conn.stream):
                    ready_streams.append(conn.stream)
                    batch.append(conn)
                    if len(ready_streams) >= self.max_batch:
                        break

            # Decode current batch
            if ready_streams:
                self.rec.decode_streams(ready_streams)

                # Emit partials (at most every ~60ms per conn)
                for c in batch:
                    if (now - c.last_emit) >= 0.06:
                        r = self.rec.get_result(c.stream)
                        if r.text:
                            try:
                                asyncio.create_task(
                                    c.ws.send(json.dumps({"type": "partial", "text": r.text}))
                                )
                            except Exception:
                                pass
                            c.last_emit = now

            # Finalize any endpoints (silence/EOS)
            for c in list(self.conns.values()):
                if c.finalized:
                    continue
                if self.rec.is_endpoint(c.stream):
                    self.rec.finalize_segmentation(c.stream)
                    r = self.rec.get_result(c.stream)
                    if r.text:
                        try:
                            await c.ws.send(json.dumps({"type": "final", "text": r.text}))
                        except Exception:
                            pass
                # If input finished and nothing more to decode, close with final
                if self.rec.is_ready(c.stream):
                    # will be handled above
                    pass
                elif self.rec.is_input_finished(c.stream) and not self.rec.is_ready(c.stream):
                    r = self.rec.get_result(c.stream)
                    if r.text and not c.finalized:
                        try:
                            await c.ws.send(json.dumps({"type": "final", "text": r.text}))
                        except Exception:
                            pass
                    c.finalized = True

            await asyncio.sleep(tick)

    async def run(self, host: str, port: int, max_active: int):
        async def handler(ws, path):
            if len(self.conns) >= max_active:
                await ws.close(code=1013, reason="server busy")
                return
            return await self.ws_handler(ws)

        async with websockets.serve(handler, host, port, max_size=None, max_queue=None):
            await self._shutdown.wait()

    def stop(self):
        self._shutdown.set()

# ---- CLI ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokens", required=True)
    ap.add_argument("--provider", default="cuda", choices=["cuda","tensorrt","cpu"])
    ap.add_argument("--num-threads", type=int, default=1)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--max-batch-size", type=int, default=16)
    ap.add_argument("--loop-ms", type=int, default=15)
    ap.add_argument("--max-active", type=int, default=400)
    args = ap.parse_args()

    server = NemoCtcServer(args.model, args.tokens, args.provider, args.num_threads,
                           args.max_batch_size, args.loop_ms)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, server.stop)

    loop.create_task(server.decode_loop())
    loop.run_until_complete(server.run(args.host, args.port, args.max_active))

if __name__ == "__main__":
    main()
