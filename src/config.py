from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARAKEET_", extra="ignore", protected_namespaces=())

    # NeMo model identifier
    # Use NVIDIA Parakeet TDT-CTC 0.6B by default
    model_id: str = os.getenv("PARAKEET_MODEL_ID", "nvidia/parakeet-tdt_ctc-1.1b")

    # Long-form inference knobs (see NVIDIA blog)
    # Enable limited context attention with 128 tokens left/right
    use_local_attention: bool = os.getenv("PARAKEET_USE_LOCAL_ATTENTION", "1") not in ("0", "false", "False")
    local_attention_context: int = int(os.getenv("PARAKEET_LOCAL_ATTENTION_CONTEXT", "128"))
    # Chunking factor for subsampling conv (1 = auto select)
    subsampling_chunking_factor: int = int(os.getenv("PARAKEET_SUBSAMPLING_CHUNKING_FACTOR", "1"))

    # Concurrency and queuing (micro-batching only)
    queue_max_factor: int = int(os.getenv("PARAKEET_QUEUE_MAX_FACTOR", "32"))
    max_queue_wait_s: float = float(os.getenv("PARAKEET_MAX_QUEUE_WAIT_S", "30"))
    
    # Duration-aware inference timeout system
    expected_xrt_min: float = float(os.getenv("PARAKEET_EXPECTED_XRT_MIN", "2.0"))
    infer_timeout_safety: float = float(os.getenv("PARAKEET_INFER_TIMEOUT_SAFETY", "1.8"))
    infer_timeout_cap_s: float = float(os.getenv("PARAKEET_INFER_TIMEOUT_CAP_S", "210"))

    # Micro-batching (server-level)
    microbatch_window_ms: float = float(os.getenv("PARAKEET_MICROBATCH_WINDOW_MS", "10"))
    microbatch_max_batch: int = int(os.getenv("PARAKEET_MICROBATCH_MAX_BATCH", "32"))

    # Admission control
    max_audio_seconds: float = float(os.getenv("PARAKEET_MAX_AUDIO_SECONDS", "600"))  # 10 minutes
    max_upload_mb: float = float(os.getenv("PARAKEET_MAX_UPLOAD_MB", "64"))

    # API
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # ASR dataloader + precision controls
    asr_batch_size: int = int(os.getenv("PARAKEET_ASR_BATCH_SIZE", "32"))
    asr_num_workers: int = int(os.getenv("PARAKEET_ASR_NUM_WORKERS", "0"))
    use_autocast: bool = os.getenv("PARAKEET_USE_AUTOCAST", "1") not in ("0", "false", "False")
    autocast_dtype: str = os.getenv("PARAKEET_AUTOCAST_DTYPE", "float16")  # float16 | bfloat16
    cudnn_benchmark: bool = os.getenv("PARAKEET_CUDNN_BENCHMARK", "1") not in ("0", "false", "False")


settings = Settings()
