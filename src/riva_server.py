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


def pcm16_to_f32(buf: bytes) -> np.ndarray:
    return (np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0)


class RivaASRServicer(riva_asr_pb2_grpc.RivaSpeechRecognitionServicer):
    def __init__(self, model: ParakeetModel, scheduler: MicroBatchScheduler):
        self.model = model
        self.scheduler = scheduler

    async def StreamingRecognize(self, request_iterator, context):  # type: ignore[override]
        await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Use Recognize (one-shot segment API).")

    async def Recognize(self, request, context):  # type: ignore[override]
        if request.config.encoding != AudioEncoding.LINEAR_PCM:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "only LINEAR_PCM supported")
        sr = request.config.sample_rate_hertz or SAMPLE_RATE
        if sr != SAMPLE_RATE:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "expected 16 kHz")
        try:
            pcm = pcm16_to_f32(request.audio)
            audio_seconds = float(pcm.shape[0]) / float(SAMPLE_RATE)
            # Duration-aware timeout: safety * (audio / expected_xrt_min), capped
            expected = audio_seconds / max(0.01, float(settings.expected_xrt_min))
            timeout_s = min(float(settings.infer_timeout_cap_s), float(settings.infer_timeout_safety) * expected)
            fut = self.scheduler.submit(pcm, SAMPLE_RATE, priority=0)
            text, *_ = await asyncio.wait_for(fut, timeout=max(1.0, timeout_s))
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
    servicer = RivaASRServicer(model, scheduler)
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


