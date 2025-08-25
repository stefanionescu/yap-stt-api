from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARAKEET_", extra="ignore", protected_namespaces=())

    # NeMo model identifier
    # Use NVIDIA Parakeet TDT-CTC 0.6B by default
    model_id: str = os.getenv("PARAKEET_MODEL_ID", "nvidia/parakeet-tdt-0.6b-v2")

    # Long-form inference knobs (see NVIDIA blog)
    # Enable limited context attention with 128 tokens left/right
    use_local_attention: bool = os.getenv("PARAKEET_USE_LOCAL_ATTENTION", "1") not in ("0", "false", "False")
    local_attention_context: int = int(os.getenv("PARAKEET_LOCAL_ATTENTION_CONTEXT", "128"))
    # Chunking factor for subsampling conv (1 = auto select)
    subsampling_chunking_factor: int = int(os.getenv("PARAKEET_SUBSAMPLING_CHUNKING_FACTOR", "1"))

    # Concurrency and queuing (micro-batching only)
    queue_max_factor: int = int(os.getenv("PARAKEET_QUEUE_MAX_FACTOR", "128"))
    max_queue_wait_s: float = float(os.getenv("PARAKEET_MAX_QUEUE_WAIT_S", "30"))
    
    # Duration-aware inference timeout system
    expected_xrt_min: float = float(os.getenv("PARAKEET_EXPECTED_XRT_MIN", "1.3"))
    infer_timeout_safety: float = float(os.getenv("PARAKEET_INFER_TIMEOUT_SAFETY", "1.8"))
    infer_timeout_cap_s: float = float(os.getenv("PARAKEET_INFER_TIMEOUT_CAP_S", "210"))

    # Micro-batching (server-level)
    microbatch_window_ms: float = float(os.getenv("PARAKEET_MICROBATCH_WINDOW_MS", "8"))
    microbatch_max_batch: int = int(os.getenv("PARAKEET_MICROBATCH_MAX_BATCH", "32"))

    # Finals timeout (single-lane priority scheduler, no separate finals lane)
    finals_timeout_s: float = float(os.getenv("PARAKEET_FINALS_TIMEOUT_S", "20"))

    # Admission control
    max_audio_seconds: float = float(os.getenv("PARAKEET_MAX_AUDIO_SECONDS", "600"))  # 10 minutes
    max_upload_mb: float = float(os.getenv("PARAKEET_MAX_UPLOAD_MB", "64"))

    # gRPC API
    grpc_host: str = os.getenv("HOST", "0.0.0.0")
    grpc_port: int = int(os.getenv("PORT", "8000"))
    grpc_use_tls: bool = os.getenv("PARAKEET_GRPC_TLS", "0") not in ("0", "false", "False")
    grpc_cert_path: str | None = os.getenv("PARAKEET_GRPC_CERT", None)
    grpc_key_path: str | None = os.getenv("PARAKEET_GRPC_KEY", None)

    # Streaming cadence and context window
    stream_step_ms: float = float(os.getenv("PARAKEET_STREAM_STEP_MS", "240"))
    stream_context_seconds: float = float(os.getenv("PARAKEET_STREAM_CONTEXT_SECONDS", "4"))

    # Streaming backpressure and decimation
    stream_decimation_min_interval_ms: float = float(os.getenv("PARAKEET_STREAM_DECIMATION_MIN_INTERVAL_MS", "300"))
    stream_decimation_when_hot: bool = os.getenv("PARAKEET_STREAM_DECIMATION_WHEN_HOT", "1") not in ("0", "false", "False")
    stream_hot_queue_fraction: float = float(os.getenv("PARAKEET_STREAM_HOT_QUEUE_FRACTION", "0.5"))  # 0..1

    # Per-tick inference timeout cap (seconds)
    stream_tick_timeout_s: float = float(os.getenv("PARAKEET_STREAM_TICK_TIMEOUT_S", "1.0"))

    # Simple VAD gating for partial ticks and eager finalize
    vad_enable: bool = os.getenv("PARAKEET_VAD_ENABLE", "0") not in ("0", "false", "False")
    vad_tail_ms: float = float(os.getenv("PARAKEET_VAD_TAIL_MS", "300"))
    vad_energy_threshold: float = float(os.getenv("PARAKEET_VAD_ENERGY_THRESHOLD", "0.001"))
    eager_sil_ms: float = float(os.getenv("PARAKEET_EAGER_SIL_MS", "500"))

    # ASR dataloader + precision controls
    asr_batch_size: int = int(os.getenv("PARAKEET_ASR_BATCH_SIZE", "32"))
    asr_num_workers: int = int(os.getenv("PARAKEET_ASR_NUM_WORKERS", "0"))
    use_autocast: bool = os.getenv("PARAKEET_USE_AUTOCAST", "1") not in ("0", "false", "False")
    autocast_dtype: str = os.getenv("PARAKEET_AUTOCAST_DTYPE", "float16")  # float16 | bfloat16
    cudnn_benchmark: bool = os.getenv("PARAKEET_CUDNN_BENCHMARK", "1") not in ("0", "false", "False")


settings = Settings()
