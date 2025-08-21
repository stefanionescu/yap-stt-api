## Parakeet 0.6B v2 ONNX FastAPI (ORT + TensorRT-EP)

A single-process FastAPI service that runs NVIDIA Parakeet TDT 0.6b v2 (English) converted to ONNX, exposing a one-shot transcription endpoint.

- Endpoint: `POST /v1/transcribe` (multipart form: `file`)
- Concurrency: asyncio lane workers + priority queue
- Metrics: JSONL logs under `logs/metrics/` + an on-pod Python report
- Health: `/healthz`, Readiness: `/readyz`

> GPU-only: requirements are pinned to onnxruntime-gpu and onnx-asr >= 0.7.0. CPU ORT is not supported here.

### Admission control

- Queue is capped to `PARAKEET_NUM_LANES * PARAKEET_QUEUE_MAX_FACTOR`.
- If the queue is full, the API returns `429` with `Retry-After: PARAKEET_MAX_QUEUE_WAIT_S`.
- Each request has a queue TTL; if it waits longer than `PARAKEET_MAX_QUEUE_WAIT_S`, it is canceled with `503`.
- Upload size capped via `PARAKEET_MAX_UPLOAD_MB` (default 64 MB).

### Model

Models can be loaded from Hugging Face by onnx-asr (hub ids) or from a local INT8 directory.

- Default model id: `nemo-parakeet-tdt-0.6b-v2`
- Fallback: `istupakov/parakeet-tdt-0.6b-v2-onnx`  \
  See: [istupakov/parakeet-tdt-0.6b-v2-onnx](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx)

INT8 setup (recommended):

```bash
# Defaults already set: PARAKEET_MODEL_DIR=./models/parakeet-int8 and PARAKEET_USE_DIRECT_ONNX=1
# You can override these if desired.

# Fetch INT8 artifacts (idempotent; set FORCE_FETCH_INT8=1 to refetch)
# Requires huggingface_hub (already in requirements) and optional HF_TOKEN
bash scripts/fetch_int8.sh

# Files will be placed as:
#   $PARAKEET_MODEL_DIR/encoder-model.onnx
#   $PARAKEET_MODEL_DIR/decoder_joint-model.onnx
#   $PARAKEET_MODEL_DIR/vocab.txt
```

### Run (venv, GPU only)

```bash
# 1) Setup (installs deps, loads defaults from scripts/env.sh)
bash scripts/setup.sh
source .venv/bin/activate

# 2) Verify GPU provider is available
python -c "import onnxruntime as ort; print(ort.get_available_providers())"  # must include CUDAExecutionProvider

# 3) Start server (foreground)
bash scripts/start.sh
# or start in background and tail logs
bash scripts/start_bg.sh
bash scripts/tail_bg_logs.sh

# 4) Warmup test (result saved to test/results/warmup.txt)
python3 test/warmup.py --file long.mp3
```

If you want to tweak defaults (lanes, paths, queue), edit `scripts/env.sh`.

### API

- `POST /v1/transcribe`
  - form-data: `file` = audio file (wav/flac/ogg/mp3). Service resamples to 16 kHz mono.
  - response JSON: `{ "text": str, "duration": float, "sample_rate": 16000, "model": str }`

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

- `PARAKEET_MODEL_DIR` (local INT8 dir; if set with `PARAKEET_USE_DIRECT_ONNX=1`, used instead of hub)
- `PARAKEET_USE_DIRECT_ONNX` (1 to prefer local INT8 dir and explicit providers)
- `PARAKEET_MODEL_ID` (default: `nemo-parakeet-tdt-0.6b-v2`)
- `PARAKEET_FALLBACK_MODEL_ID` (default: `istupakov/parakeet-tdt-0.6b-v2-onnx`)
- `PARAKEET_NUM_LANES` (default: 6)
- `PARAKEET_QUEUE_MAX_FACTOR` (default: 2)
- `PARAKEET_MAX_QUEUE_WAIT_S` (default: 30)
- `PARAKEET_MAX_AUDIO_SECONDS` (default: 600)
- `PARAKEET_MAX_UPLOAD_MB` (default: 64)

TensorRT engine and timing caches (Linux GPU with ORT TensorRT-EP builds):

- `TRT_ENGINE_CACHE` (default: `/models/trt_cache`)
- `TRT_TIMING_CACHE` (default: `/models/timing.cache`)
- `PARAKEET_USE_TRT` (default: 1) — enable TensorRT EP if available
- `ORT_INTRA_OP_NUM_THREADS` (default: 1)
- `OMP_NUM_THREADS` (default: 1)
- `MKL_NUM_THREADS` (default: 1)
- `CUDA_MODULE_LOADING` (default: `LAZY`)

### Testing

**Warmup (single request)**
```bash
# Default: uses samples/mid.wav
python3 test/warmup.py

# Custom file from samples/
python3 test/warmup.py --file long.mp3

# View full transcription result
python3 -c "import json; print(json.load(open('test/results/warmup.txt'))['text'])"
```

**Benchmark (fixed number of requests)**
```bash
# Basic: 40 requests, concurrency 1
python3 test/bench.py --n 40

# High load: 100 requests, 6 concurrent workers
python3 test/bench.py --n 100 --concurrency 6

# Specific file stress test
python3 test/bench.py --n 50 --file long.mp3 --concurrency 4
```

**TPM (transactions per minute - constant load)**
```bash
# Default: 6 workers for 60 seconds
python3 test/tpm.py --concurrency 6

# High concurrency for 2 minutes
python3 test/tpm.py --concurrency 12 --duration 120

# Single file sustained load
python3 test/tpm.py --concurrency 8 --file short-noisy.wav
```

**TCP client (for RunPod endpoints)**
```bash
# Setup .env with RUNPOD_TCP_HOST, RUNPOD_TCP_PORT, RUNPOD_API_KEY
python3 test/client.py --file mid.wav
```

### Purging

Purges everything by default (logs, TRT caches, model caches, venv, pip cache). No flags needed.

```bash
bash scripts/purge_pod.sh
```

### Sources & docs

- Parakeet 0.6B v2 ONNX: `https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx`
- ONNX Runtime — TensorRT EP: `https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html`
- I/O Binding: `https://onnxruntime.ai/docs/performance/tune-performance/iobinding.html`
- L40S GPU: `https://www.nvidia.com/en-us/data-center/l40s/`
