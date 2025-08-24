from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARAKEET_", extra="ignore", protected_namespaces=())

    # Model identifiers (onnx-asr hub supports aliases)
    # Logical model name (used by onnx-asr when loading from local dir)
    model_name: str = os.getenv("PARAKEET_MODEL_NAME", "nemo-parakeet-tdt-0.6b-v2")
    model_id: str = os.getenv("PARAKEET_MODEL_ID", "nemo-parakeet-tdt-0.6b-v2")
    fallback_model_id: str = os.getenv("PARAKEET_FALLBACK_MODEL_ID", "istupakov/parakeet-tdt-0.6b-v2-onnx")

    # Optional local model directory (preferred when provided). Directory must contain
    # encoder-model.onnx (and encoder-model.onnx.data for FP32), decoder_joint-model.onnx,
    # vocab.txt, and config.json
    model_dir: str | None = os.getenv("PARAKEET_MODEL_DIR")

    # Enforce GPU
    require_gpu: bool = os.getenv("PARAKEET_REQUIRE_GPU", "1") not in ("0", "false", "False")

    device_id: int = int(os.getenv("PARAKEET_DEVICE_ID", "0"))
    # Allow either PARAKEET_USE_TENSORRT (preferred) or PARAKEET_USE_TRT
    use_tensorrt: bool = os.getenv("PARAKEET_USE_TENSORRT", os.getenv("PARAKEET_USE_TRT", "1")) not in ("0", "false", "False")
    ort_intra_op_num_threads: int = int(os.getenv("ORT_INTRA_OP_NUM_THREADS", "1"))

    # Concurrency and queuing (micro-batching only)
    queue_max_factor: int = int(os.getenv("PARAKEET_QUEUE_MAX_FACTOR", "2"))
    max_queue_wait_s: float = float(os.getenv("PARAKEET_MAX_QUEUE_WAIT_S", "30"))

    # Micro-batching (server-level)
    microbatch_window_ms: float = float(os.getenv("PARAKEET_MICROBATCH_WINDOW_MS", "10"))
    microbatch_max_batch: int = int(os.getenv("PARAKEET_MICROBATCH_MAX_BATCH", "8"))

    # Admission control
    max_audio_seconds: float = float(os.getenv("PARAKEET_MAX_AUDIO_SECONDS", "600"))  # 10 minutes
    max_upload_mb: float = float(os.getenv("PARAKEET_MAX_UPLOAD_MB", "64"))

    # ORT / TRT caches (effective on Linux with TRT-EP build)
    trt_engine_cache: str = os.getenv("TRT_ENGINE_CACHE", "/models/trt_cache")
    trt_timing_cache: str = os.getenv("TRT_TIMING_CACHE", "/models/timing.cache")
    trt_max_workspace_size: int = int(os.getenv("TRT_MAX_WORKSPACE_SIZE", str(8 * 1024**3)))

    # API
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))


settings = Settings()
