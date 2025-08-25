from __future__ import annotations

import asyncio
import logging
from typing import Optional

import grpc
import numpy as np

# Using NVIDIA's packaged protos (no local compile needed)
from riva.client.proto import riva_asr_pb2, riva_asr_pb2_grpc  # type: ignore
import riva.client.proto.types.audio_pb2 as riva_audio_pb2  # type: ignore

from .model import ParakeetModel
from .scheduler import MicroBatchScheduler
from .config import settings


LOGGER = logging.getLogger("parakeet.riva_grpc")

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # PCM16


def pcm16_to_f32(buf: bytes) -> np.ndarray:
    return (np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0)


class RivaASRServicer(riva_asr_pb2_grpc.RivaSpeechRecognitionServicer):
    def __init__(self, model: ParakeetModel, scheduler: MicroBatchScheduler, *, step_ms: float, max_ctx_seconds: float):
        self.model = model
        self.scheduler = scheduler
        # Convert cadence to bytes at 16k PCM16
        self.step_bytes = int((step_ms / 1000.0) * SAMPLE_RATE * BYTES_PER_SAMPLE)
        # Bound context to keep compute stable per tick
        self.max_ctx_samps = int(max_ctx_seconds * SAMPLE_RATE)
        self.max_ctx_bytes = int(self.max_ctx_samps * BYTES_PER_SAMPLE)
        # Backpressure / decimation config
        self.decimation_min_interval_s = max(0.0, float(settings.stream_decimation_min_interval_ms) / 1000.0)
        self.decimation_when_hot = bool(settings.stream_decimation_when_hot)
        self.hot_queue_threshold = max(0.0, min(1.0, float(settings.stream_hot_queue_fraction)))
        self.tick_timeout_s = float(settings.stream_tick_timeout_s)

    async def StreamingRecognize(self, request_iterator, context):  # type: ignore[override]
        cfg = None
        buf = bytearray()
        last_emit_monotonic = 0.0

        first = True
        async for req in request_iterator:
            if first:
                first = False
                if not req.HasField("streaming_config"):
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "first message must include streaming_config")
                cfg = req.streaming_config
                # Minimal validation; support only LINEAR_PCM mono 16 kHz
                if cfg.config.encoding != getattr(riva_audio_pb2, "LINEAR_PCM", 1):
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "only LINEAR_PCM supported")
                continue

            if not req.audio_content:
                continue

            buf.extend(req.audio_content)

            # Emit at cadence governed by step_bytes, but optionally decimate under load
            if len(buf) >= self.step_bytes:
                now_mono = asyncio.get_running_loop().time()
                queue_fraction = 0.0
                try:
                    queue_fraction = self.scheduler.qsize() / max(1, self.scheduler.maxsize())
                except Exception:
                    pass

                # Decimation: if hot and last emit was too recent, skip this tick
                if self.decimation_when_hot and queue_fraction >= self.hot_queue_threshold:
                    if (now_mono - last_emit_monotonic) < self.decimation_min_interval_s:
                        # drop this partial emit to reduce pressure; keep rolling context bounded
                        if len(buf) > self.max_ctx_bytes:
                            # trim to last max_ctx_bytes
                            del buf[:-self.max_ctx_bytes]
                        continue

                pcm = pcm16_to_f32(memoryview(buf)[:])
                if pcm.shape[0] > self.max_ctx_samps:
                    # Keep only rightmost max_ctx_samps; model will re-use limited left context implicit in audio
                    pcm = pcm[-self.max_ctx_samps :]

                fut = self.scheduler.submit(pcm, SAMPLE_RATE)
                try:
                    text, *_ = await asyncio.wait_for(fut, timeout=self.tick_timeout_s)
                except asyncio.TimeoutError:
                    # Skip missed tick; bound rolling context so we don't grow unbounded
                    if len(buf) > self.max_ctx_bytes:
                        del buf[:-self.max_ctx_bytes]
                    continue
                except Exception as e:  # noqa: BLE001
                    await context.abort(grpc.StatusCode.INTERNAL, f"inference_error: {e}")

                last_emit_monotonic = now_mono
                # retain only last max_ctx_bytes as rolling context for next tick
                if len(buf) > self.max_ctx_bytes:
                    del buf[:-self.max_ctx_bytes]

                yield riva_asr_pb2.StreamingRecognizeResponse(
                    results=[
                        riva_asr_pb2.StreamingRecognitionResult(
                            alternatives=[riva_asr_pb2.SpeechRecognitionAlternative(transcript=text)],
                            is_final=False,
                            stability=0.5,
                        )
                    ]
                )

        # Final flush
        if buf:
            try:
                pcm = pcm16_to_f32(memoryview(buf)[:])
                text = self.model.recognize_waveform(pcm, SAMPLE_RATE)
            except Exception as e:  # noqa: BLE001
                await context.abort(grpc.StatusCode.INTERNAL, f"final_inference_error: {e}")
                return
            yield riva_asr_pb2.StreamingRecognizeResponse(
                results=[
                    riva_asr_pb2.StreamingRecognitionResult(
                        alternatives=[riva_asr_pb2.SpeechRecognitionAlternative(transcript=text)],
                        is_final=True,
                    )
                ]
            )

    async def Recognize(self, request, context):  # type: ignore[override]
        if request.config.encoding != getattr(riva_audio_pb2, "LINEAR_PCM", 1):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "only LINEAR_PCM supported")
        sr = request.config.sample_rate_hertz or SAMPLE_RATE
        if sr != SAMPLE_RATE:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "expected 16 kHz")
        try:
            pcm = pcm16_to_f32(request.audio)
            text = self.model.recognize_waveform(pcm, sr)
        except Exception as e:  # noqa: BLE001
            await context.abort(grpc.StatusCode.INTERNAL, f"inference_error: {e}")
        return riva_asr_pb2.RecognizeResponse(
            results=[
                riva_asr_pb2.SpeechRecognitionResult(
                    alternatives=[riva_asr_pb2.SpeechRecognitionAlternative(transcript=text)]
                )
            ]
        )


async def start_riva_grpc_server(
    model: ParakeetModel,
    scheduler: MicroBatchScheduler,
    *,
    port: int,
    secure: bool = False,
    cert: Optional[str] = None,
    key: Optional[str] = None,
    step_ms: Optional[float] = None,
    max_ctx_seconds: Optional[float] = None,
):
    opts = [("grpc.max_receive_message_length", 64 * 1024 * 1024)]
    server = grpc.aio.server(options=opts)
    servicer = RivaASRServicer(
        model,
        scheduler,
        step_ms=step_ms if step_ms is not None else float(getattr(settings, "stream_step_ms", 320.0)),
        max_ctx_seconds=max_ctx_seconds if max_ctx_seconds is not None else float(getattr(settings, "stream_context_seconds", 10.0)),
    )
    riva_asr_pb2_grpc.add_RivaSpeechRecognitionServicer_to_server(servicer, server)
    if secure:
        if not cert or not key:
            raise RuntimeError("TLS enabled but cert/key not provided")
        with open(cert, "rb") as f:
            cert_chain = f.read()
        with open(key, "rb") as f:
            private_key = f.read()
        creds = grpc.ssl_server_credentials(((private_key, cert_chain),))
        server.add_secure_port(f"[::]:{port}", creds)
    else:
        server.add_insecure_port(f"[::]:{port}")

    await server.start()
    LOGGER.info("Riva-compatible gRPC ASR listening on %s (secure=%s)", port, secure)
    return server


