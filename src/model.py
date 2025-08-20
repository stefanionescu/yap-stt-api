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
        # Allow hub id aliases from onnx-asr; this will download/cached under ~/.cache/onnx-asr
        model = onnx_asr.load_model(model_id)
        return cls(model_id=model_id, _model=model)

    def recognize_waveform(self, waveform: np.ndarray, sample_rate: int) -> str:
        # onnx-asr API prefers file path; write to a temp wav for compatibility
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            sf.write(tmp.name, waveform, sample_rate)
            text = self._model.recognize(tmp.name)
        if isinstance(text, (list, tuple)):
            # Some wrappers return list of segments or list with single string
            return " ".join(map(str, text))
        return str(text)

    def warmup(self, seconds: float = 1.0, sample_rate: int = 16000) -> None:
        samples = int(seconds * sample_rate)
        silence = np.zeros(samples, dtype=np.float32)
        # Run one dry pass to initialize providers, compile graphs, build TRT caches if applicable
        try:
            _ = self.recognize_waveform(silence, sample_rate)
        except Exception:
            # Ignore text result; goal is EP initialization
            pass
