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

Defaults: `PARAKEET_MODEL_ID=nvidia/parakeet-tdt-0.6b-v2`, streaming step `320ms`, context `10s`.

### Configuration

Key environment variables (see `scripts/env.sh`):

- `PARAKEET_MODEL_ID` (default: `nvidia/parakeet-tdt-0.6b-v2`)
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