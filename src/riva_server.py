from __future__ import annotations

import asyncio
import logging
from typing import Optional

import grpc
import numpy as np

# Using NVIDIA's packaged protos (no local compile needed)
from riva.client.proto import riva_asr_pb2, riva_asr_pb2_grpc  # type: ignore
import riva.client as riva_client  # type: ignore
AudioEncoding = riva_client.AudioEncoding

from .model import ParakeetModel
from .scheduler import MicroBatchScheduler
from .config import settings


LOGGER = logging.getLogger("parakeet.riva_grpc")

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # PCM16


def pcm16_to_f32(buf: bytes) -> np.ndarray:
    return (np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0)


class RivaASRServicer(riva_asr_pb2_grpc.RivaSpeechRecognitionServicer):
    def __init__(
        self,
        model: ParakeetModel,
        scheduler_partials: MicroBatchScheduler,
        finals_scheduler: MicroBatchScheduler,
        *,
        step_ms: float,
        max_ctx_seconds: float,
    ):
        self.model = model
        self.scheduler = scheduler_partials
        self.finals_scheduler = finals_scheduler
        # Tick cadence
        self.step_ms = float(step_ms)
        # Convert cadence to bytes at 16k PCM16
        self.step_bytes = int((self.step_ms / 1000.0) * SAMPLE_RATE * BYTES_PER_SAMPLE)
        # Bound context to keep compute stable per tick
        self.max_ctx_samps = int(max_ctx_seconds * SAMPLE_RATE)
        self.max_ctx_bytes = int(self.max_ctx_samps * BYTES_PER_SAMPLE)
        # Backpressure / decimation config
        self.decimation_min_interval_s = max(0.0, float(settings.stream_decimation_min_interval_ms) / 1000.0)
        self.decimation_when_hot = bool(settings.stream_decimation_when_hot)
        self.hot_queue_threshold = max(0.0, min(1.0, float(settings.stream_hot_queue_fraction)))
        self.tick_timeout_s = float(settings.stream_tick_timeout_s)
        # VAD gating and eager finalize
        self.vad_enable = bool(settings.vad_enable)
        self.vad_tail_samples = int((float(settings.vad_tail_ms) / 1000.0) * SAMPLE_RATE)
        self.vad_energy_threshold = float(settings.vad_energy_threshold)
        self.eager_sil_ms = float(settings.eager_sil_ms)

    async def StreamingRecognize(self, request_iterator, context):  # type: ignore[override]
        cfg = None
        # Rolling context buffer (bounded) for partials and full buffer for final
        ctx_buf = bytearray()
        full_buf = bytearray()
        # Track bytes since last emit to gate cadence
        since_last_emit = 0
        last_emit_monotonic = 0.0
        # VAD/eager finalize state
        silence_run_ms: float = 0.0
        final_fut: Optional[asyncio.Future] = None

        first = True
        async for req in request_iterator:
            if first:
                first = False
                if not req.HasField("streaming_config"):
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "first message must include streaming_config")
                cfg = req.streaming_config
                # Minimal validation; support only LINEAR_PCM mono 16 kHz
                if cfg.config.encoding != AudioEncoding.LINEAR_PCM:
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "only LINEAR_PCM supported")
                # Respect interim_results if present (default True)
                interim = getattr(cfg, "interim_results", True)
                continue

            if not req.audio_content:
                continue

            chunk = req.audio_content
            full_buf.extend(chunk)
            ctx_buf.extend(chunk)
            since_last_emit += len(chunk)

            # Bound rolling context buffer
            if len(ctx_buf) > self.max_ctx_bytes:
                del ctx_buf[:-self.max_ctx_bytes]

            # Only emit when NEW audio since last emit crosses cadence
            if since_last_emit < self.step_bytes:
                continue

            now_mono = asyncio.get_running_loop().time()
            queue_fraction = 0.0
            try:
                queue_fraction = self.scheduler.qsize() / max(1, self.scheduler.maxsize())
            except Exception:
                pass

            # Decimate under heat if needed
            if self.decimation_when_hot and queue_fraction >= self.hot_queue_threshold:
                if (now_mono - last_emit_monotonic) < self.decimation_min_interval_s:
                    continue

            pcm = pcm16_to_f32(memoryview(ctx_buf)[:])
            if pcm.shape[0] > self.max_ctx_samps:
                pcm = pcm[-self.max_ctx_samps :]

            # Simple VAD gating: if tail energy is low, skip tick and build up silence window
            if self.vad_enable and pcm.shape[0] > 0:
                tail = pcm[-min(self.vad_tail_samples, pcm.shape[0]) :]
                if tail.size > 0 and float(np.mean(tail * tail)) < self.vad_energy_threshold:
                    silence_run_ms = min(2000.0, silence_run_ms + self.step_ms)
                    # Fire eager finalize once per stream when sufficient trailing silence is detected
                    if final_fut is None and silence_run_ms >= self.eager_sil_ms and len(full_buf) > 0:
                        full_pcm = pcm16_to_f32(memoryview(full_buf)[:])
                        final_fut = self.finals_scheduler.submit(full_pcm, SAMPLE_RATE)
                    # Skip this tick during silence
                    continue
                else:
                    silence_run_ms = 0.0

            fut = self.scheduler.submit(pcm, SAMPLE_RATE)
            try:
                text, *_ = await asyncio.wait_for(fut, timeout=self.tick_timeout_s)
            except asyncio.TimeoutError:
                continue
            except Exception as e:  # noqa: BLE001
                await context.abort(grpc.StatusCode.INTERNAL, f"inference_error: {e}")

            last_emit_monotonic = now_mono
            since_last_emit = 0

            if interim:
                yield riva_asr_pb2.StreamingRecognizeResponse(
                    results=[
                        riva_asr_pb2.StreamingRecognitionResult(
                            alternatives=[riva_asr_pb2.SpeechRecognitionAlternative(transcript=text)],
                            is_final=False,
                            stability=0.5,
                        )
                    ]
                )

        # Final flush over the full session buffer
        if full_buf:
            try:
                if final_fut is not None:
                    text, *_ = await asyncio.wait_for(final_fut, timeout=float(settings.finals_timeout_s))
                else:
                    full_pcm = pcm16_to_f32(memoryview(full_buf)[:])
                    fut = self.finals_scheduler.submit(full_pcm, SAMPLE_RATE)
                    text, *_ = await asyncio.wait_for(fut, timeout=float(settings.finals_timeout_s))
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
        if request.config.encoding != AudioEncoding.LINEAR_PCM:
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
    scheduler_partials: MicroBatchScheduler,
    finals_scheduler: MicroBatchScheduler,
    *,
    port: int,
    secure: bool = False,
    cert: Optional[str] = None,
    key: Optional[str] = None,
    step_ms: Optional[float] = None,
    max_ctx_seconds: Optional[float] = None,
):
    opts = [
        ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ("grpc.max_send_message_length", 64 * 1024 * 1024),
        ("grpc.http2.max_pings_without_data", 0),
        ("grpc.keepalive_permit_without_calls", 1),
        ("grpc.keepalive_time_ms", 30000),
        ("grpc.keepalive_timeout_ms", 20000),
    ]
    server = grpc.aio.server(options=opts)
    servicer = RivaASRServicer(
        model,
        scheduler_partials,
        finals_scheduler,
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


