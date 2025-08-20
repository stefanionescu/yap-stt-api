from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from .audio import decode_and_resample
from .config import settings
from .logging_config import configure_logging
from .metrics import Timer, RequestMetrics, log_request
from .model import ParakeetModel
from .scheduler import Scheduler, bucket_priority


logger = logging.getLogger("parakeet.server")
configure_logging()
app = FastAPI(title="Parakeet ASR (ONNX)")

# Global runtime state
_model: ParakeetModel | None = None
_scheduler: Scheduler | None = None
_is_ready: bool = False


@app.on_event("startup")
async def on_startup() -> None:
    global _model, _scheduler, _is_ready
    logger.info("Loading model: %s", settings.model_id)
    _model = ParakeetModel.load(settings.model_id)
    logger.info("Model loaded. Warming up...")
    _model.warmup(seconds=0.5)
    logger.info("Warmup done.")

    maxsize = settings.num_lanes * settings.queue_max_factor
    _scheduler = Scheduler(num_lanes=settings.num_lanes, maxsize=maxsize, run_fn=_model.recognize_waveform)
    _scheduler.start()
    _is_ready = True
    logger.info("Scheduler started with %d lanes (queue maxsize=%d)", settings.num_lanes, maxsize)


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


@app.post("/v1/transcribe")
async def transcribe(file: UploadFile = File(...)) -> JSONResponse:
    global _scheduler, _model
    if _scheduler is None or _model is None or not _is_ready:
        raise HTTPException(status_code=503, detail="Model not initialized")

    # Basic upload size cap
    content_length = file.size if hasattr(file, "size") else None  # Starlette may not set
    if content_length is not None:
        max_bytes = int(settings.max_upload_mb * 1024 * 1024)
        if content_length > max_bytes:
            raise HTTPException(status_code=413, detail="Upload too large")

    started_ts = time.time()
    end_to_end_timer = Timer()

    raw = await file.read()
    if content_length is None:
        max_bytes = int(settings.max_upload_mb * 1024 * 1024)
        if len(raw) > max_bytes:
            raise HTTPException(status_code=413, detail="Upload too large")

    # Preprocess
    preprocess_dt = 0.0
    inference_dt = 0.0
    queue_wait_s = 0.0
    audio_len_s = 0.0
    sr = 16000

    try:
        t = Timer()
        decoded = decode_and_resample(raw)
        preprocess_dt = t.stop()
        audio_len_s = decoded.duration_seconds
        sr = decoded.sample_rate

        if decoded.duration_seconds > settings.max_audio_seconds:
            raise HTTPException(status_code=413, detail="Audio too long")

        # Admission control — immediate 429 if full
        if _scheduler.queue.full():
            headers = {"Retry-After": str(int(settings.max_queue_wait_s))}
            raise HTTPException(status_code=429, detail="Busy, try again later", headers=headers)

        prio = bucket_priority(len(decoded.waveform), decoded.sample_rate)
        fut = _scheduler.submit(decoded.waveform, decoded.sample_rate, prio)

        # Queue TTL: if waiting too long, cancel and 503
        try:
            text, inference_dt, queue_wait_s = await asyncio.wait_for(
                fut, timeout=settings.max_queue_wait_s
            )  # type: ignore[misc]
        except asyncio.TimeoutError:
            if not fut.done():
                fut.cancel()
            raise HTTPException(status_code=503, detail="Queue wait timeout")

        total = end_to_end_timer.stop()
        log_request(RequestMetrics(
            ts=started_ts,
            model=settings.model_id,
            audio_len_s=audio_len_s,
            sample_rate=sr,
            duration_preprocess_s=preprocess_dt,
            duration_inference_s=inference_dt,
            duration_total_s=total,
            queue_wait_s=queue_wait_s,
            status="ok",
            code=200,
        ))

        return JSONResponse({
            "text": text,
            "duration": decoded.duration_seconds,
            "sample_rate": decoded.sample_rate,
            "model": settings.model_id,
        })

    except HTTPException as he:
        total = end_to_end_timer.stop()
        log_request(RequestMetrics(
            ts=started_ts,
            model=settings.model_id,
            audio_len_s=audio_len_s,
            sample_rate=sr,
            duration_preprocess_s=preprocess_dt,
            duration_inference_s=inference_dt,
            duration_total_s=total,
            queue_wait_s=queue_wait_s,
            status="error",
            code=he.status_code,
            error=str(he.detail),
        ))
        raise
    except Exception as e:  # pragma: no cover
        total = end_to_end_timer.stop()
        logger.exception("Transcription failed: %s", e)
        log_request(RequestMetrics(
            ts=started_ts,
            model=settings.model_id,
            audio_len_s=audio_len_s,
            sample_rate=sr,
            duration_preprocess_s=preprocess_dt,
            duration_inference_s=inference_dt,
            duration_total_s=total,
            queue_wait_s=queue_wait_s,
            status="error",
            code=500,
            error=str(e),
        ))
        raise HTTPException(status_code=500, detail=str(e))
