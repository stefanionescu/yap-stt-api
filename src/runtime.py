from __future__ import annotations

import logging
import os
from typing import Any, List
import ctypes

import onnxruntime as ort

logger = logging.getLogger("parakeet.runtime")


def _trt_runtime_ok() -> bool:
    try:
        ctypes.CDLL("libnvinfer.so.10")
        ctypes.CDLL("libnvinfer_plugin.so.10")
        return True
    except OSError:
        return False


def pick_providers(
    *,
    device_id: int = 0,
    use_tensorrt: bool = True,
    trt_engine_cache: str = "/models/trt_cache",
    trt_timing_cache: str = "/models/timing.cache",
    trt_max_workspace_size: int = 8 * 1024**3,
) -> List[Any]:
    avail = set(ort.get_available_providers())
    providers: List[Any] = []

    want_trt = bool(use_tensorrt) and ("TensorrtExecutionProvider" in avail) and _trt_runtime_ok()
    if want_trt:
        providers.append(
            (
                "TensorrtExecutionProvider",
                {
                    "device_id": device_id,
                    "trt_engine_cache_enable": True,
                    "trt_engine_cache_path": trt_engine_cache,
                    "trt_timing_cache_enable": True,
                    "trt_timing_cache_path": trt_timing_cache,
                    "trt_max_workspace_size": trt_max_workspace_size,
                    # Prefer fastest precision available in engine if model allows
                    "trt_int8_enable": True,
                    "trt_fp16_enable": True,
                },
            )
        )

    if "CUDAExecutionProvider" in avail:
        providers.append(("CUDAExecutionProvider", {"device_id": device_id}))

    providers.append("CPUExecutionProvider")
    return providers


def make_session_options(*, intra_op_num_threads: int = 1) -> ort.SessionOptions:
    so = ort.SessionOptions()
    so.intra_op_num_threads = max(1, int(intra_op_num_threads))
    return so


def create_session(
    model_path: str,
    *,
    providers: List[Any],
    intra_op_num_threads: int = 1,
) -> ort.InferenceSession:
    sess = ort.InferenceSession(
        model_path,
        sess_options=make_session_options(intra_op_num_threads=intra_op_num_threads),
        providers=providers,
    )
    return sess


def log_session_providers(name: str, sess: ort.InferenceSession) -> None:
    try:
        logger.info("%s providers: %s", name, sess.get_providers())
    except Exception:
        pass


