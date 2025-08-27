# Sherpa-ONNX Streaming ASR with Zipformer INT8 (Bilingual Chinese + English)

Production-ready streaming WebSocket ASR server using **sherpa-onnx** with **INT8 quantized Zipformer** model for **bilingual Chinese + English** recognition. Optimized for high-concurrency deployments with **~100 concurrent streams** on a single L40S GPU.

## ✨ Features

- 🎯 **Bilingual ASR**: Chinese + English streaming recognition
- ⚡ **INT8 Quantization**: Faster inference with INT8 encoder/joiner
- 🌐 **WebSocket Streaming**: Real-time audio processing with micro-batching
- 🔥 **High Concurrency**: ~100 concurrent streams on L40S/A100
- 📦 **Multiple Deployment Options**: Single worker, multi-worker, or NGINX gateway
- 🏗️ **Production Ready**: systemd services, tmux sessions, complete cleanup
- 🚀 **Runpod Optimized**: Tested and documented for Runpod bare-metal instances

## 🚀 Quick Start

### One-Command Setup (Recommended)
```bash
# Complete automated setup + deployment
bash scripts/00_full_setup_and_run.sh
```

This will:
1. Build sherpa-onnx with GPU support
2. Download INT8 bilingual model (~5GB)
3. Optimize OS for high concurrency
4. Give you deployment options

### Manual Setup
```bash
# 1. Build sherpa-onnx
bash scripts/01_setup_sherpa_onnx.sh

# 2. Download model
bash scripts/02_get_model_zh_en_int8.sh

# 3. Optimize system
bash scripts/06_sysctl_ulimit.sh

# 4. Choose deployment method (see below)
```

## 📊 Deployment Options

### 🎯 Option A: Multi-Worker + NGINX Gateway (RECOMMENDED)
**Best for production - single public port with automatic load balancing**

```bash
# Start 3 workers + NGINX gateway
bash scripts/04_run_server_multi_int8.sh &
bash scripts/07_setup_nginx_gateway.sh
```

**Configuration:**
- **Public port**: `8000` (NGINX gateway)
- **Backend workers**: `8001`, `8002`, `8003` (internal)
- **Client connects to**: `ws://your-server:8000`
- **Load balancing**: Automatic via NGINX
- **Capacity**: ~100 concurrent streams

### ⚡ Option B: Multi-Worker Direct (NO NGINX)
**Multiple public ports - client-side load balancing**

```bash
# Start 3 workers on ports 8000-8002
WORKERS=3 BASE_PORT=8000 bash scripts/04_run_server_multi_int8.sh
```

**Configuration:**
- **Public ports**: `8000`, `8001`, `8002`
- **Client connects to**: Round-robin `[8000,8001,8002]` in your code
- **Load balancing**: Client-side (e.g., `port = 8000 + (sessionId % 3)`)
- **Capacity**: ~100 concurrent streams

### 🔧 Option C: Single Worker (SIMPLE)
**Single port - for testing or lower concurrency**

```bash
# Start single worker
bash scripts/03_run_server_single_int8.sh
```

**Configuration:**
- **Public port**: `8000`
- **Client connects to**: `ws://your-server:8000`
- **Capacity**: ~30-50 concurrent streams

## 🎮 Server Management

### Interactive Deployment Chooser
```bash
# Guided menu for deployment options
bash scripts/08_deployment_chooser.sh
```

### Health Check
```bash
# Verify all servers and services are working
bash scripts/09_health_check.sh
```

### Starting Servers

#### tmux Sessions (Survives SSH Disconnect)
```bash
# Single worker in tmux
SESSION=sherpa SCRIPT=03_run_server_single_int8.sh bash scripts/05_tmux.sh

# Multi-worker in tmux
SESSION=sherpa-multi SCRIPT=04_run_server_multi_int8.sh bash scripts/05_tmux.sh

# Attach to session
tmux attach -t sherpa
```

#### systemd Services (Production)
```bash
# Single worker service
cp scripts/sherpa-asr.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sherpa-asr.service

# Multi-worker service
cp scripts/sherpa-asr-multi.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sherpa-asr-multi.service
# Then: bash scripts/07_setup_nginx_gateway.sh
```

### Stopping Servers

#### Kill Processes
```bash
# Stop all sherpa processes
pkill -f "sherpa-onnx"

# Stop specific services
systemctl stop sherpa-asr
systemctl stop sherpa-asr-multi
```

#### Complete Cleanup (Nuclear Option)
```bash
# Remove EVERYTHING (models, deps, configs, logs)
# ⚠️ WARNING: This removes ~7GB+ data
bash scripts/99_cleanup_services.sh
# Type "YES" to confirm
```

## 🌐 Runpod Deployment

### Quick Start for Most Users (Production Ready)
1. **Launch Instance**: Ubuntu 22.04 + L40S/A100
2. **Expose Port**: `8000` only
3. **Run Setup**: 
   ```bash
   bash scripts/00_full_setup_and_run.sh
   # Choose "A" for NGINX setup
   ```
4. **Connect Clients**: `ws://your-runpod-ip:8000`

### Advanced Users (Direct Multi-Worker)
1. **Launch Instance**: Ubuntu 22.04 + L40S/A100
2. **Expose Ports**: `8000,8001,8002`
3. **Run Setup**:
   ```bash
   WORKERS=3 BASE_PORT=8000 bash scripts/04_run_server_multi_int8.sh
   ```
4. **Client Load Balancing**: Round-robin ports `[8000,8001,8002]`

### Runpod-Specific Notes
- **Root access**: No `sudo` needed (you're already root in Runpod)
- **Systemd**: Works on bare-metal instances
- **Docker containers**: Use tmux option if systemd unavailable
- **Persistence**: Save as Runpod template after setup
- **Port exposure**: Configure in Runpod dashboard before starting
- **All commands**: Run directly without `sudo` prefix

## ⚙️ Configuration & Performance

### Model Details
- **Model**: Bilingual Chinese + English Streaming Zipformer
- **Quantization**: INT8 encoder/joiner, FP32 decoder
- **Size**: ~5GB download
- **Endpointing**: Optimized for 120-150ms finalization

### Performance Tuning
```bash
# Key parameters in server scripts:
--max-batch-size=24        # Batch size (16-32 for tuning)
--loop-interval-ms=10      # Processing loop interval
--rule1-min-trailing-silence=0.12  # Endpointing (adjust for language)
--rule2-min-trailing-silence=0.15
```

### Capacity Guidelines
- **L40S/A100**: ~100 concurrent streams
- **RTX 4090**: ~50-70 concurrent streams
- **Memory**: 32GB+ recommended for multi-worker
- **Storage**: 100GB+ for models and logs

## 🛠️ Directory Structure

```
yap-stt-api/
├── scripts/
│   ├── 00_full_setup_and_run.sh        # Main orchestrator
│   ├── 01_setup_sherpa_onnx.sh         # Build sherpa-onnx
│   ├── 02_get_model_zh_en_int8.sh      # Download model
│   ├── 03_run_server_single_int8.sh    # Single worker
│   ├── 04_run_server_multi_int8.sh     # Multi-worker
│   ├── 05_tmux.sh                      # tmux management
│   ├── 06_sysctl_ulimit.sh             # OS optimization
│   ├── 07_setup_nginx_gateway.sh       # NGINX gateway
│   ├── 08_deployment_chooser.sh        # Interactive chooser
│   ├── 09_health_check.sh              # Health check & diagnostics
│   ├── 10_debug_workers.sh             # Worker startup troubleshooting
│   ├── 99_cleanup_services.sh          # Complete cleanup
│   ├── sherpa-asr.service              # Single worker systemd
│   └── sherpa-asr-multi.service        # Multi-worker systemd
├── samples/                            # Test audio files
├── test/                              # Testing utilities
└── requirements.txt
```

## 🐛 Troubleshooting

### Common Issues
- **Port conflicts**: Use `99_cleanup_services.sh` to reset
- **GPU not detected**: Verify with `nvidia-smi`
- **systemd fails**: Fall back to tmux sessions
- **High P99 latency**: Increase endpointing rules or reduce batch size
- **Server not responding**: Run `09_health_check.sh` for diagnostics
- **Workers fail to start**: Run `10_debug_workers.sh` for detailed troubleshooting

### Monitoring
```bash
# Complete health check (processes, ports, connections, logs)
bash scripts/09_health_check.sh

# Debug worker startup issues (system resources, model files, detailed logs)
bash scripts/10_debug_workers.sh

# Check server logs
tail -f /opt/sherpa-logs/server*.log

# Check system status
systemctl status sherpa-asr-multi
ss -lntp | grep 800  # Check listening ports

# Monitor GPU usage
nvidia-smi -l 1
```

### Performance Tips
- Use **Option A (NGINX)** for production workloads
- Tune `--max-batch-size` based on latency requirements
- For Mandarin fast speech, increase endpointing to 0.18-0.22s
- Monitor GPU memory - scale workers based on VRAM usage

## 📚 Client Integration

### WebSocket Connection
```python
# Connect to single endpoint (NGINX setup)
ws = websocket.create_connection("ws://your-server:8000")

# Or round-robin for direct multi-worker
ports = [8000, 8001, 8002]
port = ports[session_id % len(ports)]
ws = websocket.create_connection(f"ws://your-server:{port}")
```

### Audio Format
- **Sample rate**: 16 kHz
- **Channels**: Mono
- **Format**: 16-bit PCM
- **Chunk size**: 120-160ms recommended

## 🧪 Testing Your Server

Use the included test utilities to verify your Sherpa-ONNX server is working correctly:

### Prerequisites
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# When done testing, deactivate virtual environment
deactivate
```

### 1. Quick Test Client (`test/client.py`)
**Interactive streaming client - shows real-time partial results**
```bash
# Basic test with default settings
python test/client.py

# Test specific audio file with custom chunk size
python test/client.py --file short-noisy.wav --chunk-ms 120

# Test against remote server
python test/client.py --server your-runpod-ip:8000

# One-shot mode (no streaming simulation)  
python test/client.py --mode oneshot --file mid.wav
```

### 2. Server Warmup (`test/warmup.py`)
**Single connection test - good for initial server verification**
```bash
# Basic warmup test
python test/warmup.py

# Test different audio files
python test/warmup.py --file long.mp3 --chunk-ms 100

# Test against multi-worker setup
python test/warmup.py --server localhost:8001  # Direct worker connection
python test/warmup.py --server localhost:8000  # Via NGINX gateway
```

### 3. Load Testing (`test/bench.py`)
**Performance benchmarking - concurrent streams and metrics**
```bash
# Light load test (5 concurrent streams, 10 total)
python test/bench.py --n 10 --concurrency 5

# Heavy load test (20 concurrent streams, 100 total)
python test/bench.py --n 100 --concurrency 20 --file mid.wav

# Performance test against production server
python test/bench.py --server your-runpod-ip:8000 --n 50 --concurrency 10

# One-shot performance (no streaming delays)
python test/bench.py --mode oneshot --n 20 --concurrency 5
```

### Available Test Options

**Common Flags (all test files):**
- `--server`: Server address (`localhost:8000`, `your-ip:8000`)
- `--file`: Audio file from `samples/` directory (`mid.wav`, `short-noisy.wav`, `long.mp3`)  
- `--chunk-ms`: Audio chunk size in milliseconds (default: 100ms)
- `--mode`: `stream` (realtime simulation) or `oneshot` (fast upload)
- `--secure`: Use WSS instead of WS (requires SSL setup)

**Benchmark-Specific Flags (`bench.py`):**
- `--n`: Total number of test sessions (default: 20)
- `--concurrency`: Max concurrent sessions (default: 5)

**Environment Variables:**
```bash
# Set default server for all tests (within activated venv)
source venv/bin/activate
export SHERPA_SERVER=your-runpod-ip:8000
python test/client.py  # Will use the environment variable
```

### 🔍 Troubleshooting Tests

**Connection Refused:**
```bash
# Check server status
bash scripts/09_health_check.sh

# Check if server is listening  
ss -tlnp | grep 8000
```

**Import Errors:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# If still failing, reinstall dependencies
pip install -r requirements.txt
```

**No Audio Files:**
```bash
# Check available test files
ls -la samples/
```

## 📄 License

See LICENSE file for details.
