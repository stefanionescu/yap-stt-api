from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import List

import numpy as np
import soundfile as sf
import logging
import torch

import nemo.collections.asr as nemo_asr

from .config import settings

logger = logging.getLogger("parakeet.model")


@dataclass
class ParakeetModel:
    model_id: str
    _model: nemo_asr.models.ASRModel

    @classmethod
    def load(cls) -> "ParakeetModel":
        logger.info("Loading NeMo ASR model: %s", settings.model_id)
        asr_model = nemo_asr.models.ASRModel.from_pretrained(model_name=settings.model_id)
        # Enable local attention and chunking for long-form inference if configured
        if settings.use_local_attention:
            try:
                asr_model.change_attention_model("rel_pos_local_attn", [settings.local_attention_context, settings.local_attention_context])
                asr_model.change_subsampling_conv_chunking_factor(settings.subsampling_chunking_factor)
                logger.info(
                    "Configured local attention with context=%d and chunking_factor=%d",
                    settings.local_attention_context,
                    settings.subsampling_chunking_factor,
                )
            except Exception as e:
                logger.warning("Failed to configure local attention/chunking: %s", e)

        # Prefer GPU when available
        try:
            if torch.cuda.is_available():
                asr_model = asr_model.to(torch.device("cuda"))  # type: ignore[assignment]
                logger.info("ASR model moved to CUDA")
        except Exception as e:
            logger.warning("Could not move model to CUDA: %s", e)

        try:
            asr_model.eval()
            for p in asr_model.parameters():
                p.requires_grad_(False)
        except Exception:
            pass

        return cls(model_id=settings.model_id, _model=asr_model)

    def _transcribe_paths(self, paths: List[str]) -> List[str]:
        try:
            texts = self._model.transcribe(paths)
        except TypeError:
            # Some NeMo versions use keyword paths2audio_files
            texts = self._model.transcribe(paths2audio_files=paths)  # type: ignore[call-arg]
        # Ensure list[str]
        return [str(t) for t in texts]

    def recognize_waveform(self, waveform: np.ndarray, sample_rate: int) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            sf.write(tmp.name, waveform, sample_rate)
            out = self._transcribe_paths([tmp.name])[0]
        return out

    def recognize_waveforms(self, waveforms: List[np.ndarray], sample_rates: List[int]) -> List[str]:
        tmp_files: List[tempfile.NamedTemporaryFile] = []
        paths: List[str] = []
        try:
            for wav, sr in zip(waveforms, sample_rates):
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                sf.write(tmp.name, wav, sr)
                tmp_files.append(tmp)
                paths.append(tmp.name)
            return self._transcribe_paths(paths)
        finally:
            for tmp in tmp_files:
                try:
                    tmp.close()
                except Exception:
                    pass

    def warmup(self, seconds: float = 1.0, sample_rate: int = 16000) -> None:
        samples = int(seconds * sample_rate) or sample_rate // 2
        silence = np.zeros(samples, dtype=np.float32)
        try:
            _ = self.recognize_waveform(silence, sample_rate)
        except Exception:
            pass
