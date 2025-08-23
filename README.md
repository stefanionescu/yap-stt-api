## Parakeet 0.6B v2 ONNX FastAPI (ORT + TensorRT-EP)

A single-process FastAPI service that runs NVIDIA Parakeet TDT 0.6b v2 (English) converted to ONNX, exposing a one-shot transcription endpoint.

- Endpoint: `POST /v1/transcribe` (multipart form: `file`)
- Concurrency: asyncio lane workers + priority queue
- Metrics: JSONL logs under `logs/metrics/` + an on-pod Python report
- Health: `/healthz`, Readiness: `/readyz`

> GPU-only: requirements are pinned to onnxruntime-gpu and onnx-asr >= 0.7.0. CPU ORT is not supported here.

### Quickstart

Option A (local FP32, recommended):
```bash
# 1) Install TensorRT wheel (one-time)
bash scripts/install_trt.sh

# 2) Fetch FP32 artifacts locally (into PARAKEET_MODEL_DIR)
source scripts/env.sh
bash scripts/fetch_fp32.sh

# 3) Start the API (wires TRT libs automatically)
bash scripts/start_bg.sh && bash scripts/tail_bg_logs.sh

# 4) Test once (from pod)
source .venv/bin/activate 2>/dev/null || true
python3 test/warmup.py --file long.mp3
```

Defaults: `PARAKEET_MODEL_DIR=./models/parakeet-fp32`, `PARAKEET_USE_TENSORRT=1`.
- Local vs hub is decided solely by `PARAKEET_MODEL_DIR`: if set and contains model files, the service loads the local directory; otherwise it uses the hub id.
- Note: `PARAKEET_USE_DIRECT_ONNX` is deprecated and ignored by the server.
- Runtime will fall back to CUDA EP automatically if TRT isn’t available.

### Admission control

- Queue is capped to `PARAKEET_NUM_LANES * PARAKEET_QUEUE_MAX_FACTOR`.
- If the queue is full, the API returns `429` with `Retry-After: PARAKEET_MAX_QUEUE_WAIT_S`.
- Each request has a queue TTL; if it waits longer than `PARAKEET_MAX_QUEUE_WAIT_S`, it is canceled with `503`.
- Upload size capped via `PARAKEET_MAX_UPLOAD_MB` (default 64 MB).

### Model

Models can be loaded from Hugging Face by onnx-asr (hub ids) or from a local FP32 directory.

- Default model id: `nemo-parakeet-tdt-0.6b-v2`
- Fallback: `istupakov/parakeet-tdt-0.6b-v2-onnx`  \
  See: [istupakov/parakeet-tdt-0.6b-v2-onnx](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx)

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

- `PARAKEET_MODEL_DIR` (local FP32 dir; if set and contains `encoder-model.onnx`, `encoder-model.onnx.data`, `decoder_joint-model.onnx`, `vocab.txt`, `config.json`, local loading is used; otherwise the hub is used)
- `PARAKEET_MODEL_ID` (default: `nemo-parakeet-tdt-0.6b-v2`)
- `PARAKEET_FALLBACK_MODEL_ID` (default: `istupakov/parakeet-tdt-0.6b-v2-onnx`)
- `PARAKEET_NUM_LANES` (default: 3)
- `PARAKEET_QUEUE_MAX_FACTOR` (default: 2)
- `PARAKEET_MAX_QUEUE_WAIT_S` (default: 30)
- `PARAKEET_MAX_AUDIO_SECONDS` (default: 600)
- `PARAKEET_MAX_UPLOAD_MB` (default: 64)
- `PARAKEET_USE_TENSORRT` (default: 1) — enable TensorRT EP if libs present (auto-fallback to CUDA)
- Deprecated: `PARAKEET_USE_DIRECT_ONNX` (server ignores this; kept for backward compatibility)

TensorRT engine and timing caches (Linux GPU with ORT TensorRT-EP builds):

- `TRT_ENGINE_CACHE` (default: `/models/trt_cache`)
- `TRT_TIMING_CACHE` (default: `/models/timing.cache`)
- `PARAKEET_USE_TENSORRT` (default: 1) — enable TensorRT EP if libs present (auto-fallback to CUDA)

### Troubleshooting

- "Model dir missing: /path/to/models/parakeet-fp32" → You skipped the FP32 fetch. Run:
```bash
source scripts/env.sh
bash scripts/fetch_fp32.sh
bash scripts/start.sh
```
- Want to use hub without local files? Clear the var before launching:
```bash
export PARAKEET_MODEL_DIR=""
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000 --loop uvloop --http httptools
```

Docs: `https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html`
- `ORT_INTRA_OP_NUM_THREADS` (default: 1)
- `OMP_NUM_THREADS` (default: 6)
- `MKL_NUM_THREADS` (default: 6)
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
# Standard purge (keeps TRT wheels)
bash scripts/purge_pod.sh

# Deep purge (removes TRT wheels too)
bash scripts/purge_pod.sh --uninstall-trt
```

### Sources & docs

- Parakeet 0.6B v2 ONNX: `https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx`
- ONNX Runtime — TensorRT EP: `https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html`
- I/O Binding: `https://onnxruntime.ai/docs/performance/tune-performance/iobinding.html`
- L40S GPU: `https://www.nvidia.com/en-us/data-center/l40s/`
