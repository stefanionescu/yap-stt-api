#!/usr/bin/env bash
set -euo pipefail

echo "🧹 Cleaning up ALL installed components..."

# Kill tmux session
echo "Stopping tmux session..."
tmux kill-session -t sensevoice 2>/dev/null || echo "  (no tmux session found)"

# Remove Python virtual environment
echo "Removing Python venv..."
rm -rf ~/.venvs/sensevoice
echo "  Removed: ~/.venvs/sensevoice"

# Remove cloned repository
echo "Removing cloned repo..."
rm -rf ~/streaming-sensevoice
echo "  Removed: ~/streaming-sensevoice"

# Remove model caches
echo "Removing model caches..."
rm -rf ~/.cache/modelscope
rm -rf ~/.cache/huggingface
rm -rf ~/.cache/torch
echo "  Removed: ModelScope, HuggingFace, and PyTorch caches"

# Remove temporary files
echo "Removing temporary files..."
rm -f /tmp/_warmup_gpu.py
rm -f /tmp/sensevoice_*
echo "  Removed: temporary files"

# Remove pip cache
echo "Removing pip cache..."
rm -rf ~/.cache/pip
echo "  Removed: pip cache"

# Remove any backup files created by AMP script
echo "Removing backup files..."
find ~/streaming-sensevoice* -name "*.bak" -delete 2>/dev/null || true
echo "  Removed: backup files"

# Check for running processes
echo "Checking for running processes..."
pkill -f "realtime_ws_server" 2>/dev/null || echo "  (no server processes found)"
pkill -f "sensevoice" 2>/dev/null || echo "  (no sensevoice processes found)"

echo ""
echo "✅ Cleanup complete! All components removed:"
echo "  • Python virtual environment (~/.venvs/sensevoice)"
echo "  • Cloned repository (~/streaming-sensevoice)" 
echo "  • Model caches (ModelScope, HuggingFace, PyTorch)"
echo "  • Tmux session (sensevoice)"
echo "  • Temporary files and pip cache"
echo "  • Running server processes"
echo ""
echo "💡 System packages installed via apt-get are left intact"
echo "   (git, python3-venv, ffmpeg, tmux, etc.)"
echo ""
