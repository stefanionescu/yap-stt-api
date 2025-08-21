from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundfile as sf
import onnxruntime as ort

try:
    import onnx_asr
except Exception as e:  # pragma: no cover
    onnx_asr = None  # type: ignore


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
        # onnx-asr 0.7+ supports providers kwarg; pass CUDA-only preference
        model = onnx_asr.load_model(source, providers=[p if isinstance(p, str) else p[0] for p in CUDA_ONLY])
        # Best-effort provider check if accessible
        try:
            get_providers = getattr(model, "get_providers", None) or getattr(getattr(model, "asr", None), "get_providers", None)
            if callable(get_providers):
                active = get_providers()
                if require_gpu and all(x not in active for x in ("CUDAExecutionProvider", "TensorrtExecutionProvider")):
                    raise RuntimeError(f"Model session not using GPU providers: {active}")
        except Exception:
            pass
        return cls(model_id=source, _model=model)

    @classmethod
    def load_with_fallback(cls, primary_id: str, fallback_id: Optional[str] = None, *, model_dir: str = "", require_gpu: bool = True) -> "ParakeetModel":
        if onnx_asr is None:
            raise RuntimeError("onnx-asr is not installed; please install dependencies.")
        # Prefer an explicit local model directory (e.g., INT8 files)
        if model_dir:
            return cls._load_internal(model_dir, require_gpu)
        # Try primary alias first
        try:
            return cls._load_internal(primary_id, require_gpu)
        except Exception:
            if fallback_id and fallback_id != primary_id:
                return cls._load_internal(fallback_id, require_gpu)
            raise

    def recognize_waveform(self, waveform: np.ndarray, sample_rate: int) -> str:
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
