# Yap STT Service

One-command deployment for **Yap STT Server** with GPU acceleration. Automated CUDA 12.4 setup, Rust compilation, and production-ready WebSocket server.

## Features

- **One-command setup** - Complete deployment in ~10 minutes
- **CUDA 12.4 optimized** - Automatic GPU setup for L40S/A100/RTX cards  
- **Production ready** - tmux sessions, logging, monitoring
- **Testing suite** - Load testing, benchmarks, real-time clients
- **RunPod compatible** - Tested on cloud GPU instances

## Quick Start (One Command)

### Complete Setup + Deployment
```bash
# 0) Export your Kyutai server key (required by all scripts)
export KYUTAI_API_KEY=your_secret_here

# 1) Download, compile, configure, and start Yap STT server
bash scripts/main.sh
```

**This will:**
1. Install CUDA 12.4 toolkit (purges conflicting versions)
2. Install Rust toolchain and compile yap-server (yap-server) with CUDA
3. Fetch STT configs and models
4. Start server in tmux session on port 8000
5. Optionally run a smoke test to verify functionality

**Result:** GPU-accelerated STT server at `ws://localhost:8000` ready for connections.

## Service Management

### Check Server Status
```bash
# View tmux sessions, listening ports, recent logs
bash scripts/04_status.sh
```

### Monitor Server Logs
```bash
# Tail live server logs
tail -f /workspace/logs/yap-server.log

# Attach to tmux session
tmux attach -t yap-stt
```

### Stop Service
```bash
# Graceful shutdown (keeps installation)
tmux kill-session -t yap-stt

# Complete cleanup
bash scripts/99_stop.sh
```

## ⚙️ Manual Step-by-Step Setup

For development or custom deployments:

```bash
# 1. Install system dependencies (CUDA, Rust, Python, ffmpeg)
bash scripts/00_prereqs.sh

# 2. Compile and install yap-server (yap-server) with CUDA support
bash scripts/01_install_yap_server.sh

# 3. Fetch Kyutai configs and STT model definitions
bash scripts/02_fetch_configs.sh

# 4. Start server in tmux session
bash scripts/03_start_server.sh

# 5. Check status and verify port binding
bash scripts/04_status.sh

# 6. Run smoke test with reference client (if enabled)
bash scripts/05_smoke_test.sh
```

## Runpod Deployment

### RunPod Setup
1. **Launch Instance**: Ubuntu 22.04 + L40S/A100/RTX 4090
2. **Expose Port**: `8000` in RunPod dashboard  
3. **Run Setup**:
   ```bash
   git clone <your-repo-url>
   cd yap-stt-api
   scripts/main.sh
   ```
4. **Connect**: Server will be at `ws://your-runpod-ip:8000`

**Requirements:**
- **GPU**: L40S/A100 (recommended) or RTX 4090/3090
- **RAM**: 16GB+ system memory  
- **Storage**: 10GB+ free space
- **Network**: Port 8000 exposed publicly

**Environment Variables** (required/optional):
```bash
# Server settings  
YAP_ADDR=0.0.0.0               # Bind address
YAP_PORT=8000                  # Server port
HF_HOME=/workspace/hf_cache    # Model cache location
# Auth (Kyutai server key — NOT your RunPod API key) — must be exported before running scripts
# Example: export KYUTAI_API_KEY=your_secret_here
```

## Configuration

### Server Configuration
The service uses the provided STT config (`config-stt-en_fr-hf.toml`) supporting:
- **Languages**: English + French  
- **Models**: Streaming optimized Transformer architecture
- **GPU**: CUDA acceleration with automatic mixed precision
- **WebSocket**: Native Rust server with JSON protocol

### Performance Tuning

**GPU Memory Optimization:**
```bash
# Edit config after setup
vim server/config-stt-en_fr-hf.toml

# Key parameters:
# - batch_size: Concurrent streams (adjust for VRAM)
# - beam_size: Search beam width (accuracy vs speed)  
# - streaming_chunk_size: Audio chunk processing size
```

**Connection Limits:**
```bash
# The service automatically sets:
ulimit -n 1048576  # High file descriptor limit
# Supports hundreds of concurrent WebSocket connections
```

### Handling Capacity Rejections ("no free channels")

When the server is fully subscribed (all `batch_size` slots are in use), it accepts the WebSocket upgrade, then immediately sends a binary MessagePack frame:

- type: `Error`
- message: `"no free channels"`

and then closes the socket. Treat this as a non-fatal, retryable condition.

Recommended client pattern:

- Gate start-up: after connecting, wait briefly (200–500 ms) for either `Ready` or `Error` before sending audio
- If `Error.message` contains `"no free channels"`, close and retry with exponential backoff + jitter
- Use bounded retries and/or a local queue; avoid thundering herd on recovery

Python recipe:

```python
import asyncio, os, msgpack, websockets, random, time

async def connect_with_capacity_retry(url: str, headers: list[tuple[str,str]], max_retries=8):
    backoff = 0.2
    for attempt in range(max_retries):
        try:
            async with websockets.connect(url, extra_headers=headers, compression=None, max_size=None) as ws:
                ready = asyncio.Event()
                done = asyncio.Event()
                rejected = False

                async def rx():
                    nonlocal rejected
                    try:
                        async for raw in ws:
                            if isinstance(raw, (bytes, bytearray)):
                                data = msgpack.unpackb(raw, raw=False)
                                if data.get("type") == "Ready":
                                    ready.set()
                                elif data.get("type") == "Error":
                                    if "no free channels" in (data.get("message") or "").lower():
                                        rejected = True
                                    done.set()
                                    break
                    except Exception:
                        done.set()

                task = asyncio.create_task(rx())
                try:
                    await asyncio.wait_for(asyncio.wait({ready.wait(), done.wait()}, return_when=asyncio.FIRST_COMPLETED), timeout=0.5)
                except asyncio.TimeoutError:
                    pass

                if done.is_set() and rejected:
                    # capacity — cleanly close and retry
                    with contextlib.suppress(Exception):
                        asyncio.create_task(ws.close(code=1000, reason="capacity"))
                    raise RuntimeError("capacity: no free channels")

                # proceed to send audio normally; ensure you handle later errors too
                return ws  # or keep streaming within this context

        except Exception as e:
            # Capacity or transient network — backoff + jitter
            sleep = min(backoff, 5.0) + random.uniform(0, 0.2)
            await asyncio.sleep(sleep)
            backoff *= 2

    raise RuntimeError("exhausted retries")
```

Notes:

- Other errors (e.g., auth 401 before upgrade) should be treated as fatal and fixed at config time
- The server may also emit `Error` later in the stream if resources are reclaimed; apply the same logic

## Testing

Install Python dependencies:
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Basic Testing
```bash
# Interactive client with network latency measurement (realtime)
# Use the Kyutai API key (different from your RunPod API key)
KYUTAI_API_KEY=public_token python test/client.py --server localhost:8000 --rtf 1.0

# Interactive client (fast)
KYUTAI_API_KEY=public_token python test/client.py --server localhost:8000 --rtf 10.0

# Load testing (realtime)
KYUTAI_API_KEY=public_token python test/bench.py --n 20 --concurrency 5 --rtf 1.0

# Load testing (fast)
KYUTAI_API_KEY=public_token python test/bench.py --n 20 --concurrency 5 --rtf 100.0

# Health check (fast warmup)
KYUTAI_API_KEY=public_token python test/warmup.py --rtf 1000.0
```

### Checking Test Results & Logs
```bash
# View interactive client metrics and network latency
cat test/results/client_metrics.jsonl

# View load testing performance metrics  
cat test/results/bench_metrics.jsonl | head -5

# Check for connection errors and timeouts
cat test/results/bench_errors.txt

# View health check results
cat test/results/warmup.txt

# Monitor server logs during testing
tail -f /workspace/logs/yap-server.log

# Check server status
scripts/04_status.sh
```

### Test Files
- `samples/mid.wav` - Clean speech
- `samples/long.mp3` - Extended audio
- `samples/short-noisy.wav` - Background noise test

### Test Results
Tests create detailed logs in `test/results/`:
- `client_metrics.jsonl` - Interactive session with network latency
- `bench_metrics.jsonl` - Performance metrics
- `bench_errors.txt` - Connection errors  
- `warmup.txt` - Health check results

**Network Latency Metrics** (in `client.py`):
- **Connection time**: WebSocket establishment latency
- **Handshake time**: Time to receive Ready message  
- **First response**: Time from first audio to first server response

### Analyzing Results
```bash
# Find performance issues in bench results
grep -E '"delta_to_audio_ms":[0-9]+' test/results/bench_metrics.jsonl | head -3

# Check connection error patterns  
grep -i "timeout\|connection\|refused" test/results/bench_errors.txt

# Look for CUDA/GPU errors in server logs
grep -i "cuda\|gpu\|memory" /workspace/logs/yap-server.log

# Monitor real-time performance during tests
tail -f /workspace/logs/yap-server.log | grep -i "batch\|worker"
```

## Protocol

**WebSocket Endpoint**: `ws://localhost:8000` 

**Audio Format**:
- 24kHz, 16-bit PCM, mono
- Base64 encoded in JSON messages

**Protocol Flow**:
```json
// Client → Server
{"type":"StartSTT"}                            // Start session
{"type":"Audio","audio":"<base64_audio>"}      // Audio chunks
{"type":"Flush"}                               // End session

// Server → Client  
{"type":"Ready"}                               // Ready to receive
{"type":"Word","word":"hello"}                 // Word tokens
{"type":"Partial","text":"hello world"}       // Partial results
{"type":"Final","text":"hello world"}         // Final transcript
```

### Authentication

- **Header**: `kyutai-api-key: <your_api_key>` (Kyutai server key; do NOT use your RunPod key)
- **Server config**: `scripts/03_start_server.sh` injects your key into `authorized_ids` at runtime.
- **Set your key**:

```bash
# Option A: set once (default .env written by scripts/main.sh)
sed -i.bak 's/^KYUTAI_API_KEY=.*/KYUTAI_API_KEY=my_secret_123/' scripts/.env

# Option B: export before starting (Kyutai key)
export KYUTAI_API_KEY=my_secret_123
scripts/03_start_server.sh

# Clients (Kyutai key):
export KYUTAI_API_KEY=my_secret_123
python test/client.py --server localhost:8000

For RunPod-hosted servers, you must also export your RunPod token and the client will pass it upstream:
```bash
export KYUTAI_API_KEY=my_secret_123
export RUNPOD_API_KEY=rp_xxx
python test/client.py --server your-pod-id-12345-uc.a.runpod.net:8000
```
```

## Troubleshooting

### Server Won't Start
```bash
# Check CUDA 12.4 installation
nvidia-smi && nvcc --version

# View server logs (live)
tail -f /workspace/logs/yap-server.log

# Check specific errors in logs
cat /workspace/logs/yap-server.log | grep -i error

# Check tmux session
tmux attach -t yap-stt
```

### Connection Issues  
```bash
# Check port binding
ss -tlnp | grep 8000

# Test WebSocket connectivity
python test/warmup.py

# Check recent connection errors
cat test/results/bench_errors.txt | tail -10

# For RunPod: ensure port 8000 is exposed
```

### Performance Issues
```bash
# Check GPU utilization during tests
nvidia-smi -l 1

# View server resource usage
top -p $(pgrep yap-server)

# Find slow sessions in results
grep -E '"delta_to_audio_ms":[5-9][0-9][0-9]|[0-9]{4}' test/results/bench_metrics.jsonl
```

### CUDA Issues
```bash
# Check for CUDA errors in logs
grep -i "cuda\|ptx\|driver" /workspace/logs/yap-server.log

# Clean install if CUDA problems
scripts/99_stop.sh  
scripts/main.sh
```

## Structure

```
├── scripts/                       # Deployment scripts
│   ├── main.sh                    # One-command setup
│   ├── 00_prereqs.sh              # CUDA 12.4 + dependencies
│   ├── 01_install_yap_server.sh   # Compile server
│   ├── 02_fetch_configs.sh        # Get STT configs
│   ├── 03_start_server.sh         # Start in tmux
│   ├── 04_status.sh               # Monitor server
│   └── 99_stop.sh                 # Complete cleanup
├── test/                          # Testing suite
│   ├── client.py                  # Interactive client
│   ├── bench.py                   # Load testing
│   └── warmup.py                  # Health checks
├── samples/                       # Test audio files
└── requirements.txt               # Python deps
```

## Cleanup

```bash
# Complete removal
scripts/99_stop.sh
```

**Removes**:
- yap-server binary + Rust toolchain
- All CUDA installations and configs
- HuggingFace model cache and logs  
- tmux sessions and build artifacts