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
# 1) Make scripts executable
chmod +x scripts/*.sh

# 2) (Optional) Install TensorRT, then bootstrap to build ORT with TRT EP
./scripts/install_tensorrt.sh   # optional; skip if TRT already present
./scripts/bootstrap.sh          # sets up venv, downloads models, builds ORT (TRT if available)

# 3) Activate venv and install test deps
source .venv/bin/activate
pip install -r requirements.txt

# 4) Start server (defaults: PORT=8000, MAX_BATCH=12, LOOP_MS=15)
./scripts/start_server.sh
# Logs → ./logs/server.out (optional tail: tail -f logs/server.out | sed -u 's/\r/\n/g')

# 5) Warmup and verify
python test/warmup.py --server localhost:8000 --file mid.wav --chunk-ms 120
cat test/results/warmup.txt
```

You can override at runtime:

```bash
PORT=8000 MAX_BATCH=12 LOOP_MS=15 PROVIDER=cuda ./scripts/start_server.sh
```

### Stop and purge

```bash
./scripts/stop_and_wipe.sh
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
