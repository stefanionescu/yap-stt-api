import numpy as np


def _frame_energy(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    # simple RMS energy
    return float(np.mean(x.astype(np.float32) ** 2))


def build_segments(
    wav_i16: np.ndarray,
    sr: int = 16000,
    seg_ms: int = 2200,          # shorter ⇒ smaller tail
    min_ms: int = 1200,
    overlap_ms: int = 200,
    vad_window_ms: int = 400,    # search window for a quiet cut
    vad_thr: float = 1.2e-3,     # tweak per mic/noise
    vad_frame_ms: int = 20,      # 20 ms RMS frames
):
    seg_len = int(seg_ms * sr / 1000)
    min_len = int(min_ms * sr / 1000)
    ovl = int(overlap_ms * sr / 1000)
    vad_win = int(vad_window_ms * sr / 1000)
    frm = max(1, int(vad_frame_ms * sr / 1000))

    N = len(wav_i16)
    edges = []
    start = 0
    while start + min_len < N:
        hard_end = min(start + seg_len, N)
        # search for the last quiet frame in [hard_end - vad_win, hard_end]
        search_lo = max(start + min_len, hard_end - vad_win)
        cut = hard_end
        if search_lo < hard_end:
            last_quiet = None
            i = search_lo
            while i < hard_end:
                j = min(i + frm, hard_end)
                if _frame_energy(wav_i16[i:j]) < vad_thr:
                    last_quiet = i
                i = j
            if last_quiet is not None:
                cut = max(last_quiet, start + min_len)
        edges.append((start, cut, ovl))
        if cut >= N:
            break
        start = max(cut - ovl, 0)

    if not edges or edges[-1][1] < N:
        edges.append((edges[-1][1] if edges else 0, N, 0))

    # force last segment to have zero extra overlap when slicing
    s, e, _ = edges[-1]
    edges[-1] = (s, e, 0)
    return edges  # list[(start, end, overlap)]


