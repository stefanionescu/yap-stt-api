# Runpod Deployment Notes

## ✅ What Works
- All scripts work on Runpod bare-metal instances
- Ubuntu 22.04/24.04 with NVIDIA drivers pre-installed
- Standard ports (8000-8003) work fine
- File paths (/opt/) work as expected

## ⚠️ Runpod-Specific Setup

### 1. Port Exposure
In Runpod, you need to **expose ports**:
- **Single worker**: Expose port `8000`
- **Multi-worker + NGINX**: Expose port `8000` only (NGINX handles internal routing)
- **Multi-worker direct**: Expose ports `8000,8001,8002` if no NGINX

### 2. Systemd Services
- **Bare-metal Runpod**: systemd works fine
- **Docker containers**: systemd may not be available
  - Use **tmux** option instead: `bash 05_tmux.sh`

### 3. Deployment Options: With or Without NGINX

Choose your preferred deployment strategy:

#### 🎯 **Option A: Multi-Worker + NGINX Gateway (RECOMMENDED)**
**Best for production - single public port with automatic load balancing**

```bash
# Automated setup
sudo bash 00_full_setup_and_run.sh
# Choose "Y" when prompted for NGINX setup

# Manual setup
sudo bash 04_run_server_multi_int8.sh &  # Starts workers on 8001-8003
sudo bash 07_setup_nginx_gateway.sh      # NGINX on 8000 → round-robin to workers
```

**Runpod Configuration:**
- Expose port: `8000` only
- Client connects to: `ws://your-runpod-ip:8000`
- NGINX automatically distributes to 3 backend workers
- Perfect for ~100 concurrent streams

#### ⚡ **Option B: Multi-Worker Direct (NO NGINX)**  
**Simpler setup - multiple public ports, client-side load balancing**

```bash
# Automated setup
sudo bash 00_full_setup_and_run.sh
# Choose "n" when prompted, then manually start multi-worker

# Manual setup
WORKERS=3 BASE_PORT=8000 bash 04_run_server_multi_int8.sh  # Workers on 8000-8002
```

**Runpod Configuration:**
- Expose ports: `8000,8001,8002`
- Client connects to: Pick random from `[8000,8001,8002]` or round-robin
- Good for ~100 concurrent streams
- Less infrastructure but more client complexity

#### 🔧 **Option C: Single Worker (SIMPLE)**
**Quick testing or lower concurrency needs**

```bash
sudo bash 03_run_server_single_int8.sh
```

**Runpod Configuration:**
- Expose port: `8000`
- Client connects to: `ws://your-runpod-ip:8000`
- Good for ~30-50 concurrent streams

### 4. Persistence
- **Templates**: Save a Runpod template after setup
- **Auto-start**: Add to `/etc/rc.local` if systemd unavailable:
  ```bash
  echo '#!/bin/bash' > /etc/rc.local
  echo 'cd /opt && bash 04_run_server_multi_int8.sh &' >> /etc/rc.local
  echo 'sleep 10 && bash 07_setup_nginx_gateway.sh &' >> /etc/rc.local
  chmod +x /etc/rc.local
  ```

### 5. Resource Recommendations
- **L40S/A100**: Perfect for ~100 concurrent streams
- **RTX 4090**: Good for ~50-70 streams
- **Memory**: 32GB+ recommended for multiple workers
- **Storage**: 100GB+ for models and logs

## 🚀 Quick Start Recommendations

### For Most Users (Production Ready):
1. Launch Ubuntu 22.04 + L40S instance
2. **Expose port: `8000` only**
3. Run: `sudo bash 00_full_setup_and_run.sh`
4. Choose **"Y"** for NGINX setup
5. Connect clients to: `ws://your-runpod-ip:8000`

### For Advanced Users (Direct Multi-Worker):
1. Launch Ubuntu 22.04 + L40S instance  
2. **Expose ports: `8000,8001,8002`**
3. Run: `WORKERS=3 BASE_PORT=8000 bash 04_run_server_multi_int8.sh`
4. Round-robin clients across the 3 ports in your client code

## Troubleshooting
- If systemd fails: Use tmux option
- If ports don't work: Check Runpod port exposure settings
- If GPU not detected: Run `nvidia-smi` to verify drivers
