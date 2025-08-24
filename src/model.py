from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import List, Any

import numpy as np
import soundfile as sf
import logging
import torch

import nemo.collections.asr as nemo_asr
import nemo.collections.nlp as nemo_nlp

from .config import settings

logger = logging.getLogger("parakeet.model")


@dataclass
class ParakeetModel:
    model_id: str
    _model: nemo_asr.models.ASRModel
    _punct_model: object | None = None

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

        # Prefer greedy_batch decoding for CTC (same output, faster than greedy)
        try:
            # Primary API
            if hasattr(asr_model, "change_decoding_strategy"):
                asr_model.change_decoding_strategy(decoding_cfg={"strategy": "greedy_batch"})  # type: ignore[arg-type]
                logger.info("CTC decoding strategy set to greedy_batch")
            else:
                # Fallback: try to tweak cfg and refresh
                cfg = getattr(asr_model, "cfg", None) or getattr(asr_model, "_cfg", None)
                if cfg is not None and getattr(cfg, "decoding", None) is not None:
                    cfg.decoding.strategy = "greedy_batch"  # type: ignore[attr-defined]
                    if hasattr(asr_model, "change_decoding_strategy"):
                        asr_model.change_decoding_strategy(cfg.decoding)  # type: ignore[arg-type]
                    logger.info("CTC decoding strategy set to greedy_batch via cfg")
        except Exception as e:
            logger.warning("Could not set decoding strategy to greedy_batch: %s", e)

        # Prefer GPU when available
        try:
            if torch.cuda.is_available():
                asr_model = asr_model.to(torch.device("cuda"))  # type: ignore[assignment]
                # Enable TF32 for faster matmul on Ampere+ GPUs
                try:
                    torch.backends.cuda.matmul.allow_tf32 = True  # type: ignore[attr-defined]
                    if hasattr(torch, "set_float32_matmul_precision"):
                        torch.set_float32_matmul_precision("high")  # type: ignore[attr-defined]
                    if settings.cudnn_benchmark and hasattr(torch.backends, "cudnn"):
                        torch.backends.cudnn.benchmark = True  # type: ignore[attr-defined]
                except Exception:
                    pass
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
    
    def _maybe_load_punct_model(self) -> None:
        if not settings.enable_punct_capit:
            return
        if self._punct_model is not None:
            return
        try:
            logger.info("Loading NeMo punctuation/capitalization model: %s", settings.punct_capit_model_id)
            self._punct_model = nemo_nlp.models.PunctuationCapitalizationModel.from_pretrained(
                model_name=settings.punct_capit_model_id
            )
            try:
                if torch.cuda.is_available():
                    self._punct_model = self._punct_model.to(torch.device("cuda"))  # type: ignore[assignment]
            except Exception:
                pass
        except Exception as e:
            logger.warning("Failed to load punctuation/capitalization model: %s", e)

    def _extract_text(self, item: Any) -> str:
        # Handle NeMo Hypothesis objects, dicts, or plain strings
        try:
            if hasattr(item, "text"):
                return str(getattr(item, "text"))
            if isinstance(item, dict) and "text" in item:
                return str(item.get("text", ""))
            return str(item)
        except Exception:
            return str(item)

    def _normalize_outputs(self, outputs: Any) -> List[str]:
        # NeMo may return list[str], list[Hypothesis], or list[list[Hypothesis]]
        texts: List[str] = []
        for out in outputs:
            cand = out
            if isinstance(out, (list, tuple)) and len(out) > 0:
                cand = out[0]
            texts.append(self._extract_text(cand))
        # Optional punctuation + capitalization
        if settings.enable_punct_capit:
            self._maybe_load_punct_model()
            if self._punct_model is not None and texts:
                try:
                    with torch.inference_mode():
                        puncted = self._punct_model.add_punctuation_capitalization(texts)  # type: ignore[attr-defined]
                    # Model returns list[{'punct_pred': text, ...}] or list[str] depending on version
                    processed: List[str] = []
                    for p in puncted:
                        if isinstance(p, dict) and "punct_pred" in p:
                            processed.append(str(p["punct_pred"]))
                        else:
                            processed.append(str(p))
                    return processed
                except Exception as e:
                    logger.warning("Punctuation/capitalization failed: %s", e)
        return texts

    def _transcribe_paths(self, paths: List[str]) -> List[str]:
        autocast_dtype = torch.float16 if settings.autocast_dtype.lower() == "float16" else (
            torch.bfloat16 if settings.autocast_dtype.lower() == "bfloat16" else torch.float16
        )
        with torch.inference_mode():
            try:
                # Prefer batched transcription without progress bar; keep workers=0 to reduce overhead
                if settings.use_autocast and torch.cuda.is_available():
                    with torch.autocast(device_type="cuda", dtype=autocast_dtype):
                        outputs = self._model.transcribe(
                            paths,
                            batch_size=min(len(paths), settings.asr_batch_size),
                            num_workers=settings.asr_num_workers,
                            verbose=False,
                        )
                else:
                    outputs = self._model.transcribe(
                        paths,
                        batch_size=min(len(paths), settings.asr_batch_size),
                        num_workers=settings.asr_num_workers,
                        verbose=False,
                    )
            except TypeError:
                # Some NeMo versions use keyword paths2audio_files
                try:
                    if settings.use_autocast and torch.cuda.is_available():
                        with torch.autocast(device_type="cuda", dtype=autocast_dtype):
                            outputs = self._model.transcribe(paths2audio_files=paths, batch_size=min(len(paths), settings.asr_batch_size), num_workers=settings.asr_num_workers, verbose=False)  # type: ignore[call-arg]
                    else:
                        outputs = self._model.transcribe(paths2audio_files=paths, batch_size=min(len(paths), settings.asr_batch_size), num_workers=settings.asr_num_workers, verbose=False)  # type: ignore[call-arg]
                except TypeError:
                    outputs = self._model.transcribe(paths2audio_files=paths)  # type: ignore[call-arg]
        return self._normalize_outputs(outputs)

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
