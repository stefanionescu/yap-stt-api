## Sherpa-ONNX Streaming ASR (NVIDIA FastConformer 80 ms CTC) — RunPod

This repo runs sherpa-onnx’s streaming WebSocket server with NVIDIA FastConformer Hybrid Streaming Multi (80 ms, CTC). It supports micro-batching across clients and prefers ONNX Runtime TensorRT EP when available (falls back to CUDA EP).

### What you get

- **bootstrap**: installs deps, sets up venv, downloads the 80 ms ONNX pack, enables TensorRT EP if present, and downloads PnC.
- **start**: runs the batching WebSocket server on **port 8000**.
- **stop+wipe**: kills the server and removes venv/repos/models/logs/TRT cache.
- **PnC (optional)**: punctuation+capitalization model downloaded; apply on finals only from your gateway.

### Directory layout

```
./
  scripts/
    bootstrap.sh
    start_server.sh
    stop_and_wipe.sh
  .venv/
  models/
    nemo_ctc_80ms/
    pnc/
  repos/
    sherpa-onnx/
  logs/
  trt_cache/
```

### Setup on RunPod (Ubuntu 22.04 / CUDA 12.x)

```bash
# 1) (Optional) Install TensorRT pinned to CUDA 12.x, then bootstrap
# Check driver supports your target CUDA first:
#   nvidia-smi | head -n 15   # if driver shows only CUDA 12.x, pin TRT to cuda12
TRT_CUDA_SERIES=cuda12 bash scripts/install_tensorrt.sh   # optional; skip if TRT already present

# If you pinned TRT to CUDA 12.x, export CUDA_HOME before bootstrap (example paths):
#   export CUDA_HOME=/usr/local/cuda-12.8
#   export CUDNN_HOME=/usr/lib/x86_64-linux-gnu
#   export TENSORRT_HOME=/usr/lib/x86_64-linux-gnu

bash scripts/bootstrap.sh          # sets up venv, downloads models, builds ORT (TRT if available)

# 2) Activate venv and install test deps
source .venv/bin/activate
pip install -r requirements.txt

# 3) Start server (defaults: PORT=8000, MAX_BATCH=12, LOOP_MS=15)
bash scripts/start_server.sh
# Logs → ./logs/server.out (optional tail: tail -f logs/server.out | sed -u 's/\r/\n/g')

# 4) Warmup and verify
python test/warmup.py --server localhost:8000 --file mid.wav --chunk-ms 120
cat test/results/warmup.txt
```

You can override at runtime:

```bash
PORT=8000 MAX_BATCH=12 LOOP_MS=15 PROVIDER=cuda ./scripts/start_server.sh
```

### Stop and purge

```bash
bash scripts/stop_and_wipe.sh
```

### PnC (punctuation + capitalization) — finals only

Bootstrap downloads the online PnC model to `models/pnc`. Apply it only when emitting finals from your gateway/service to keep partial latency low:

```python
import sherpa_onnx as so
pnc = so.OnlinePunctuation(
    cnn_bilstm="models/pnc/model.onnx",
    bpe_vocab="models/pnc/bpe.vocab"
)
def punctuate(final_text: str, ctx_tail: str) -> str:
    return pnc.add_punctuation((ctx_tail + " " + final_text).strip())
```

Recommended: keep a short rolling context tail (~60 tokens) per session, but only run PnC on finals.

### Notes / knobs

- **Micro-batching**: tune `MAX_BATCH` (e.g., 8–16) and `LOOP_MS` (10–20 ms).
- **Client frames**: send 120–160 ms 16 kHz mono PCM for stable batching.
- **Provider**: `tensorrt` first, fallback `cuda`.
- **TRT cache**: engines saved under `./trt_cache` for faster restarts.
- **Swap model**: replace the 80 ms pack URL in `scripts/bootstrap.sh` to use 480/1040 ms variants.
