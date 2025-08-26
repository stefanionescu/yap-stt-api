#!/usr/bin/env bash
set -euo pipefail
PORT="${1:-8000}"
ss -ltnp | grep ":${PORT} " || { echo "Port ${PORT} not listening"; exit 1; }
source ~/.venvs/sensevoice/bin/activate
python - <<'PY'
import os, asyncio, websockets
uri=f"ws://127.0.0.1:8000/api/realtime/ws?chunk_duration=0.1"
async def go():
    async with websockets.connect(uri, ping_interval=None, close_timeout=1) as ws:
        print("WS OK:", uri)
        await ws.close()
asyncio.run(go())
PY
