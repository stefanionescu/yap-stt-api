## Parakeet on GPU — Riva-compatible gRPC ASR (Pipecat-ready)

This service runs NVIDIA Parakeet (NeMo) and exposes a Riva-compatible gRPC interface for streaming and single-shot ASR. It plugs directly into Pipecat’s `RivaSTTService` without NVIDIA cloud.

- RPCs:
  - `StreamingRecognize(stream StreamingRecognizeRequest) returns (stream StreamingRecognizeResponse)`
  - `Recognize(RecognizeRequest) returns (RecognizeResponse)`
- Audio: PCM16 mono 16 kHz
- Partials: emitted with `is_final=false`; final result with `is_final=true`

GPU is strongly recommended. NeMo downloads model checkpoints automatically on first run.

### Quickstart

```bash
source scripts/env.sh
bash scripts/start_bg.sh && bash scripts/tail_bg_logs.sh

# Warmup (realtime streaming)
source .venv/bin/activate 2>/dev/null || true
python3 test/warmup.py --server localhost:8000 --file long.mp3 --chunk-ms 50
```

Defaults: `PARAKEET_MODEL_ID=nvidia/parakeet-tdt_ctc-1.1b`, streaming step `320ms`, context `10s`.

### Configuration

Key environment variables (see `scripts/env.sh`):

- `PARAKEET_MODEL_ID` (default: `nvidia/parakeet-tdt_ctc-1.1b`)
- `PARAKEET_MICROBATCH_WINDOW_MS` (default: 8)
- `PARAKEET_MICROBATCH_MAX_BATCH` (default: 32)
- `PARAKEET_STREAM_STEP_MS` (default: 320)
- `PARAKEET_STREAM_CONTEXT_SECONDS` (default: 10)
- `PORT` (gRPC port, default: 8000)
- TLS (optional): `PARAKEET_GRPC_TLS`, `PARAKEET_GRPC_CERT`, `PARAKEET_GRPC_KEY`

### Pipecat integration

- Local/dev (no TLS): subclass Pipecat’s Riva client to allow insecure channels, or run with a local override.
- Prod: enable TLS on the gRPC server and point Pipecat at `your-domain:443`.

### Testing

- Warmup (realtime streaming):
```bash
python3 test/warmup.py --server localhost:8000 --file long.mp3 --chunk-ms 50
```

- Simple client (prints PART/FINAL):
```bash
python3 test/client.py --server localhost:8000 --file mid.wav --chunk-ms 50
```

- Benchmark (gRPC realtime streaming under concurrency):
```bash
python3 test/bench.py --server localhost:8000 --n 20 --concurrency 5 --file long.mp3 --chunk-ms 50
```

### Sources & docs

- NVIDIA proto reference: `https://docs.nvidia.com/deeplearning/riva/user-guide/docs/reference/protos/riva_asr.proto.html`
- Pipecat Riva adapter usage: `https://github.com/pipecat-ai/pipecat-framework/blob/main/src/pipecat/services/riva/stt.py`

---

Legacy FastAPI docs (no longer active):

## Parakeet TDT-CTC 1.1B FastAPI (NeMo)

A single-process FastAPI service that runs NVIDIA Parakeet TDT-CTC 1.1B v2 (English) using the NeMo toolkit, exposing OpenAI-compatible audio endpoints and a streaming WebSocket endpoint.

- Endpoints:
  - `POST /v1/audio/transcriptions` — OpenAI-compatible transcription (multipart form: `file`)
  - `WS /v1/realtime` — OpenAI Realtime-compatible transcription over WebSocket
- Concurrency: asyncio lane workers + priority queue
- Metrics: JSONL logs under `logs/metrics/` + an on-pod Python report
- Health: `/healthz`, Readiness: `/readyz`

> GPU strongly recommended. NeMo downloads model checkpoints automatically on first run.

### Quickstart

Quickstart:
```bash
source scripts/env.sh
bash scripts/start_bg.sh && bash scripts/tail_bg_logs.sh

# Test once (from pod)
source .venv/bin/activate 2>/dev/null || true
python3 test/warmup.py

# Inspect saved transcription JSON (written by warmup.py)
cat test/results/warmup.txt
```

Defaults: `PARAKEET_MODEL_ID=nvidia/parakeet-tdt_ctc-1.1b`, `PARAKEET_USE_LOCAL_ATTENTION=1`, `PARAKEET_LOCAL_ATTENTION_CONTEXT=128`.
NeMo checkpoints are fetched automatically; no local FP32 model directory is required.

### Admission control

- Queue is capped to `PARAKEET_QUEUE_MAX_FACTOR * PARAKEET_MICROBATCH_MAX_BATCH`.
- If the queue is full, the API returns `429` with `Retry-After: PARAKEET_MAX_QUEUE_WAIT_S`.
- Each request has a queue TTL; if it waits longer than `PARAKEET_MAX_QUEUE_WAIT_S`, it is canceled with `503`.
- Upload size capped via `PARAKEET_MAX_UPLOAD_MB` (default 64 MB).

### Model

Model is loaded via NeMo by `PARAKEET_MODEL_ID` (default: `nvidia/parakeet-tdt_ctc-1.1b`). Local attention and chunking are enabled by default for long-form inference.

### API

- `POST /v1/audio/transcriptions`
  - form-data: `file` (required) — audio file (wav/flac/ogg/mp3). Resampled to 16 kHz mono.
  - response JSON: `{ "text": str }`

- `WS /v1/realtime`
  - OpenAI Realtime-style events: send `input_audio_buffer.append` with base64 PCM16 (mono, 16 kHz),
    then `response.create` to trigger transcription. Responses emit `response.output_text.delta` and `response.completed`.

- `GET /healthz`: basic health check.
- `GET /readyz`: returns `{ ready: true|false }` once model is loaded and scheduler started.

### Metrics (no endpoint)

- Structured JSON lines written to `logs/metrics/metrics.log` with daily rotation (kept 7 days).
- Each line includes: `ts`, `status`, `code`, `audio_len_s`, `duration_preprocess_s`, `duration_inference_s`, `duration_total_s`, `queue_wait_s`, `model`.
- On the pod, run the report directly from the metrics module:

```bash
python3 -m src.metrics --windows 30m 1h 3h 6h 12h 24h 3d
```

### Configuration

Defaults live in `scripts/env.sh`. You can override via environment vars before `start.sh`.

- `PARAKEET_MODEL_ID` (default: `nvidia/parakeet-tdt_ctc-1.1b`)
- `PARAKEET_USE_LOCAL_ATTENTION` (default: 1)
- `PARAKEET_LOCAL_ATTENTION_CONTEXT` (default: 128)
- `PARAKEET_SUBSAMPLING_CHUNKING_FACTOR` (default: 1)
- `PARAKEET_QUEUE_MAX_FACTOR` (default: 32)
- `PARAKEET_MAX_QUEUE_WAIT_S` (default: 2)
- `PARAKEET_MICROBATCH_WINDOW_MS` (default: 8)
- `PARAKEET_MICROBATCH_MAX_BATCH` (default: 32)
- `PARAKEET_MAX_AUDIO_SECONDS` (default: 600)
- `PARAKEET_MAX_UPLOAD_MB` (default: 64)
 
### Troubleshooting

- If first run downloads are slow, ensure Hugging Face cache is writable at `~/.cache/huggingface`.

 
- `OMP_NUM_THREADS` (default: 6)
- `MKL_NUM_THREADS` (default: 6)
- `CUDA_MODULE_LOADING` (default: `LAZY`)

### Purging

Purges everything by default (logs, model caches, venv, pip cache). No flags needed.

```bash
bash scripts/purge_pod.sh
```

### Purging

Purges everything by default (logs, model caches, venv, pip cache). No flags needed.

```bash
bash scripts/purge_pod.sh
```

### Sources & docs

- NVIDIA blog on Parakeet and long-form inference: `https://developer.nvidia.com/blog/pushing-the-boundaries-of-speech-recognition-with-nemo-parakeet-asr-models/`
