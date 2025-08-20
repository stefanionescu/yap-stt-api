from __future__ import annotations

import argparse
import glob
import json
import logging
import logging.handlers
import os
import time
from dataclasses import asdict, dataclass
from statistics import mean
from typing import List

# Where metrics JSONL are stored (rotated daily, keep 7 days)
METRICS_DIR = os.getenv("METRICS_DIR", "logs/metrics")
METRICS_FILE = os.path.join(METRICS_DIR, "metrics.log")

_logger: logging.Logger | None = None


class Timer:
    def __init__(self):
        self._start = time.perf_counter()

    def stop(self) -> float:
        return time.perf_counter() - self._start


@dataclass
class RequestMetrics:
    ts: float
    model: str
    audio_len_s: float
    sample_rate: int
    duration_preprocess_s: float
    duration_inference_s: float
    duration_total_s: float
    queue_wait_s: float
    status: str  # "ok" or "error"
    code: int
    error: str = ""


def _ensure_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    os.makedirs(METRICS_DIR, exist_ok=True)
    logger = logging.getLogger("parakeet.metrics")
    logger.setLevel(logging.INFO)

    handler = logging.handlers.TimedRotatingFileHandler(
        METRICS_FILE, when="midnight", backupCount=7, encoding="utf-8"
    )

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            if isinstance(record.msg, dict):
                payload = record.msg
            else:
                payload = {"message": record.getMessage()}
            payload["ts_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return json.dumps(payload, separators=(",", ":"))

    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    _logger = logger
    return logger


def log_request(metrics: RequestMetrics) -> None:
    logger = _ensure_logger()
    payload = asdict(metrics)
    logger.info(payload)


# ---- Reporting helpers ----

@dataclass
class Record:
    ts: float
    duration_total_s: float
    duration_preprocess_s: float
    duration_inference_s: float
    audio_len_s: float
    code: int
    status: str


def _load_records_since(since_ts: float) -> List[Record]:
    paths = sorted(glob.glob(os.path.join(METRICS_DIR, "metrics.log*")))
    out: List[Record] = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        ts = float(obj.get("ts", 0.0))
                        if ts < since_ts:
                            continue
                        out.append(
                            Record(
                                ts=ts,
                                duration_total_s=float(obj.get("duration_total_s", 0.0)),
                                duration_preprocess_s=float(obj.get("duration_preprocess_s", 0.0)),
                                duration_inference_s=float(obj.get("duration_inference_s", 0.0)),
                                audio_len_s=float(obj.get("audio_len_s", 0.0)),
                                code=int(obj.get("code", 0)),
                                status=str(obj.get("status", "")),
                            )
                        )
                    except Exception:
                        continue
        except FileNotFoundError:
            continue
    return out


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[int(k)]
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return d0 + d1


def _window_seconds(spec: str) -> int:
    spec = spec.strip().lower()
    if spec.endswith("m"):
        return int(float(spec[:-1]) * 60)
    if spec.endswith("h"):
        return int(float(spec[:-1]) * 3600)
    if spec.endswith("d"):
        return int(float(spec[:-1]) * 86400)
    return int(spec)


def report_window(name: str, seconds: int) -> None:
    now = time.time()
    since = now - seconds
    recs = _load_records_since(since)
    ok = [r for r in recs if r.status == "ok"]
    errs = [r for r in recs if r.status != "ok"]

    totals = [r.duration_total_s for r in ok]
    preprocess = [r.duration_preprocess_s for r in ok]
    infer = [r.duration_inference_s for r in ok]
    audio = [r.audio_len_s for r in ok]

    print(f"\n=== {name} (last {seconds//60}m) ===")
    print(f"count={len(recs)} ok={len(ok)} err={len(errs)}")
    if ok:
        print(
            f"latency_total_s: avg={mean(totals):.3f} p50={_percentile(totals,50):.3f} p95={_percentile(totals,95):.3f}"
        )
        print(f"latency_preprocess_s: avg={mean(preprocess):.3f}")
        print(f"latency_inference_s: avg={mean(infer):.3f}")
        print(f"audio_len_s: p50={_percentile(audio,50):.2f} p95={_percentile(audio,95):.2f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--windows",
        nargs="*",
        default=["30m", "1h", "3h", "6h", "12h", "24h", "3d"],
        help="Windows to report, e.g., 30m 1h 3h 6h 12h 24h 3d",
    )
    args = parser.parse_args()

    mapping = {}
    for w in args.windows:
        mapping[w] = _window_seconds(w)

    for name, secs in mapping.items():
        report_window(name, secs)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
