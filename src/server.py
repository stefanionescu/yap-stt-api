from __future__ import annotations

import asyncio
import logging
import importlib
import importlib.util

import numpy as np

from .config import settings
from .logging_config import configure_logging
from .model import ParakeetModel
from .scheduler import MicroBatchScheduler
from .riva_server import start_riva_grpc_server


logger = logging.getLogger("parakeet.server")
configure_logging()


async def main() -> None:
    # CUDA diagnostics: detect cuda-python availability and driver load
    try:
        cuda_spec = importlib.util.find_spec("cuda")
        cudart_spec = importlib.util.find_spec("cuda.cudart")
        if cuda_spec and not cudart_spec:
            logger.warning(
                "Found 'cuda' top-level module but no 'cuda.cudart'. A conflicting 'cuda' package may be installed."
            )
        cuda_mod = importlib.import_module("cuda")
        # Try driver API first; this only requires libcuda (no full toolkit)
        try:
            cu = importlib.import_module("cuda.cuda")
            try:
                cu.cuInit(0)
                _err, ndev_drv = cu.cuDeviceGetCount()
                logger.info("cuda-python driver API ok; devices=%s", ndev_drv)
            except Exception as e:
                logger.warning("cuda driver API present but failed to query devices: %s", e)
        except Exception:
            pass
        # Then try runtime API (requires libcudart from CUDA toolkit)
        try:
            cudart = importlib.import_module("cuda.cudart")
            try:
                _err, ndev = cudart.cudaGetDeviceCount()
                num_devices = ndev
            except Exception:
                num_devices = -1
            logger.info("cuda-python runtime API ok; cuda.cudart devices=%s", num_devices)
        except Exception:
            logger.info("cuda runtime API (cudart) not available; likely no CUDA toolkit in the container")
    except Exception as e:
        logger.warning("cuda-python import failed (no CUDA graphs optimizations): %s", e)

    model = ParakeetModel.load()
    logger.info("Model loaded: %s", model.model_id)

    maxsize = settings.queue_max_factor * settings.microbatch_max_batch

    def run_batch_fn(wavs: list[np.ndarray], srs: list[int]) -> list[str]:
        return model.recognize_waveforms(wavs, srs)

    # Partials scheduler (normal lane)
    scheduler_partials = MicroBatchScheduler(
        maxsize=maxsize,
        run_batch_fn=run_batch_fn,
        window_ms=settings.microbatch_window_ms,
        max_batch=settings.microbatch_max_batch,
    )
    scheduler_partials.start()
    logger.info(
        "Partials MicroBatchScheduler started (window_ms=%s, max_batch=%s, queue maxsize=%d)",
        settings.microbatch_window_ms,
        settings.microbatch_max_batch,
        maxsize,
    )

    # Finals fast-lane scheduler
    finals_maxsize = settings.finals_queue_max_factor * settings.microbatch_max_batch
    scheduler_finals = MicroBatchScheduler(
        maxsize=finals_maxsize,
        run_batch_fn=run_batch_fn,
        window_ms=settings.microbatch_finals_window_ms,
        max_batch=settings.microbatch_max_batch,
    )
    scheduler_finals.start()
    logger.info(
        "Finals MicroBatchScheduler started (window_ms=%s, max_batch=%s, queue maxsize=%d)",
        settings.microbatch_finals_window_ms,
        settings.microbatch_max_batch,
        finals_maxsize,
    )

    # Start gRPC server (secure optional)
    grpc_server = await start_riva_grpc_server(
        model,
        scheduler_partials,
        scheduler_finals,
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
        await scheduler_partials.stop()
        await scheduler_finals.stop()


if __name__ == "__main__":
    asyncio.run(main())
