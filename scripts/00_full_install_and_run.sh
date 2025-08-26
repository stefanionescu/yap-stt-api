#!/usr/bin/env bash
set -euo pipefail

bash ./10_bootstrap_system.sh
bash ./20_python_venv.sh
bash ./30_install_torch.sh
bash ./40_clone_and_requirements.sh
bash ./45_assert_cuda_ok.sh
bash ./50_model_warmup.sh         # GPU warmup only (cuda:0)
bash ./55_optional_enable_amp.sh  # optional; safe to skip
bash ./60_run_server_tmux.sh

echo
echo "WS URL:"
echo "  ws://<PUBLIC_HOST>:8000/api/realtime/ws?chunk_duration=0.1&vad_threshold=0.5&vad_min_silence_duration_ms=550"
echo "Logs: tmux attach -t sensevoice"

