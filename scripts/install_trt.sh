#!/usr/bin/env bash
set -euo pipefail

echo "[TRT] Installing TensorRT via Python wheel (CUDA 12.x)..."
python3 -m pip install --upgrade pip wheel
python3 -m pip install "tensorrt-cu12"
# Optional cuDNN wheel (runtime only); ignore failures if not needed
python3 -m pip install "nvidia-cudnn-cu12>=9.1" || true

TRT_LIB_DIR=$(python3 - <<'PY'
import os, glob, sysconfig

def find_trt_lib_dir():
    # 1) Scan site-packages roots recursively (handles tensorrt_cu12_libs layout)
    paths = sysconfig.get_paths()
    roots = [p for k,p in paths.items() if k in ("purelib","platlib") and p]
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", "libnvinfer.so*"), recursive=True)
        if hits:
            return os.path.dirname(hits[0])
    # 2) Try under tensorrt package as a fallback
    try:
        import tensorrt
        base = os.path.dirname(tensorrt.__file__)
        for sub in ("lib", ".", ".."):
            cand = os.path.abspath(os.path.join(base, sub))
            hits = glob.glob(os.path.join(cand, "libnvinfer.so*"))
            if hits:
                return os.path.dirname(hits[0])
        hits = glob.glob(os.path.join(base, "**", "libnvinfer.so*"), recursive=True)
        if hits:
            return os.path.dirname(hits[0])
    except Exception:
        pass
    return ""

print(find_trt_lib_dir())
PY
)

if [[ -z "${TRT_LIB_DIR}" ]]; then
  echo "ERROR: Could not locate tensorrt/lib in site-packages." >&2
  exit 1
fi

# Best-effort linker config (some minimal containers won't have ldconfig)
echo "${TRT_LIB_DIR}" >/etc/ld.so.conf.d/tensorrt-wheel.conf 2>/dev/null || true
ldconfig 2>/dev/null || true

python3 - <<'PY'
import ctypes, onnxruntime as ort
for lib in ("libnvinfer.so.10","libnvinfer_plugin.so.10"):
    try:
        ctypes.CDLL(lib); print(lib, "OK")
    except OSError as e:
        raise SystemExit(f"{lib} MISSING: {e}")
print("ORT available providers:", ort.get_available_providers())
PY

echo "[TRT] Done."

