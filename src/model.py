from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundfile as sf
import onnxruntime as ort
import logging

from .config import settings
from .runtime import pick_providers

try:
    import onnx_asr
except Exception as e:  # pragma: no cover
    onnx_asr = None  # type: ignore

logger = logging.getLogger("parakeet.model")

CUDA_ONLY = [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]

@dataclass
class ParakeetModel:
    model_id: str
    _model: object

    @staticmethod
    def _ensure_gpu_active(require_gpu: bool) -> None:
        providers = ort.get_available_providers()
        if require_gpu and "CUDAExecutionProvider" not in providers and "TensorrtExecutionProvider" not in providers:
            raise RuntimeError(
                f"GPU provider not available. Available providers: {providers}. Ensure CUDA/cuDNN (and TensorRT if desired) are installed."
            )

    @classmethod
    def _load_internal(cls, source: str, require_gpu: bool) -> "ParakeetModel":
        cls._ensure_gpu_active(require_gpu)
        # Build providers list (names only for onnx-asr)
        prov_list = pick_providers(
            device_id=settings.device_id,
            use_tensorrt=settings.use_tensorrt,
            trt_engine_cache=settings.trt_engine_cache,
            trt_timing_cache=settings.trt_timing_cache,
            trt_max_workspace_size=settings.trt_max_workspace_size,
        )
        prov_names_only = [p if isinstance(p, str) else p[0] for p in prov_list]

        # If source is a directory, load local with model_name and onnx_dir
        if os.path.isdir(source):
            local_dir = source
            enc = os.path.join(local_dir, "encoder-model.onnx")
            dec = os.path.join(local_dir, "decoder_joint-model.onnx")
            if not (os.path.isfile(enc) and os.path.isfile(dec)):
                raise RuntimeError(
                    "Model dir missing encoder-model.onnx and/or decoder_joint-model.onnx. "
                    "If you have INT8 files named *.int8.onnx, rename them accordingly."
                )
            ext_data = [p for p in os.listdir(local_dir) if p.endswith(".onnx.data")]
            if ext_data:
                logger.warning("Found external-data files in model dir (possible FP32): %s", ext_data)
            # onnx-asr: pass model name and local dir
            model = onnx_asr.load_model(settings.model_name, onnx_dir=local_dir, providers=prov_names_only)
        else:
            # Remote/hub path
            model = onnx_asr.load_model(source, providers=prov_names_only)
        # Best-effort provider check if accessible
        try:
            get_providers = getattr(model, "get_providers", None) or getattr(getattr(model, "asr", None), "get_providers", None)
            if callable(get_providers):
                active = get_providers()
                if require_gpu and all(x not in active for x in ("CUDAExecutionProvider", "TensorrtExecutionProvider")):
                    raise RuntimeError(f"Model session not using GPU providers: {active}")
                logger.info("Active model providers: %s", active)
        except Exception:
            pass
        return cls(model_id=source, _model=model)

    @classmethod
    def load_with_fallback(
        cls,
        primary_id: str,
        fallback_id: Optional[str] = None,
        *,
        require_gpu: bool = True,
    ) -> "ParakeetModel":
        if onnx_asr is None:
            raise RuntimeError("onnx-asr is not installed; please install dependencies.")

        # Try primary alias
        try:
            logger.info("Attempting to load model by id: %s", primary_id)
            return cls._load_internal(primary_id, require_gpu)
        except Exception as e_primary:
            logger.warning("Primary id load failed (%s).", e_primary)

        # Try fallback repo id
        if fallback_id and fallback_id != primary_id:
            logger.info("Attempting to load fallback id: %s", fallback_id)
            return cls._load_internal(fallback_id, require_gpu)

        # If everything fails, raise the original error
        raise RuntimeError(f"Failed to load model by id. Primary='{primary_id}', fallback='{fallback_id}'.")

    def recognize_waveform(self, waveform: np.ndarray, sample_rate: int) -> str:
        # Prefer direct waveform APIs if available to avoid temp file I/O
        try:
            if hasattr(self._model, "recognize_waveform"):
                text = self._model.recognize_waveform(waveform, sample_rate)  # type: ignore[attr-defined]
            else:
                text = self._model.recognize(waveform, sample_rate)  # type: ignore[misc]
        except TypeError:
            # Fallback to file path API
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                sf.write(tmp.name, waveform, sample_rate)
                text = self._model.recognize(tmp.name)
        if isinstance(text, (list, tuple)):
            return " ".join(map(str, text))
        return str(text)

    def warmup(self, seconds: float = 1.0, sample_rate: int = 16000) -> None:
        samples = int(seconds * sample_rate)
        if samples <= 0:
            samples = sample_rate // 2
        silence = np.zeros(samples, dtype=np.float32)
        try:
            _ = self.recognize_waveform(silence, sample_rate)
        except Exception:
            pass
