from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import List, Any

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
        desired_model_id = settings.model_id
        # Force RNNT Parakeet-TDT if a CTC model id is provided (accuracy over CTC)
        if "ctc" in desired_model_id.lower():
            desired_model_id = "nvidia/parakeet-tdt-0.6b-v2"
            logger.warning("CTC model id detected; overriding to RNNT: %s", desired_model_id)
        logger.info("Loading NeMo ASR model: %s", desired_model_id)
        asr_model = nemo_asr.models.ASRModel.from_pretrained(model_name=desired_model_id)
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

        # Prefer greedy_batch only for CTC models; RNNT uses its own decoding configs
        try:
            cls_name = asr_model.__class__.__name__
            if "CTC" in cls_name and hasattr(asr_model, "change_decoding_strategy"):
                asr_model.change_decoding_strategy(decoding_cfg={"strategy": "greedy_batch"})  # type: ignore[arg-type]
                logger.info("CTC decoding strategy set to greedy_batch")
        except Exception as e:
            logger.warning("Could not adjust decoding strategy: %s", e)

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

        return cls(model_id=desired_model_id, _model=asr_model)
    
    def _maybe_load_punct_model(self) -> None:
        return

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
        return texts

    def _extract_words(self, hyp: Any) -> List[dict]:
        words: List[dict] = []
        try:
            # Common RNNT/Nemo structures
            if hasattr(hyp, "words") and isinstance(getattr(hyp, "words"), (list, tuple)):
                for w in getattr(hyp, "words"):
                    wdict = getattr(w, "__dict__", None) or {}
                    word = wdict.get("word") or getattr(w, "word", None)
                    start = wdict.get("start_time") or getattr(w, "start_time", None)
                    end = wdict.get("end_time") or getattr(w, "end_time", None)
                    if word is not None and start is not None and end is not None:
                        words.append({"word": str(word), "start": float(start), "end": float(end)})
            elif hasattr(hyp, "word_timestamps") and isinstance(getattr(hyp, "word_timestamps"), (list, tuple)):
                for w in getattr(hyp, "word_timestamps"):
                    wdict = getattr(w, "__dict__", None) or {}
                    word = wdict.get("word") or getattr(w, "word", None)
                    start = wdict.get("start_time") or getattr(w, "start_time", None)
                    end = wdict.get("end_time") or getattr(w, "end_time", None)
                    if word is not None and start is not None and end is not None:
                        words.append({"word": str(word), "start": float(start), "end": float(end)})
        except Exception:
            pass
        return words

    def _transcribe_paths_with_timestamps(self, paths: List[str]) -> List[dict]:
        # Best-effort enable timestamps on RNNT
        try:
            if hasattr(self._model, "change_decoding_strategy"):
                self._model.change_decoding_strategy(decoding_cfg={"compute_timestamps": True})  # type: ignore[arg-type]
        except Exception:
            pass

        autocast_dtype = torch.float16 if settings.autocast_dtype.lower() == "float16" else (
            torch.bfloat16 if settings.autocast_dtype.lower() == "bfloat16" else torch.float16
        )
        with torch.inference_mode():
            try:
                if settings.use_autocast and torch.cuda.is_available():
                    with torch.autocast(device_type="cuda", dtype=autocast_dtype):
                        outs = self._model.transcribe(paths, return_hypotheses=True, batch_size=min(len(paths), settings.asr_batch_size), num_workers=settings.asr_num_workers, verbose=False)  # type: ignore[call-arg]
                else:
                    outs = self._model.transcribe(paths, return_hypotheses=True, batch_size=min(len(paths), settings.asr_batch_size), num_workers=settings.asr_num_workers, verbose=False)  # type: ignore[call-arg]
            except TypeError:
                outs = self._model.transcribe(paths)  # type: ignore[call-arg]

        results: List[dict] = []
        for out in outs:
            hyp = out[0] if isinstance(out, (list, tuple)) and len(out) > 0 else out
            text = self._extract_text(hyp)
            words = self._extract_words(hyp)
            results.append({"text": text, "words": words})

        # Restore default decoding if possible (no timestamps)
        try:
            if hasattr(self._model, "change_decoding_strategy"):
                self._model.change_decoding_strategy(decoding_cfg={})  # type: ignore[arg-type]
        except Exception:
            pass

        return results

    def recognize_waveform_with_timestamps(self, waveform: np.ndarray, sample_rate: int) -> dict:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            sf.write(tmp.name, waveform, sample_rate)
            out = self._transcribe_paths_with_timestamps([tmp.name])[0]
        return out

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
