"""Metrics calculation and reporting utilities."""
from __future__ import annotations
import statistics as stats
from typing import Dict, List


def calculate_basic_metrics(audio_duration_s: float, wall_s: float, 
                          ttfw_word_s: float | None = None, 
                          ttfw_text_s: float | None = None) -> Dict[str, float]:
    """Calculate basic performance metrics."""
    rtf = wall_s / audio_duration_s if audio_duration_s > 0 else float("inf")
    xrt = (audio_duration_s / wall_s) if wall_s > 0 else 0.0
    throughput_min_per_min = (audio_duration_s / wall_s) if wall_s > 0 else 0.0
    
    metrics = {
        "wall_s": wall_s,
        "audio_s": audio_duration_s,
        "rtf": rtf,
        "xrt": xrt,
        "throughput_min_per_min": throughput_min_per_min,
    }
    
    if ttfw_word_s is not None:
        metrics["ttfw_word_s"] = float(ttfw_word_s)
    if ttfw_text_s is not None:
        metrics["ttfw_text_s"] = float(ttfw_text_s)
    
    return metrics


def calculate_detailed_metrics(handler, streamer, t0: float, last_signal_ts: float, 
                             file_duration_s: float, rtf: float) -> Dict[str, float]:
    """Calculate detailed metrics from handler and streamer state."""
    wall_to_final = (handler.final_recv_ts - t0) if handler.final_recv_ts else (last_signal_ts - t0)
    
    # Basic metrics
    metrics = {
        "wall_to_final_s": float(wall_to_final),
        "rtf_measured": float(wall_to_final / file_duration_s) if file_duration_s > 0 else None,
        "partials": float(len(handler.partial_ts)),
        "final_len_chars": float(len(handler.final_text)),
        "rtf_target": float(rtf),
    }
    
    # Timing metrics
    if len(handler.partial_ts) >= 2:
        gaps = [b - a for a, b in zip(handler.partial_ts[:-1], handler.partial_ts[1:])]
        metrics["avg_partial_gap_ms"] = float((sum(gaps) / len(gaps)) * 1000.0)
    else:
        metrics["avg_partial_gap_ms"] = 0.0
    
    # Latency metrics
    metrics["finalize_ms"] = float(
        ((handler.final_recv_ts - last_signal_ts) * 1000.0) 
        if (handler.final_recv_ts and last_signal_ts) else 0.0
    )
    
    # Processing metrics
    metrics["send_duration_s"] = float(
        (streamer.last_chunk_sent_ts - t0) if streamer.last_chunk_sent_ts else 0.0
    )
    metrics["post_send_final_s"] = float(
        (handler.final_recv_ts - streamer.last_chunk_sent_ts) 
        if (handler.final_recv_ts and streamer.last_chunk_sent_ts) else 0.0
    )
    metrics["delta_to_audio_ms"] = float((wall_to_final - file_duration_s) * 1000.0)
    metrics["flush_to_final_ms"] = float(
        ((handler.final_recv_ts - last_signal_ts) * 1000.0) 
        if (handler.final_recv_ts and last_signal_ts) else 0.0
    )
    metrics["decode_tail_ms"] = float(
        ((handler.final_recv_ts - handler.last_partial_ts) * 1000.0) 
        if (handler.final_recv_ts and handler.last_partial_ts) else 0.0
    )
    
    return metrics


def percentile(values: List[float], q: float) -> float:
    """Calculate percentile of values."""
    if not values:
        return 0.0
    k = max(0, min(len(values)-1, int(round(q*(len(values)-1)))))
    return sorted(values)[k]


def summarize_results(title: str, results: List[Dict[str, float]]) -> None:
    """Print summary statistics for benchmark results."""
    if not results:
        print(f"{title}: no results")
        return

    wall = [r["wall_s"] for r in results]
    audio = [r["audio_s"] for r in results]
    rtf = [r["rtf"] for r in results]
    rtf_measured = [r["rtf_measured"] for r in results if "rtf_measured" in r and r["rtf_measured"] is not None]
    xrt = [r["xrt"] for r in results]
    throughput = [r["throughput_min_per_min"] for r in results]
    ttfw_word_vals = [r["ttfw_word_s"] for r in results if "ttfw_word_s" in r]
    ttfw_text_vals = [r["ttfw_text_s"] for r in results if "ttfw_text_s" in r]
    fin = [r.get("finalize_ms", 0.0) for r in results if r.get("finalize_ms", 0.0) > 0]
    gaps = [r.get("avg_partial_gap_ms", 0.0) for r in results if r.get("avg_partial_gap_ms", 0.0) > 0]

    # New honest metrics
    deltas = [r["delta_to_audio_ms"] for r in results if "delta_to_audio_ms" in r]
    sendd = [r["send_duration_s"] for r in results if "send_duration_s" in r]
    postf = [r["post_send_final_s"] for r in results if "post_send_final_s" in r]
    f2f = [r["flush_to_final_ms"] for r in results if "flush_to_final_ms" in r and r["flush_to_final_ms"] > 0]
    dtail = [r["decode_tail_ms"] for r in results if "decode_tail_ms" in r and r["decode_tail_ms"] > 0]

    print(f"\n== {title} ==")
    print(f"n={len(results)}")
    print(f"Wall s      | avg={stats.mean(wall):.4f}  p50={stats.median(wall):.4f}  p95={percentile(wall,0.95):.4f}")
    if ttfw_word_vals:
        print(f"TTFW(word)  | avg={stats.mean(ttfw_word_vals):.4f}  p50={stats.median(ttfw_word_vals):.4f}  p95={percentile(ttfw_word_vals,0.95):.4f}")
    if ttfw_text_vals:
        print(f"TTFW(text)  | avg={stats.mean(ttfw_text_vals):.4f}  p50={stats.median(ttfw_text_vals):.4f}  p95={percentile(ttfw_text_vals,0.95):.4f}")
    print(f"Audio s     | avg={stats.mean(audio):.4f}")
    print(f"RTF         | avg={stats.mean(rtf):.4f}  p50={stats.median(rtf):.4f}  p95={percentile(rtf,0.95):.4f}")
    if rtf_measured:
        print(f"RTF(meas)   | avg={stats.mean(rtf_measured):.4f}  p50={stats.median(rtf_measured):.4f}  p95={percentile(rtf_measured,0.95):.4f}")
    print(f"xRT         | avg={stats.mean(xrt):.4f}")
    print(f"Throughput  | avg={stats.mean(throughput):.2f} min/min")
    
    # New honest metrics display
    if deltas: print(f"Δ(audio) ms | avg={stats.mean(deltas):.1f}  p50={percentile(deltas,0.50):.1f}  p95={percentile(deltas,0.95):.1f}")
    if sendd:  print(f"Send dur s  | avg={stats.mean(sendd):.3f}  p50={stats.median(sendd):.3f}  p95={percentile(sendd,0.95):.3f}")
    if postf:  print(f"Post-send→Final s | avg={stats.mean(postf):.3f}  p50={stats.median(postf):.3f}  p95={percentile(postf,0.95):.3f}")
    if f2f:    print(f"Flush→Final ms    | avg={stats.mean(f2f):.1f}  p50={percentile(f2f,0.50):.1f}  p95={percentile(f2f,0.95):.1f}")
    if dtail:  print(f"Decode tail ms    | avg={stats.mean(dtail):.1f}  p50={percentile(dtail,0.50):.1f}  p95={percentile(dtail,0.95):.1f}")
    if gaps:   print(f"Partial gap ms    | avg={stats.mean(gaps):.1f}  p50={percentile(gaps,0.50):.1f}  p95={percentile(gaps,0.95):.1f}")
