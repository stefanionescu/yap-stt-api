from __future__ import annotations

import asyncio
import logging

import numpy as np

from .config import settings
from .logging_config import configure_logging
from .model import ParakeetModel
from .scheduler import MicroBatchScheduler
from .riva_server import start_riva_grpc_server


logger = logging.getLogger("parakeet.server")
configure_logging()


async def main() -> None:
    model = ParakeetModel.load()
    logger.info("Model loaded: %s", model.model_id)

    maxsize = settings.queue_max_factor * settings.microbatch_max_batch

    def run_batch_fn(wavs: list[np.ndarray], srs: list[int]) -> list[str]:
        return model.recognize_waveforms(wavs, srs)

    scheduler = MicroBatchScheduler(
        maxsize=maxsize,
        run_batch_fn=run_batch_fn,
        window_ms=settings.microbatch_window_ms,
        max_batch=settings.microbatch_max_batch,
    )
    scheduler.start()
    logger.info(
        "MicroBatchScheduler started (window_ms=%s, max_batch=%s, queue maxsize=%d)",
        settings.microbatch_window_ms,
        settings.microbatch_max_batch,
        maxsize,
    )

    # Start gRPC server (secure optional)
    grpc_server = await start_riva_grpc_server(
        model,
        scheduler,
        port=settings.grpc_port,
        secure=bool(settings.grpc_use_tls),
        cert=settings.grpc_cert_path,
        key=settings.grpc_key_path,
        step_ms=settings.stream_step_ms,
        max_ctx_seconds=settings.stream_context_seconds,
    )

    try:
        await grpc_server.wait_for_termination()
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
