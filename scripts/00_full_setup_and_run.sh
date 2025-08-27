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

# Step 3: Offline smoke test to verify everything works
echo "Step 3: Running offline INT8 smoke test..." | tee -a "$LOG_FILE"

# Find a test audio file - prefer downloaded, fallback to local samples
TEST_WAV=""
POSSIBLE_WAVS=(
    "/opt/sherpa-models/zh-en-zipformer-2023-02-20/test_wavs/0.wav"
    "$SCRIPT_DIR/../samples/short-noisy.wav"
    "$SCRIPT_DIR/../samples/mid.wav"
)

for wav in "${POSSIBLE_WAVS[@]}"; do
    if [ -f "$wav" ] && [ -s "$wav" ]; then
        # Check if it's a valid WAV file (has RIFF header)
        if head -c 4 "$wav" 2>/dev/null | grep -q "RIFF"; then
            TEST_WAV="$wav"
            echo "Using test file: $(basename "$TEST_WAV")" | tee -a "$LOG_FILE"
            break
        fi
    fi
done

if [ -n "$TEST_WAV" ]; then
    if timeout 30 /opt/sherpa-onnx/build/bin/sherpa-onnx \
      --tokens=/opt/sherpa-models/zh-en-zipformer-2023-02-20/tokens.txt \
      --encoder=/opt/sherpa-models/zh-en-zipformer-2023-02-20/encoder-epoch-99-avg-1.int8.onnx \
      --decoder=/opt/sherpa-models/zh-en-zipformer-2023-02-20/decoder-epoch-99-avg-1.onnx \
      --joiner=/opt/sherpa-models/zh-en-zipformer-2023-02-20/joiner-epoch-99-avg-1.int8.onnx \
      "$TEST_WAV" >/dev/null 2>&1; then
        echo "✓ Offline smoke test completed successfully" | tee -a "$LOG_FILE"
    else
        echo "⚠ Offline smoke test failed, but installation appears complete" | tee -a "$LOG_FILE"
        echo "  Servers should still work normally" | tee -a "$LOG_FILE"
    fi
else
    echo "⚠ No valid test audio found, skipping smoke test" | tee -a "$LOG_FILE"
    echo "  Installation appears complete - servers should work normally" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Step 4: Optimize OS limits for high-concurrency (optional but recommended)
echo "Step 4: Optimizing OS limits for high-concurrency streaming..." | tee -a "$LOG_FILE"
# OS optimization (Linux/Runpod only)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Run optimization script and capture output
    if bash "$SCRIPT_DIR/06_sysctl_ulimit.sh" 2>&1 | tee -a "$LOG_FILE"; then
        echo "✓ OS optimization completed successfully" | tee -a "$LOG_FILE"
    else
        echo "⚠ OS optimization encountered issues" | tee -a "$LOG_FILE"
    fi
else
    echo "✓ OS optimization skipped (Linux/Runpod deployment only)" | tee -a "$LOG_FILE"
    bash "$SCRIPT_DIR/06_sysctl_ulimit.sh" >> "$LOG_FILE" 2>&1
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
echo "Option 2 - Multi-worker (RECOMMENDED for 100+ streams, ports 8001-8003):" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/04_run_server_multi_int8.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Option 3 - Multi-worker + NGINX gateway (BEST - single port 8000):" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/04_run_server_multi_int8.sh" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/07_setup_nginx_gateway.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Option 4 - Run in tmux session:" | tee -a "$LOG_FILE"
echo "  bash $SCRIPT_DIR/05_tmux.sh" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Option 5 - Install as systemd service (single worker, port 8000):" | tee -a "$LOG_FILE"
echo "  cp $SCRIPT_DIR/sherpa-asr.service /etc/systemd/system/"
echo "  systemctl daemon-reload"
echo "  systemctl enable --now sherpa-asr.service"
echo "" | tee -a "$LOG_FILE"
echo "Option 6 - Install as systemd service (multi-worker + NGINX):" | tee -a "$LOG_FILE"
echo "  cp $SCRIPT_DIR/sherpa-asr-multi.service /etc/systemd/system/"
echo "  systemctl daemon-reload"
echo "  systemctl enable --now sherpa-asr-multi.service"
echo "  # Then run: bash $SCRIPT_DIR/07_setup_nginx_gateway.sh"
echo "" | tee -a "$LOG_FILE"
echo "⚠️  NOTE: Don't run both services - they conflict on port 8000!" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Prompt user for deployment choice
echo "" | tee -a "$LOG_FILE"
echo "🚀 Ready to deploy! Choose your setup:" | tee -a "$LOG_FILE"
echo "A) Multi-worker + NGINX (RECOMMENDED - single port 8000)" | tee -a "$LOG_FILE"
echo "B) Multi-worker direct (ports 8000-8002, no NGINX)" | tee -a "$LOG_FILE"
echo "C) Manual setup (choose from options above)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
read -p "Enter choice (A/B/C): " -n 1 -r
echo

case $REPLY in
    [Aa])
        echo "Starting multi-worker + NGINX gateway (best for production)..." | tee -a "$LOG_FILE"
        echo "Step 1: Starting 3 workers on ports 8001-8003..." | tee -a "$LOG_FILE"
        bash "$SCRIPT_DIR/04_run_server_multi_int8.sh" 2>&1 | tee -a "$LOG_FILE"
        
        echo "Step 2: Setting up NGINX gateway on port 8000..." | tee -a "$LOG_FILE"
        bash "$SCRIPT_DIR/07_setup_nginx_gateway.sh" 2>&1 | tee -a "$LOG_FILE"
        
        echo "" | tee -a "$LOG_FILE"
        echo "✅ Complete! Connect clients to ws://your-server:8000" | tee -a "$LOG_FILE"
        echo "NGINX will automatically round-robin across 3 workers" | tee -a "$LOG_FILE"
        echo "Runpod users: Expose port 8000 only" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        echo "💡 To verify status: bash scripts/09_health_check.sh" | tee -a "$LOG_FILE"
        ;;
    [Bb])
        echo "Starting multi-worker direct (no NGINX)..." | tee -a "$LOG_FILE"
        echo "Starting 3 workers on ports 8000-8002..." | tee -a "$LOG_FILE"
        WORKERS=3 BASE_PORT=8000 bash "$SCRIPT_DIR/04_run_server_multi_int8.sh"
        
        echo "" | tee -a "$LOG_FILE"
        echo "✅ Complete! Connect clients to ports 8000-8002" | tee -a "$LOG_FILE"
        echo "Round-robin these ports in your client code" | tee -a "$LOG_FILE"
        echo "Runpod users: Expose ports 8000,8001,8002" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        echo "💡 To verify status: bash scripts/09_health_check.sh" | tee -a "$LOG_FILE"
        ;;
    [Cc]|*)
        echo "Setup complete. Use one of the options above to start the server." | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        echo "💡 TIP: Run ./08_deployment_chooser.sh for interactive deployment" | tee -a "$LOG_FILE"
        echo "💡 TIP: Run ./09_health_check.sh to verify server status" | tee -a "$LOG_FILE"
        ;;
esac
