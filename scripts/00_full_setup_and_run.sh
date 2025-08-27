#!/usr/bin/env bash
set -euo pipefail

# Full setup and run script for Sherpa-ONNX with Zipformer INT8 model
# This script orchestrates the complete setup process

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/opt/sherpa-logs/setup.log"
mkdir -p /opt/sherpa-logs

echo "=== Sherpa-ONNX Zipformer INT8 Setup ===" | tee -a "$LOG_FILE"
echo "Started at: $(date)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Step 1: Build sherpa-onnx with GPU + WebSocket support
echo "Step 1: Building sherpa-onnx with GPU + WebSocket support..." | tee -a "$LOG_FILE"
if bash "$SCRIPT_DIR/01_setup_sherpa_onnx.sh" 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ sherpa-onnx build completed successfully" | tee -a "$LOG_FILE"
else
    echo "✗ sherpa-onnx build failed" | tee -a "$LOG_FILE"
    exit 1
fi
echo "" | tee -a "$LOG_FILE"

# Step 2: Download INT8 bilingual zh/en model
echo "Step 2: Downloading INT8 bilingual zh/en model..." | tee -a "$LOG_FILE"
if bash "$SCRIPT_DIR/02_get_model_zh_en_int8.sh" 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Model download completed successfully" | tee -a "$LOG_FILE"
else
    echo "✗ Model download failed" | tee -a "$LOG_FILE"
    exit 1
fi
echo "" | tee -a "$LOG_FILE"

# Step 3: Optional offline test to verify everything works
echo "Step 3: Running offline INT8 smoke test..." | tee -a "$LOG_FILE"
if /opt/sherpa-onnx/build/bin/sherpa-onnx \
  --tokens=/opt/sherpa-models/zh-en-zipformer-2023-02-20/tokens.txt \
  --encoder=/opt/sherpa-models/zh-en-zipformer-2023-02-20/encoder-epoch-99-avg-1.int8.onnx \
  --decoder=/opt/sherpa-models/zh-en-zipformer-2023-02-20/decoder-epoch-99-avg-1.onnx \
  --joiner=/opt/sherpa-models/zh-en-zipformer-2023-02-20/joiner-epoch-99-avg-1.int8.onnx \
  /opt/sherpa-models/zh-en-zipformer-2023-02-20/test_wavs/4.wav 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Offline smoke test completed successfully" | tee -a "$LOG_FILE"
else
    echo "✗ Offline smoke test failed" | tee -a "$LOG_FILE"
    exit 1
fi
echo "" | tee -a "$LOG_FILE"

# Step 4: Optimize OS limits for high-concurrency (optional but recommended)
echo "Step 4: Optimizing OS limits for high-concurrency streaming..." | tee -a "$LOG_FILE"
if bash "$SCRIPT_DIR/06_sysctl_ulimit.sh" 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ OS optimization completed successfully" | tee -a "$LOG_FILE"
else
    echo "⚠ OS optimization had issues (may need sudo)" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Step 5: Choose server mode
echo "Setup completed successfully!" | tee -a "$LOG_FILE"
echo "Completed at: $(date)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

echo "=== Next Steps ===" | tee -a "$LOG_FILE"
echo "Choose how to run the server:" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Option 1 - Single worker (simple, port 8000):" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/03_run_server_single_int8.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Option 2 - Multi-worker (RECOMMENDED for 100+ streams, ports 8000-8002):" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/04_run_server_multi_int8.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Option 3 - Run in tmux session:" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/05_tmux.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Option 4 - Install as systemd service:" | tee -a "$LOG_FILE"
echo "  sudo cp $SCRIPT_DIR/sherpa-asr.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now sherpa-asr.service"
echo "" | tee -a "$LOG_FILE"
echo "Option 5 - Load test (120 concurrent clients):" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/07_load_test_120_clients.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Prompt user for immediate action
read -p "Would you like to start the multi-worker server now? (Y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Setup complete. Use one of the options above to start the server." | tee -a "$LOG_FILE"
else
    echo "Starting multi-worker server (recommended for high concurrency)..." | tee -a "$LOG_FILE"
    exec bash "$SCRIPT_DIR/04_run_server_multi_int8.sh"
fi
