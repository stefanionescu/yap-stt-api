# Yap STT Service

Complete production-ready **Moshi STT Server** deployment system with GPU acceleration and comprehensive testing harness. One-command setup for high-performance speech-to-text service on bare metal, cloud instances, or Runpod.

## ✨ What This Is

**Yap STT Service** provides:

1. 🚀 **Complete Moshi STT Server Deployment** - Automated CUDA setup, Rust compilation, server configuration
2. 📊 **Production Management** - tmux sessions, logging, status monitoring, graceful shutdown  
3. 🧪 **Comprehensive Testing Suite** - Real-time clients, load testing, benchmarks, protocol validation
4. ⚡ **GPU Optimized** - Automatic CUDA toolkit matching, optimized for L40S/A100/RTX cards
5. 🌐 **Runpod Ready** - Tested for bare-metal cloud deployments with public endpoint support

## 🚀 Quick Start (One Command)

### Complete Setup + Deployment
```bash
# Download, compile, configure, and start Moshi STT server
bash scripts/main.sh
```

**This will:**
1. Install CUDA toolkit (matching your GPU driver)
2. Install Rust toolchain and compile moshi-server
3. Clone Kyutai DSM repository and fetch configs
4. Start Moshi server in tmux session on port 8000
5. Run smoke test to verify everything works
6. Show you connection details and management commands

**After ~5-10 minutes, you'll have:**
- Moshi STT server running on `ws://0.0.0.0:8000/api/asr-streaming`
- GPU-accelerated speech recognition
- Production tmux session with logging
- Ready for client connections

## 📊 Service Management

### Check Server Status
```bash
# View tmux sessions, listening ports, recent logs
bash scripts/05_status.sh
```

### Monitor Server Logs
```bash
# Tail live server logs
tail -f /workspace/logs/moshi-server.log

# Attach to tmux session
tmux attach -t moshi-stt
```

### Stop Service
```bash
# Graceful shutdown (keeps installation)
tmux kill-session -t moshi-stt

# Complete cleanup (removes everything, ~5GB freed)
bash scripts/99_stop.sh
```

## ⚙️ Manual Step-by-Step Setup

For development or custom deployments:

```bash
# 1. Install system dependencies (CUDA, Rust, Python, ffmpeg)
bash scripts/00_prereqs.sh

# 2. Compile and install moshi-server with CUDA support
bash scripts/01_install_moshi_server.sh

# 3. Fetch Kyutai configs and STT model definitions
bash scripts/02_fetch_configs.sh

# 4. Start server in tmux session
bash scripts/03_start_server.sh

# 5. Check status and verify port binding
bash scripts/05_status.sh

# 6. Run smoke test with reference client
bash scripts/04_smoke_test.sh
```

## 🌐 Runpod Deployment

### Quick Runpod Setup
1. **Launch Instance**: Ubuntu 22.04 + L40S/A100/RTX 4090
2. **Expose Port**: `8000` in Runpod dashboard  
3. **Run Setup**:
   ```bash
   git clone https://github.com/your-repo/yap-stt-api.git
   cd yap-stt-api
   bash scripts/main.sh
   ```
4. **Connect**: Your server will be at `ws://your-runpod-ip:8000/api/asr-streaming`

### Runpod Configuration

**Environment Variables** (optional, set in `.env`):
```bash
# Server binding
MOSHI_ADDR=0.0.0.0          # Bind to all interfaces
MOSHI_PORT=8000             # Default port
MOSHI_CLIENT_HOST=127.0.0.1 # Internal health check host

# Public endpoint (if using Runpod proxy)
MOSHI_PUBLIC_WS_URL=wss://your-runpod-proxy.com

# Performance tuning
HF_HOME=/workspace/hf_cache          # Model cache location
HF_HUB_ENABLE_HF_TRANSFER=1         # Fast downloads
SMOKETEST_RTF=1000                   # Smoke test speed
```

**Resource Requirements:**
- **GPU**: L40S/A100 (recommended) or RTX 4090/3090
- **RAM**: 16GB+ (32GB recommended)  
- **Storage**: 20GB+ free space
- **Network**: Public port 8000 exposed

## 🔧 Configuration

### Server Configuration
The service uses Kyutai's official STT config (`config-stt-en_fr-hf.toml`) supporting:
- **Languages**: English + French  
- **Models**: Streaming optimized Transformer architecture
- **GPU**: CUDA acceleration with automatic mixed precision
- **WebSocket**: Native Rust server with JSON protocol

### Performance Tuning

**GPU Memory Optimization:**
```bash
# Edit config after setup
vim /workspace/moshi-stt.toml

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

## 🧪 Testing Your Deployed Server

Once your server is running, use the comprehensive test suite:

### Prerequisites for Testing
```bash
# Install Python testing dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 🖥️ Interactive Client (`test/client.py`)
**Real-time streaming client with live partial results**

```bash
# Connect to local server
python test/client.py --server localhost:8000

# Connect to Runpod server  
python test/client.py --server your-runpod-ip:8000/api/asr-streaming

# Test with specific audio file
python test/client.py --file samples/mid.wav --rtf 1.0

# Fast upload mode (no streaming delays)
python test/client.py --mode oneshot --file samples/long.mp3
```

**What you'll see:**
- Real-time `WORD:` events as speech is processed
- `PART:` partial transcripts building up
- Final transcription and timing metrics
- Connection and protocol validation

### 📊 Load Testing (`test/bench.py`)
**Performance benchmarking with concurrent streams**

```bash
# Light load test (20 sessions, 5 concurrent)
python test/bench.py --n 20 --concurrency 5

# Heavy load test (100 sessions, 20 concurrent)  
python test/bench.py --n 100 --concurrency 20

# Production server stress test
python test/bench.py --server your-runpod-ip:8000/api/asr-streaming --n 200 --concurrency 50

# Real-time vs throughput testing
python test/bench.py --rtf 1.0 --mode stream     # Real-time simulation
python test/bench.py --rtf 1000 --mode oneshot   # Max throughput
```

**Metrics you'll get:**
- **TTFW(word)**: Time to first word token (latency SLA)
- **TTFW(text)**: Time to first partial text (user experience)
- **Finalize latency**: End-of-audio to final result
- **RTF/xRT**: Real-time factor and throughput analysis  
- **P50/P95**: Percentile latency for production SLAs
- **Error rates**: Connection failures and timeouts

### 🔥 Server Warm-up (`test/warmup.py`)
**Single connection verification and cache warming**

```bash
# Quick server health check
python test/warmup.py

# Fast warm-up (primes caches for consistent benchmarks)
python test/warmup.py --rtf 1000

# Debug mode (see all server protocol messages)
python test/warmup.py --debug --server localhost:8000

# Test transcription accuracy
python test/warmup.py --file samples/mid.wav --rtf 1.0
```

### Test Audio Files
Located in `samples/`:
- `short-noisy.wav` - Quick test with background noise
- `mid.wav` - Clean medium-length speech
- `long.mp3` - Extended audio for endurance testing  
- `long-noisy.mp3` - Challenging noisy audio

## 🔌 Moshi Protocol Details

### WebSocket Protocol
Your deployed server speaks the native Moshi Rust protocol:

**Client → Server:**
```json
{"type":"StartSTT"}                                    // Handshake
{"type":"Audio","audio":"<base64_pcm_24khz_mono>"}     // Audio frames  
{"type":"Flush"}                                       // End signal
```

**Server → Client:**
```json
{"type":"Ready"}                          // Server ready
{"type":"Step"}                          // Processing step  
{"type":"Word","word":"hello"}           // Word token
{"type":"Partial","text":"hello world"} // Partial transcript
{"type":"Text","text":"hello world"}    // Updated transcript
{"type":"Final","text":"hello world"}   // Final result
```

### Audio Format Requirements
- **Sample Rate**: 24kHz (Moshi native)
- **Channels**: Mono
- **Format**: 16-bit PCM
- **Chunk Size**: 80ms (1920 samples, 3840 bytes)
- **Encoding**: Base64 encoded in JSON frames

### WebSocket Endpoint  
- **Path**: `/api/asr-streaming` (not root `/`)
- **Full URL**: `ws://host:port/api/asr-streaming`
- **SSL**: `wss://host:port/api/asr-streaming`
- **Auth**: Requires `kyutai-api-key` header (set via `MOSHI_API_KEY` env var)

### Environment Variables
```bash
# Set default server for all tests
export MOSHI_SERVER=localhost:8000/api/asr-streaming
python test/client.py  # Uses environment variable

# Set API key (defaults to "public_token" for local testing)
export MOSHI_API_KEY=your-secret-key
python test/client.py

# Both together for production testing
export MOSHI_SERVER=prod-server:8000/api/asr-streaming
export MOSHI_API_KEY=production-key
python test/bench.py --n 100 --concurrency 20
```

### Connection Settings
```python
# Optimized WebSocket settings (used by test suite)
import os
API_KEY = os.getenv("MOSHI_API_KEY", "public_token")
headers = [("kyutai-api-key", API_KEY)]

websocket_options = {
    "max_size": None,           # No frame size limit
    "compression": None,        # Disable compression  
    "ping_interval": 20,        # Keep-alive
    "ping_timeout": 20,         
    "max_queue": 4,            # Send queue limit
    "write_limit": 2**22,      # Write buffer size
    "extra_headers": headers   # API key authentication
}
```

## 🐛 Troubleshooting

### WebSocket 401/404 Errors
**Problem**: Connection refused, 401 Unauthorized, or 404 during WebSocket handshake  

**Common Causes:**
1. **Wrong path**: Connecting to root `/` instead of `/api/asr-streaming` 
2. **Missing API key**: Server expects `kyutai-api-key` header

```bash
# ❌ Wrong - will get 404
python test/client.py --server localhost:8000

# ✅ Correct - will connect successfully  
python test/client.py --server localhost:8000/api/asr-streaming

# ✅ With custom API key
export MOSHI_API_KEY=your-secret-key
python test/client.py --server localhost:8000/api/asr-streaming
```

**Solutions**: 
- Always use the full path `/api/asr-streaming` 
- Set `MOSHI_API_KEY` env var (defaults to `"public_token"` for local testing)

### Server Won't Start
```bash
# Check CUDA installation
nvidia-smi
nvcc --version

# Check dependencies
bash scripts/00_prereqs.sh

# View server logs
tail -f /workspace/logs/moshi-server.log

# Check tmux session
tmux ls
tmux attach -t moshi-stt
```

### GPU Issues
```bash
# Verify GPU detection
python -c "import torch; print(torch.cuda.is_available())"

# Check CUDA toolkit version matching
ls /usr/local/cuda-*/bin/nvcc

# Rebuild with correct CUDA
bash scripts/99_stop.sh  # Clean everything
bash scripts/main.sh     # Fresh install
```

### Connection Issues
```bash
# Check port binding
ss -tlnp | grep 8000

# Test WebSocket connectivity  
python -c "import websockets, asyncio; asyncio.run(websockets.connect('ws://localhost:8000/api/asr-streaming'))"

# Check firewall (Runpod)
# Ensure port 8000 is exposed in Runpod dashboard
```

### Performance Issues
```bash
# Monitor GPU usage during testing
nvidia-smi -l 1

# Check server resource usage
top -p $(pgrep moshi-server)

# Reduce batch size in config
vim /workspace/moshi-stt.toml
# Decrease batch_size if running out of VRAM
```

### Audio/Testing Issues  
```bash
# Install ffmpeg for audio conversion
apt-get update && apt-get install -y ffmpeg

# Test audio processing
python -c "from test.utils import file_to_pcm16_mono_24k; print('OK' if file_to_pcm16_mono_24k('samples/mid.wav') else 'ERROR')"

# Activate Python environment
source venv/bin/activate
pip install -r requirements.txt
```

## 📁 Directory Structure

```
yap-stt-api/
├── scripts/                          # Server deployment & management
│   ├── main.sh                      # One-command complete setup
│   ├── 00_prereqs.sh               # System dependencies (CUDA, Rust)
│   ├── 01_install_moshi_server.sh  # Compile moshi-server
│   ├── 02_fetch_configs.sh         # Get Kyutai configs
│   ├── 03_start_server.sh          # Start server in tmux
│   ├── 04_smoke_test.sh            # Smoke test with reference client
│   ├── 05_status.sh                # Status monitoring
│   ├── 99_stop.sh                  # Complete cleanup
│   └── env.lib.sh                  # Environment configuration
├── test/                            # Comprehensive testing suite
│   ├── client.py                   # Interactive streaming client
│   ├── bench.py                    # Load testing & benchmarks
│   ├── warmup.py                   # Server warm-up & health check
│   ├── utils.py                    # Audio processing utilities
│   └── results/                    # Test output and metrics
├── samples/                         # Test audio files
│   ├── short-noisy.wav
│   ├── mid.wav  
│   ├── long.mp3
│   └── long-noisy.mp3
├── requirements.txt                 # Python testing dependencies
└── README.md
```

## 🔧 Advanced Usage

### Custom Configuration
```bash
# Edit environment before setup
cp scripts/.env.example scripts/.env
vim scripts/.env

# Custom server settings
export MOSHI_PORT=8080
export MOSHI_ADDR=0.0.0.0
bash scripts/main.sh
```

### Multiple Servers (Load Balancing)
```bash
# Start additional servers on different ports
MOSHI_PORT=8001 TMUX_SESSION=moshi-stt-1 bash scripts/03_start_server.sh
MOSHI_PORT=8002 TMUX_SESSION=moshi-stt-2 bash scripts/03_start_server.sh

# Test round-robin load balancing
python test/bench.py --server localhost:8000 --n 30 --concurrency 10
python test/bench.py --server localhost:8001 --n 30 --concurrency 10  
python test/bench.py --server localhost:8002 --n 30 --concurrency 10
```

### Production Deployment
```bash
# Setup with production settings
export HF_HOME=/opt/hf_cache
export MOSHI_LOG_DIR=/opt/moshi-logs
export MOSHI_ADDR=0.0.0.0
bash scripts/main.sh

# Setup log rotation
echo "/opt/moshi-logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    sharedscripts
}" > /etc/logrotate.d/moshi
```

### Proxy/SSL Setup
```bash
# Behind nginx proxy
server {
    listen 443 ssl;
    server_name your-domain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Test with SSL
python test/client.py --server your-domain.com:443 --secure
```

## 🧹 Complete Removal

```bash
# Nuclear option - removes everything (~5GB freed)
bash scripts/99_stop.sh

# This removes:
# - moshi-server binary and Rust toolchain
# - Kyutai DSM repository and configs  
# - HuggingFace model cache
# - All logs and tmux sessions
# - CUDA toolkit (optional)
```

## 📄 License

MIT License - Production ready for commercial deployments.

## 🤝 Support

**For Server Issues:**
- Check server logs: `tail -f /workspace/logs/moshi-server.log`
- Verify GPU: `nvidia-smi`
- Status check: `bash scripts/05_status.sh`

**For Testing Issues:**
- Activate venv: `source venv/bin/activate`  
- Check dependencies: `pip install -r requirements.txt`
- Debug mode: `python test/warmup.py --debug`

**Performance Questions:**
- Run benchmarks: `python test/bench.py --n 100 --concurrency 20`
- Monitor GPU: `nvidia-smi -l 1` during tests
- Tune config: `/workspace/moshi-stt.toml`