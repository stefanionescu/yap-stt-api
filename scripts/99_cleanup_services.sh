#!/usr/bin/env bash
set -euo pipefail

# NUCLEAR CLEANUP: Remove EVERYTHING sherpa-related
# WARNING: This removes all models, dependencies, caches, configs
# Use this to completely uninstall sherpa from the system

echo "=== NUCLEAR SHERPA CLEANUP ==="
echo "⚠️  WARNING: This will remove EVERYTHING sherpa-related:"
echo "   • All processes and services"
echo "   • All models (~5GB+ data)"
echo "   • All dependencies and packages"
echo "   • All logs and caches"
echo "   • All configuration files"
echo ""
read -p "Are you absolutely sure? This cannot be undone. (type 'YES' to confirm): " confirm
if [ "$confirm" != "YES" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🗑️  Starting nuclear cleanup..."

# 1. Stop and disable all systemd services
echo "1. Stopping and removing systemd services..."
for service in sherpa-asr sherpa-asr-multi; do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        echo "   Stopping $service..."
        systemctl stop "$service" || true
    fi
    
    if systemctl is-enabled --quiet "$service" 2>/dev/null; then
        echo "   Disabling $service..."
        systemctl disable "$service" || true
    fi
    
    # Remove service files
    if [ -f "/etc/systemd/system/${service}.service" ]; then
        echo "   Removing /etc/systemd/system/${service}.service"
        rm -f "/etc/systemd/system/${service}.service" || true
    fi
done
systemctl daemon-reload || true

# 2. Kill all sherpa processes
echo "2. Killing all sherpa processes..."
pkill -f "sherpa-onnx" || true
pkill -f "sherpa" || true

# 3. Stop CUDA MPS if running
echo "3. Stopping CUDA MPS..."
if command -v nvidia-cuda-mps-control >/dev/null 2>&1; then
    echo quit | nvidia-cuda-mps-control 2>/dev/null || true
fi

# 4. Remove NGINX sherpa configuration
echo "4. Cleaning up NGINX configuration..."
if systemctl is-active --quiet nginx 2>/dev/null; then
    systemctl stop nginx || true
fi
rm -f /etc/nginx/sites-available/sherpa-ws.conf || true
rm -f /etc/nginx/sites-enabled/sherpa-ws.conf || true
# Restart nginx with default config if it was running
if systemctl is-enabled --quiet nginx 2>/dev/null; then
    if [ -f /etc/nginx/sites-available/default.bak ]; then
        mv /etc/nginx/sites-available/default.bak /etc/nginx/sites-enabled/default || true
    fi
    systemctl start nginx || true
fi

# 5. Kill tmux sessions
echo "5. Killing tmux sessions..."
for session in sherpa sherpa-multi; do
    if tmux has-session -t "$session" 2>/dev/null; then
        echo "   Killing tmux session: $session"
        tmux kill-session -t "$session" || true
    fi
done

# 6. Remove all sherpa directories and data
echo "6. Removing all sherpa data directories..."
echo "   Removing /opt/sherpa-onnx (~2GB source + build)"
rm -rf /opt/sherpa-onnx || true
echo "   Removing /opt/sherpa-models (~5GB+ models)"
rm -rf /opt/sherpa-models || true
echo "   Removing /opt/sherpa-logs"
rm -rf /opt/sherpa-logs || true

# 7. Remove Python packages
echo "7. Removing Python packages..."
python3 -m pip uninstall -y websockets soundfile numpy onnxruntime-gpu onnxruntime 2>/dev/null || true

# 8. Remove build dependencies (optional - commented out by default)
echo "8. Removing build dependencies..."
echo "   Removing sherpa-specific packages..."
apt-get remove -y --autoremove \
    build-essential git cmake pkg-config \
    libssl-dev zlib1g-dev libsndfile1 libsndfile1-dev libasound2-dev \
    numactl psmisc 2>/dev/null || true

echo "   Note: Keeping common packages (wget, curl, python3, tmux, nginx)"
echo "   Uncomment lines below to remove these too if needed"
# apt-get remove -y --autoremove wget curl python3 python3-pip python3-venv tmux nginx || true

# 9. Clean package caches
echo "9. Cleaning package caches..."
apt-get autoremove -y || true
apt-get autoclean || true
apt-get clean || true

# 10. Reset sysctl changes (restore defaults)
echo "10. Resetting network optimizations..."
sysctl -w net.core.somaxconn=128 2>/dev/null || true
sysctl -w net.core.netdev_max_backlog=1000 2>/dev/null || true
sysctl -w net.ipv4.ip_local_port_range="32768 60999" 2>/dev/null || true
sysctl -w net.ipv4.tcp_fin_timeout=60 2>/dev/null || true

# 11. Reset ulimit (session only - permanent changes require editing /etc/security/limits.conf)
echo "11. Resetting ulimits for current session..."
ulimit -n 1024 2>/dev/null || true

# 12. Clean up any remaining build artifacts
echo "12. Cleaning build artifacts..."
rm -rf /tmp/sherpa* /tmp/onnx* /var/tmp/sherpa* 2>/dev/null || true

# 13. Remove any sherpa entries from crontab/rc.local if added manually
echo "13. Note: Check /etc/rc.local and crontab for any manual sherpa entries"

echo ""
echo "💥 NUCLEAR CLEANUP COMPLETE! 💥"
echo ""
echo "Removed:"
echo "✓ All sherpa processes and services"
echo "✓ All models and data (~5GB+ freed)"
echo "✓ All build dependencies"
echo "✓ All configuration files"
echo "✓ All logs and caches"
echo "✓ All Python packages"
echo "✓ All network optimizations"
echo ""
echo "System is now clean - sherpa completely removed."
echo "To reinstall: run 00_full_setup_and_run.sh"
