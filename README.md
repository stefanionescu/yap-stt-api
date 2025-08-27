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
sudo bash scripts/00_full_setup_and_run.sh
```

This will:
1. Build sherpa-onnx with GPU support
2. Download INT8 bilingual model (~5GB)
3. Optimize OS for high concurrency
4. Give you deployment options

### Manual Setup
```bash
# 1. Build sherpa-onnx
sudo bash scripts/01_setup_sherpa_onnx.sh

# 2. Download model
sudo bash scripts/02_get_model_zh_en_int8.sh

# 3. Optimize system
sudo bash scripts/06_sysctl_ulimit.sh

# 4. Choose deployment method (see below)
```

## 📊 Deployment Options

### 🎯 Option A: Multi-Worker + NGINX Gateway (RECOMMENDED)
**Best for production - single public port with automatic load balancing**

```bash
# Start 3 workers + NGINX gateway
sudo bash scripts/04_run_server_multi_int8.sh &
sudo bash scripts/07_setup_nginx_gateway.sh
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
sudo bash scripts/03_run_server_single_int8.sh
```

**Configuration:**
- **Public port**: `8000`
- **Client connects to**: `ws://your-server:8000`
- **Capacity**: ~30-50 concurrent streams

## 🎮 Server Management

### Interactive Deployment Chooser
```bash
# Guided menu for deployment options
sudo bash scripts/08_deployment_chooser.sh
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
sudo cp scripts/sherpa-asr.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sherpa-asr.service

# Multi-worker service
sudo cp scripts/sherpa-asr-multi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sherpa-asr-multi.service
# Then: sudo bash scripts/07_setup_nginx_gateway.sh
```

### Stopping Servers

#### Kill Processes
```bash
# Stop all sherpa processes
sudo pkill -f "sherpa-onnx"

# Stop specific services
sudo systemctl stop sherpa-asr
sudo systemctl stop sherpa-asr-multi
```

#### Complete Cleanup (Nuclear Option)
```bash
# Remove EVERYTHING (models, deps, configs, logs)
# ⚠️ WARNING: This removes ~7GB+ data
sudo bash scripts/99_cleanup_services.sh
# Type "YES" to confirm
```

## 🌐 Runpod Deployment

### Quick Start for Most Users (Production Ready)
1. **Launch Instance**: Ubuntu 22.04 + L40S/A100
2. **Expose Port**: `8000` only
3. **Run Setup**: 
   ```bash
   sudo bash scripts/00_full_setup_and_run.sh
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
- **Systemd**: Works on bare-metal instances
- **Docker containers**: Use tmux option if systemd unavailable
- **Persistence**: Save as Runpod template after setup
- **Port exposure**: Configure in Runpod dashboard before starting

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

### Monitoring
```bash
# Check server logs
tail -f /opt/sherpa-logs/server*.log

# Check system status
sudo systemctl status sherpa-asr-multi
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

## 📄 License

See LICENSE file for details.
