from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundfile as sf

try:
    import onnx_asr
except Exception as e:  # pragma: no cover
    onnx_asr = None  # type: ignore


@dataclass
class ParakeetModel:
    model_id: str
    _model: object

    @classmethod
    def load(cls, model_id: str) -> "ParakeetModel":
        if onnx_asr is None:
            raise RuntimeError("onnx-asr is not installed; please install dependencies.")
        model = onnx_asr.load_model(model_id)
        return cls(model_id=model_id, _model=model)

    @classmethod
    def load_with_fallback(cls, primary_id: str, fallback_id: Optional[str] = None) -> "ParakeetModel":
        if onnx_asr is None:
            raise RuntimeError("onnx-asr is not installed; please install dependencies.")
        # Try primary first
        try:
            return cls(model_id=primary_id, _model=onnx_asr.load_model(primary_id))
        except Exception:
            # Try fallback if provided and different
            if fallback_id and fallback_id != primary_id:
                try:
                    return cls(model_id=fallback_id, _model=onnx_asr.load_model(fallback_id))
                except Exception as e2:
                    raise RuntimeError(f"Failed to load models: primary='{primary_id}', fallback='{fallback_id}': {e2}")
            raise

    def recognize_waveform(self, waveform: np.ndarray, sample_rate: int) -> str:
        # onnx-asr API prefers file path; write to a temp wav for compatibility
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
