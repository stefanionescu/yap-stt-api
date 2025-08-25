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
        scheduler: MicroBatchScheduler,
        *,
        step_ms: float,
        max_ctx_seconds: float,
    ):
        self.model = model
        self.scheduler = scheduler
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
        # VAD knobs (used only for segmentation cut selection; not gating interims)
        self.vad_enable = bool(settings.vad_enable)
        self.vad_tail_samples = int((float(settings.vad_tail_ms) / 1000.0) * SAMPLE_RATE)
        self.vad_energy_threshold = float(settings.vad_energy_threshold)
        self.eager_sil_ms = float(settings.eager_sil_ms)

        # Segmentation sizes in bytes (16 kHz, PCM16)
        self.seg_len_bytes = int((settings.segment_len_ms / 1000.0) * SAMPLE_RATE * BYTES_PER_SAMPLE)
        self.seg_min_bytes = int((settings.segment_min_ms / 1000.0) * SAMPLE_RATE * BYTES_PER_SAMPLE)
        self.seg_overlap_bytes = int((settings.segment_overlap_ms / 1000.0) * SAMPLE_RATE * BYTES_PER_SAMPLE)
        self.sil_win_bytes = int((settings.vad_tail_ms / 1000.0) * SAMPLE_RATE * BYTES_PER_SAMPLE)

        def _is_silence(pcm_tail: np.ndarray) -> bool:
            if pcm_tail.size == 0:
                return True
            return float(np.mean(pcm_tail * pcm_tail)) < self.vad_energy_threshold

        # Bind helper as instance method
        self._is_silence = _is_silence

    async def StreamingRecognize(self, request_iterator, context):  # type: ignore[override]
        cfg = None
        # Rolling context buffer (bounded) for partials and full buffer for final
        ctx_buf = bytearray()
        full_buf = bytearray()
        # Track bytes since last emit to gate cadence
        since_last_emit = 0
        last_emit_monotonic = 0.0
        # Segmented finals state
        pending_segments: list[tuple[asyncio.Future, int]] = []
        seg_idx = 0
        seg_start_bytes = 0

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

            fut = self.scheduler.submit(pcm, SAMPLE_RATE, priority=1)
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

            # ----- Segmentation for finals (do NOT block the main loop) -----
            since_seg = len(full_buf) - seg_start_bytes

            should_cut = False
            # Always enforce a hard max segment length
            if since_seg >= self.seg_len_bytes:
                should_cut = True
            elif since_seg >= self.seg_min_bytes:
                tail_len = min(self.sil_win_bytes, since_seg)
                tail_pcm = pcm16_to_f32(memoryview(full_buf[-tail_len:])[:]) if tail_len > 0 else np.asarray([], dtype=np.float32)
                if self._is_silence(tail_pcm):
                    should_cut = True

            if should_cut:
                seg_end_bytes = len(full_buf)
                overlap = self.seg_overlap_bytes
                seg_slice = full_buf[seg_start_bytes : min(seg_end_bytes + overlap, len(full_buf))]
                seg_pcm = pcm16_to_f32(memoryview(seg_slice)[:])

                fut2 = self.scheduler.submit(seg_pcm, SAMPLE_RATE, priority=0)
                pending_segments.append((fut2, seg_idx))
                seg_idx += 1

                keep = min(overlap, len(full_buf))
                if keep:
                    del full_buf[:-keep]
                    seg_start_bytes = 0
                else:
                    full_buf.clear()
                    seg_start_bytes = 0

            # Emit any completed segment finals
            if pending_segments:
                done_now: list[tuple[asyncio.Future, int]] = []
                for fut3, idx in pending_segments:
                    if fut3.done():
                        try:
                            text2, *_ = fut3.result()
                        except Exception as e:  # noqa: BLE001
                            await context.abort(grpc.StatusCode.INTERNAL, f"final_segment_error: {e}")
                            return
                        text2 = (text2 or "").strip()
                        if text2:
                            yield riva_asr_pb2.StreamingRecognizeResponse(
                                results=[
                                    riva_asr_pb2.StreamingRecognitionResult(
                                        alternatives=[riva_asr_pb2.SpeechRecognitionAlternative(transcript=text2)],
                                        is_final=True,
                                    )
                                ]
                            )
                        done_now.append((fut3, idx))
                if done_now:
                    pending_segments = [p for p in pending_segments if p not in done_now]

        # ----- End of stream: flush the small tail only -----
        if len(full_buf) > 0:
            tail_pcm = pcm16_to_f32(memoryview(full_buf)[:])
            fut4 = self.scheduler.submit(tail_pcm, SAMPLE_RATE, priority=0)
            try:
                text3, *_ = await asyncio.wait_for(fut4, timeout=float(settings.finals_timeout_s))
            except Exception as e:  # noqa: BLE001
                await context.abort(grpc.StatusCode.INTERNAL, f"final_tail_error: {e}")
                return
            text3 = (text3 or "").strip()
            if text3:
                yield riva_asr_pb2.StreamingRecognizeResponse(
                    results=[
                        riva_asr_pb2.StreamingRecognitionResult(
                            alternatives=[riva_asr_pb2.SpeechRecognitionAlternative(transcript=text3)],
                            is_final=True,
                        )
                    ]
                )

        # Emit any still-pending segment results
        for fut5, idx in pending_segments:
            try:
                text4, *_ = await asyncio.wait_for(fut5, timeout=float(settings.finals_timeout_s))
            except Exception as e:  # noqa: BLE001
                await context.abort(grpc.StatusCode.INTERNAL, f"final_segment_error: {e}")
                return
            text4 = (text4 or "").strip()
            if text4:
                yield riva_asr_pb2.StreamingRecognizeResponse(
                    results=[
                        riva_asr_pb2.StreamingRecognitionResult(
                            alternatives=[riva_asr_pb2.SpeechRecognitionAlternative(transcript=text4)],
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
    scheduler: MicroBatchScheduler,
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


