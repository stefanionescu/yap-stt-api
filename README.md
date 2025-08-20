## Parakeet 0.6B v2 ONNX FastAPI (ORT + TensorRT-EP)

A single-process FastAPI service that runs NVIDIA Parakeet TDT 0.6B v2 (English) converted to ONNX, exposing a one-shot transcription endpoint.

- Endpoint: `POST /v1/transcribe` (multipart form: `file`)
- Concurrency: asyncio lane workers + priority queue
- Metrics: JSONL logs under `logs/metrics/` + an on-pod Python report (no Prometheus)
- Health: `/healthz`, Readiness: `/readyz`

### Admission control

- Queue is capped to `PARAKEET_NUM_LANES * PARAKEET_QUEUE_MAX_FACTOR`.
- If the queue is full, the API returns `429` with `Retry-After: PARAKEET_MAX_QUEUE_WAIT_S`.
- Each request has a queue TTL; if it waits longer than `PARAKEET_MAX_QUEUE_WAIT_S`, it is canceled with `503`.
- Upload size capped via `PARAKEET_MAX_UPLOAD_MB` (default 64 MB).

### Model

Default model uses onnx-asr hub alias `nemo-parakeet-tdt-0.6b-v2`, backed by the HF ONNX export:

- HF: `istupakov/parakeet-tdt-0.6b-v2-onnx`  
  See: `https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx`

### Install (local dev, macOS CPU)

```bash
./scripts/setup.sh
source .venv/bin/activate
./scripts/start.sh
```

Send a request:

```bash
python3 test/warmup.py --file /path/to/audio.wav --url http://127.0.0.1:8000
```

### Run (Linux GPU / Runpod)

Build image:

```bash
docker build -t parakeet-onnx:latest .
```

Run with GPU:

```bash
docker run --gpus all -p 8000:8000 \
  -e PARAKEET_NUM_LANES=6 \
  -e TRT_ENGINE_CACHE=/models/trt_cache -e TRT_TIMING_CACHE=/models/timing.cache \
  -v $(pwd)/models:/models \
  parakeet-onnx:latest
```

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

Environment variables (prefix `PARAKEET_`):

- `PARAKEET_MODEL_ID` (default: `nemo-parakeet-tdt-0.6b-v2`)
- `PARAKEET_NUM_LANES` (default: 2; set 6 for L40S)
- `PARAKEET_QUEUE_MAX_FACTOR` (default: 2)
- `PARAKEET_MAX_QUEUE_WAIT_S` (default: 30)
- `PARAKEET_MAX_AUDIO_SECONDS` (default: 600)
- `PARAKEET_MAX_UPLOAD_MB` (default: 64)

TensorRT engine and timing caches (Linux GPU with ORT TensorRT-EP builds):

- `TRT_ENGINE_CACHE` (default: `/models/trt_cache`)
- `TRT_TIMING_CACHE` (default: `/models/timing.cache`)

### Notes on Precision & EPs

- This v1 uses `onnx-asr` to keep the RNNT decode/simple setup. Next iteration wires explicit ORT sessions with TensorRT EP and I/O binding (INT8/FP16) for maximum throughput.

### Warmup

- At startup, the service runs a short warmup (0.5s) to initialize runtime and caches.
- You can also hit a warmup request via `test/warmup.py` using a file in `samples/` or provide a path:

```bash
python3 test/warmup.py --file samples/your.wav
```

### Docker vs bare runtime

- For Runpod, a Docker image is recommended: consistent CUDA/TRT/ORT stack, enables persistent TRT caches via volumes, reproducible deploys.
- For quick iteration, you can run directly with `uvicorn` on the pod using a Python venv; just ensure the correct ORT GPU build and CUDA/TensorRT libs are present. This repo supports both workflows.

### Sources & docs

- Parakeet 0.6B v2 ONNX: `https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx`
- ONNX Runtime — TensorRT EP: `https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html`
- I/O Binding: `https://onnxruntime.ai/docs/performance/tune-performance/iobinding.html`
- L40S GPU: `https://www.nvidia.com/en-us/data-center/l40s/`
- Runpod ports: `https://docs.runpod.io/pods/configuration/expose-ports`
