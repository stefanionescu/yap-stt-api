## Parakeet 0.6B v2 ONNX FastAPI (ORT + TensorRT-EP)

A single-process FastAPI service that runs NVIDIA Parakeet TDT 0.6B v2 (English) converted to ONNX, exposing a one-shot transcription endpoint.

- Endpoint: `POST /v1/transcribe` (multipart form: `file`)
- Concurrency: asyncio lane workers + priority queue
- Metrics: JSONL logs under `logs/metrics/` + an on-pod Python report (no Prometheus)
- Health: `/healthz`, Readiness: `/readyz`

> GPU-only: requirements are pinned to onnxruntime-gpu and onnx-asr >= 0.7.0. CPU ORT is not supported here.

### Admission control

- Queue is capped to `PARAKEET_NUM_LANES * PARAKEET_QUEUE_MAX_FACTOR`.
- If the queue is full, the API returns `429` with `Retry-After: PARAKEET_MAX_QUEUE_WAIT_S`.
- Each request has a queue TTL; if it waits longer than `PARAKEET_MAX_QUEUE_WAIT_S`, it is canceled with `503`.
- Upload size capped via `PARAKEET_MAX_UPLOAD_MB` (default 64 MB).

### Model

Default model uses onnx-asr hub alias `nemo-parakeet-tdt-0.6b-v2`, backed by the HF ONNX export:

- HF: `istupakov/parakeet-tdt-0.6b-v2-onnx`  
  See: `https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx`

### Run (venv, GPU only)

```bash
# 1) Setup (installs deps, loads defaults from scripts/env.sh)
bash scripts/purge_pod.sh
bash scripts/setup.sh
source .venv/bin/activate

# 2) Fetch INT8 model from Hugging Face (respects HF_TOKEN if set)
bash scripts/fetch_int8_model.sh

# 3) Verify GPU provider is available
python -c "import onnxruntime as ort; print(ort.get_available_providers())"  # must include CUDAExecutionProvider

# 4) Start server
bash scripts/start.sh

# 5) Warmup test (result saved to test/results/warmup.txt)
python3 test/warmup.py --url http://127.0.0.1:8000
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

- `PARAKEET_MODEL_DIR` (default: `/models/parakeet-int8`) — local INT8 folder
- `PARAKEET_NUM_LANES` (default: 6)
- `PARAKEET_QUEUE_MAX_FACTOR` (default: 2)
- `PARAKEET_MAX_QUEUE_WAIT_S` (default: 30)
- `PARAKEET_MAX_AUDIO_SECONDS` (default: 600)
- `PARAKEET_MAX_UPLOAD_MB` (default: 64)

TensorRT engine and timing caches (Linux GPU with ORT TensorRT-EP builds):

- `TRT_ENGINE_CACHE` (default: `/models/trt_cache`)
- `TRT_TIMING_CACHE` (default: `/models/timing.cache`)

### Warmup

- At startup, the service runs a short warmup (0.5s) to initialize runtime and caches.
- You can also hit a warmup request via `test/warmup.py` using a file in `samples/` or provide a path:

```bash
python3 test/warmup.py --file samples/your.wav
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
