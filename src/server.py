from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional
import base64
import uuid

import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect, Form, Request
from pydantic import BaseModel
import onnxruntime as ort

from .audio import decode_and_resample, DecodedAudio
from .config import settings
from .logging_config import configure_logging
from .metrics import Timer, RequestMetrics, log_request
from .model import ParakeetModel
from .scheduler import MicroBatchScheduler

logger = logging.getLogger("parakeet.server")
configure_logging()
app = FastAPI(title="Parakeet ASR (ONNX)")

# Global runtime state
_model: ParakeetModel | None = None
_scheduler: MicroBatchScheduler | None = None
_is_ready: bool = False


class TranscriptionResponse(BaseModel):
    text: str


@app.on_event("startup")
async def on_startup() -> None:
    global _model, _scheduler, _is_ready
    logger.info("Available ORT providers: %s", ort.get_available_providers())
    if settings.model_dir:
        try:
            import os
            abs_dir = os.path.abspath(settings.model_dir)
        except Exception:
            abs_dir = settings.model_dir  # best-effort
        logger.info("Using local ONNX: dir=%s name=%s", abs_dir, settings.model_name)
        _model = ParakeetModel.load_local(
            settings.model_name,
            settings.model_dir,
            require_gpu=settings.require_gpu,
        )
    else:
        logger.info("Using hub id: %s (fallback=%s)", settings.model_id, settings.fallback_model_id)
        _model = ParakeetModel.load_with_fallback(
            settings.model_id,
            settings.fallback_model_id,
            require_gpu=settings.require_gpu,
        )
    logger.info("Model loaded from: %s", _model.model_id)
    logger.info("Warming up...")
    _model.warmup(seconds=0.5)
    logger.info("Warmup done.")

    maxsize = settings.queue_max_factor * settings.microbatch_max_batch
    # Prefer micro-batching for better GPU utilization
    def run_batch_fn(wavs: list[np.ndarray], srs: list[int]) -> list[str]:
        return _model.recognize_waveforms(wavs, srs)  # type: ignore[union-attr]

    _scheduler = MicroBatchScheduler(
        maxsize=maxsize,
        run_batch_fn=run_batch_fn,
        window_ms=settings.microbatch_window_ms,
        max_batch=settings.microbatch_max_batch,
    )
    _scheduler.start()
    _is_ready = True
    logger.info("MicroBatchScheduler started (window_ms=%s, max_batch=%s, queue maxsize=%d)",
                settings.microbatch_window_ms, settings.microbatch_max_batch, maxsize)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global _scheduler, _is_ready
    if _scheduler is not None:
        await _scheduler.stop()
    _is_ready = False


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {"status": "ok", "model": settings.model_id}


@app.get("/readyz")
async def readyz() -> Dict[str, Any]:
    return {"ready": bool(_is_ready)}


@app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def openai_transcribe(
    request: Request,
    file: UploadFile | None = File(None),
) -> TranscriptionResponse:
    global _scheduler, _model
    if _scheduler is None or _model is None or not _is_ready:
        raise HTTPException(status_code=503, detail="Model not initialized")

    # Input size validation
    # Support multipart (UploadFile) or raw body (Content-Type: audio/pcm or application/octet-stream)
    content_length = None
    if file is not None and hasattr(file, "size"):
        content_length = file.size  # type: ignore[attr-defined]
    else:
        try:
            content_length = int(request.headers.get("content-length", "0")) or None
        except Exception:
            content_length = None
    if content_length is not None:
        max_bytes = int(settings.max_upload_mb * 1024 * 1024)
        if content_length > max_bytes:
            raise HTTPException(status_code=413, detail="Upload too large")

    # Admission control — immediate 429 if full to keep latency predictable
    if _scheduler.queue.full():
        headers = {"Retry-After": str(int(settings.max_queue_wait_s))}
        raise HTTPException(status_code=429, detail="Busy, try again later", headers=headers)

    if file is not None:
        raw = await file.read()
        if content_length is None:
            max_bytes = int(settings.max_upload_mb * 1024 * 1024)
            if len(raw) > max_bytes:
                raise HTTPException(status_code=413, detail="Upload too large")

        filename = (file.filename or "").lower()
        content_type = (file.content_type or "").lower()
    else:
        raw = await request.body()
        if content_length is None:
            max_bytes = int(settings.max_upload_mb * 1024 * 1024)
            if len(raw) > max_bytes:
                raise HTTPException(status_code=413, detail="Upload too large")
        filename = ""
        content_type = (request.headers.get("content-type") or "").lower()

    # Accept containerized audio (mp3/ogg/wav/flac/...) and also raw PCM16 mono 16kHz (filename .pcm/.raw or audio/pcm)
    if filename.endswith((".pcm", ".raw")) or content_type in ("audio/pcm", "audio/l16"):
        try:
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            sr = 16000
            decoded = DecodedAudio(waveform=pcm, sample_rate=sr, duration_seconds=float(len(pcm) / sr))
        except Exception as e:
            raise HTTPException(status_code=415, detail=f"Invalid PCM payload: {e}")
    else:
        decoded = decode_and_resample(raw)
    if decoded.duration_seconds > settings.max_audio_seconds:
        raise HTTPException(status_code=413, detail="Audio too long")

    # Queue submit
    fut = _scheduler.submit(decoded.waveform, decoded.sample_rate)
    try:
        text, _inference_dt, _queue_wait_s = await asyncio.wait_for(
            fut, timeout=settings.max_queue_wait_s
        )  # type: ignore[misc]
    except asyncio.TimeoutError:
        if not fut.done():
            fut.cancel()
        raise HTTPException(status_code=503, detail="Queue wait timeout")

    return TranscriptionResponse(text=text)


@app.websocket("/v1/realtime")
async def ws_realtime(ws: WebSocket) -> None:
    await ws.accept()
    if _scheduler is None or _model is None or not _is_ready:
        await ws.send_json({"type": "error", "error": "model_not_ready"})
        await ws.close(code=1013)
        return

    # Send session created event
    await ws.send_json({"type": "session.created", "id": str(uuid.uuid4())})

    audio_buf = bytearray()

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "session.update" or mtype == "session.create":
                await ws.send_json({"type": "session.updated"})

            elif mtype == "input_audio_buffer.append":
                # Expect base64-encoded PCM16 mono 16 kHz
                b64 = msg.get("audio") or msg.get("audio_base64")
                if not isinstance(b64, str):
                    await ws.send_json({"type": "error", "error": "missing_audio_base64"})
                    continue
                try:
                    audio_buf.extend(base64.b64decode(b64))
                except Exception:
                    await ws.send_json({"type": "error", "error": "invalid_base64"})

            elif mtype == "input_audio_buffer.clear":
                audio_buf.clear()
                await ws.send_json({"type": "input_audio_buffer.cleared"})

            elif mtype == "input_audio_buffer.commit":
                await ws.send_json({"type": "input_audio_buffer.committed"})

            elif mtype == "response.create":
                # Transcribe accumulated buffer
                if not audio_buf:
                    await ws.send_json({"type": "error", "error": "no_audio"})
                    continue
                # Admission control — immediate backpressure for realtime
                if _scheduler.queue.full():
                    await ws.send_json({"type": "error", "error": "busy"})
                    continue
                pcm = np.frombuffer(bytes(audio_buf), dtype=np.int16).astype(np.float32) / 32768.0
                fut = _scheduler.submit(pcm, 16000)
                try:
                    text, _inf, _q = await asyncio.wait_for(fut, timeout=settings.max_queue_wait_s)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "error", "error": "queue_timeout"})
                    continue

                await ws.send_json({"type": "response.output_text.delta", "delta": text})
                await ws.send_json({"type": "response.completed"})
                # reset buffer for next turn
                audio_buf.clear()

            else:
                await ws.send_json({"type": "error", "error": "unsupported_type"})

    except WebSocketDisconnect:
        pass
