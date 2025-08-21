from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARAKEET_", extra="ignore", protected_namespaces=())

    # Model identifiers (onnx-asr hub supports aliases)
    model_id: str = os.getenv("PARAKEET_MODEL_ID", "nemo-parakeet-tdt-0.6b-v2")
    fallback_model_id: str = os.getenv("PARAKEET_FALLBACK_MODEL_ID", "istupakov/parakeet-tdt-0.6b-v2-onnx")
    model_dir: str = os.getenv("PARAKEET_MODEL_DIR", "")  # Prefer local INT8 folder if set

    # Enforce GPU
    require_gpu: bool = os.getenv("PARAKEET_REQUIRE_GPU", "1") not in ("0", "false", "False")

    # Concurrency and queuing
    num_lanes: int = int(os.getenv("PARAKEET_NUM_LANES", "2"))
    queue_max_factor: int = int(os.getenv("PARAKEET_QUEUE_MAX_FACTOR", "2"))
    max_queue_wait_s: float = float(os.getenv("PARAKEET_MAX_QUEUE_WAIT_S", "30"))

    # Admission control
    max_audio_seconds: float = float(os.getenv("PARAKEET_MAX_AUDIO_SECONDS", "600"))  # 10 minutes
    max_upload_mb: float = float(os.getenv("PARAKEET_MAX_UPLOAD_MB", "64"))

    # ORT / TRT caches (effective on Linux with TRT-EP build)
    trt_engine_cache: str = os.getenv("TRT_ENGINE_CACHE", "/models/trt_cache")
    trt_timing_cache: str = os.getenv("TRT_TIMING_CACHE", "/models/timing.cache")

    # API
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))


settings = Settings()
