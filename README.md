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
# Export your API key and then download, compile, configure, and start Yap STT server
KYUTAI_API_KEY=your_secret_here bash scripts/main.sh
```

**This will:**
1. Install CUDA 12.4 toolkit (purges conflicting versions)
2. Install Rust toolchain and compile yap-server (yap-server) with CUDA
3. Fetch STT configs and models
4. Start server in tmux session on port 8000
5. Optionally run a smoke test to verify functionality

**Result:** GPU-accelerated STT server at `ws://localhost:8000` ready for connections.

## Docker

### One-Command Build & Push

Use the provided script for easy Docker operations:

```bash
# Build and push to DockerHub (requires docker login)
bash ./docker/build.sh myusername/yap-stt-api:latest

# Build only (for testing)
bash ./docker/build.sh --build-only myusername/yap-stt-api:dev

# Push existing image
bash ./docker/build.sh --push-only myusername/yap-stt-api:v1.0.0

# Build without cache (clean build)
bash ./docker/build.sh --no-cache myusername/yap-stt-api:latest
```

**Requirements:**
- Docker with BuildKit enabled
- DockerHub account: `docker login`
- Image name format: `username/image:tag`

### Manual Build & Push

If you prefer manual commands:

```bash
# Build
docker build -f docker/Dockerfile -t myusername/yap-stt-api:latest .

# Push
docker push myusername/yap-stt-api:latest
```

### Run Container

**Local GPU:**
```bash
docker run --rm -it \
  --gpus all \
  -p 8000:8000 \
  -e KYUTAI_API_KEY=your_secret_here \
  myusername/yap-stt-api:latest
```

**Background/Production:**
```bash
docker run -d \
  --name yap-stt \
  --gpus all \
  -p 8000:8000 \
  -e KYUTAI_API_KEY=your_secret_here \
  -v /path/to/cache:/workspace/hf_cache \
  myusername/yap-stt-api:latest
```

**RunPod/Cloud GPU:**
```bash
# Use your pushed image in RunPod template
# Set environment: KYUTAI_API_KEY=your_secret_here
# Expose port: 8000
```

### Test Container

```bash
# Get container ID
CONTAINER_ID=$(docker ps -q --filter "ancestor=myusername/yap-stt-api:latest")

# Health check
docker exec -e KYUTAI_API_KEY=your_secret_here $CONTAINER_ID \
  python3 /workspace/test/warmup.py --server 127.0.0.1:8000 --rtf 1000

# Interactive test
docker exec -it -e KYUTAI_API_KEY=your_secret_here $CONTAINER_ID \
  python3 /workspace/test/client.py --server 127.0.0.1:8000 --rtf 1.0

# Load test
docker exec -e KYUTAI_API_KEY=your_secret_here $CONTAINER_ID \
  python3 /workspace/test/bench.py --n 10 --concurrency 2 --rtf 1.0
```

### Docker Notes

- **API Key Security**: Key is injected at runtime, never stored in image
- **Cache Persistence**: Use `-v /host/path:/workspace/hf_cache` to avoid re-downloading models
- **Logs**: Available at `/workspace/logs/yap-server.log` inside container
- **Same Logic**: Docker uses identical config injection as `scripts/03_start_server.sh`

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