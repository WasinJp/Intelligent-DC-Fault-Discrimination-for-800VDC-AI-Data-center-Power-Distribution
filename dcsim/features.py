"""dcsim.features — discrimination features from observable streams only.

Inputs are the synthesized fast (2 MSa/s) and slow (50 kSa/s) streams plus
the segment's configuration ratings (I_rated, V_ref), which a protection
relay knows. Nothing here touches hidden states or ground truth.

Feature groups (used by the ablation in the classifier study):
  CONV   magnitude and di/dt — what a threshold breaker sees
  PHYS   v-i physics: early voltage lead, dynamic resistance, rise time,
         collapse, spectral noise floor
  WORK   workload-aware: periodicity residual and phase error from the
         slow-stream history
"""

import numpy as np
from scipy import signal

CONV = ["di_end", "di_max", "didt_max"]
PHYS = ["t_rise", "dv_early", "di_early", "r_dyn", "v_sag_end", "v_min",
        "collapse", "spec_i", "spec_v"]
WORK = ["has_period", "period_strength", "resid_period", "phase_err"]
ALL = CONV + PHYS + WORK

F_FAST = 2e6
F_SLOW = 50e3


def _movavg(x, n):
    if n <= 1:
        return x
    c = np.cumsum(np.insert(x, 0, 0.0))
    y = (c[n:] - c[:-n]) / n
    return np.concatenate([np.full(n - 1, y[0]), y])


def detect_onset(fi, fv, n_pre, fs_i, fs_v):
    """First sample after the pre-window where smoothed |di| or |dv|
    leaves the noise band. Returns (k_on, i_pre, v_pre, sig_i, sig_v, found)."""
    i_pre, v_pre = fi[:n_pre].mean(), fv[:n_pre].mean()
    si = _movavg(fi, 10)
    sv = _movavg(fv, 10)
    sig_i = si[:n_pre].std() + 1e-9
    sig_v = sv[:n_pre].std() + 1e-9
    thr_i = max(5.0 * sig_i, 0.004 * fs_i)
    thr_v = max(5.0 * sig_v, 0.004 * fs_v)
    hit = (np.abs(si[n_pre:] - i_pre) > thr_i) | (np.abs(sv[n_pre:] - v_pre) > thr_v)
    idx = np.flatnonzero(hit)
    if idx.size == 0:
        return n_pre, i_pre, v_pre, sig_i, sig_v, False
    return n_pre + int(idx[0]), i_pre, v_pre, sig_i, sig_v, True


def _period_from_history(t_hist, i_hist, lag_min=15e-3, lag_max=250e-3, thr=0.4):
    """Autocorrelation period estimate. Returns (period, strength) or (0, 0)."""
    x = i_hist - i_hist.mean()
    if x.std() < 1e-9 or t_hist.size < 100:
        return 0.0, 0.0
    n = x.size
    X = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(X * np.conj(X))[:n]
    ac /= ac[0] + 1e-30
    dt = t_hist[1] - t_hist[0]
    k0, k1 = int(lag_min / dt), min(int(lag_max / dt), n - 1)
    if k1 <= k0 + 2:
        return 0.0, 0.0
    seg = ac[k0:k1]
    # first local maximum above threshold (fundamental, not a harmonic)
    peaks, _ = signal.find_peaks(seg, height=thr)
    if peaks.size == 0:
        return 0.0, 0.0
    kp = k0 + peaks[0]
    return kp * dt, float(ac[kp])


def extract(obs, I_rated, V_ref, W=1e-3):
    """Compute the feature dict for decision window W (s) after onset."""
    fi, fv, ft = obs["fast_i"].astype(np.float64), obs["fast_v"].astype(np.float64), obs["fast_t"]
    si_, sv_, st = obs["slow_i"].astype(np.float64), obs["slow_v"].astype(np.float64), obs["slow_t"]
    n_pre = int(0.15e-3 * F_FAST)
    k_on, i_pre, v_pre, sig_i, sig_v, found = detect_onset(fi, fv, n_pre, obs["fs_i"], obs["fs_v"])
    nW = int(W * F_FAST)
    k1 = min(k_on + nW, fi.size)
    wi, wv = fi[k_on:k1], fv[k_on:k1]
    smi = _movavg(wi, 20)     # 10 us
    smv = _movavg(wv, 20)

    f = {}
    # ---- CONV
    n_tail = max(int(0.1 * nW), 10)
    di_end = smi[-n_tail:].mean() - i_pre
    f["di_end"] = di_end / I_rated
    f["di_max"] = (np.abs(smi - i_pre)).max() / I_rated
    d = np.diff(smi) * F_FAST * 1e-6         # A/us
    f["didt_max"] = np.abs(d).max() / I_rated

    # ---- PHYS
    a = np.abs(smi - i_pre)
    tgt = abs(di_end)
    if tgt > 3 * sig_i:
        k10 = np.argmax(a >= 0.1 * tgt)
        k90 = np.argmax(a >= 0.9 * tgt)
        f["t_rise"] = max(k90 - k10, 1) / F_FAST * 1e3    # ms
    else:
        f["t_rise"] = W * 1e3
    e0, e1 = max(k_on - int(50e-6 * F_FAST), 0), min(k_on + int(50e-6 * F_FAST), fi.size)
    smv_all = _movavg(fv, 10)
    smi_all = _movavg(fi, 10)
    f["dv_early"] = (v_pre - smv_all[e0:e1].min()) / V_ref
    f["di_early"] = abs(smi_all[e1 - 1] - i_pre) / I_rated
    v_end = smv[-n_tail:].mean()
    f["v_sag_end"] = (v_pre - v_end) / V_ref
    f["v_min"] = smv.min() / v_pre
    f["r_dyn"] = ((v_pre - v_end) / V_ref) / (abs(di_end) / I_rated + 1e-3)
    f["collapse"] = 1.0 if smv.min() < 0.8 * v_pre else 0.0
    # spectral noise floor 1-100 kHz (post-window vs pre-window)
    sos = signal.butter(4, [1e3, 100e3], btype="bandpass", fs=F_FAST, output="sos")
    bp_i = signal.sosfiltfilt(sos, fi)
    bp_v = signal.sosfiltfilt(sos, fv)
    pre_i = bp_i[20:n_pre].std() + 1e-9
    pre_v = bp_v[20:n_pre].std() + 1e-9
    kh = min(k_on + int(0.3 * nW), fi.size - 10)
    f["spec_i"] = np.log10(bp_i[kh:k1].std() / pre_i + 1e-9)
    f["spec_v"] = np.log10(bp_v[kh:k1].std() / pre_v + 1e-9)

    # ---- WORK (slow-stream history before onset)
    t_on = ft[k_on]
    hist = st < t_on - 0.5e-3
    th, ih = st[hist], si_[hist]
    T, strength = _period_from_history(th, ih) if th.size > 200 else (0.0, 0.0)
    f["has_period"] = 1.0 if T > 0 else 0.0
    f["period_strength"] = strength
    if T > 0:
        dts = st[1] - st[0]
        nWs = max(int(W / dts), 1)
        s = np.concatenate([si_[nWs:] - si_[:-nWs], np.zeros(nWs)])   # step-in-W series
        lo, hi = t_on - 1.12 * T, t_on - 0.88 * T
        m = (st >= lo) & (st <= hi)
        if m.any():
            seg = s[m]
            kk = np.argmax(np.abs(seg))
            di_pred = seg[kk]
            t_prev = st[m][kk]
            f["resid_period"] = abs(di_end - di_pred) / I_rated
            f["phase_err"] = abs((t_on - t_prev) - T) / T
        else:
            f["resid_period"] = np.nan   # cadence known but no prior edge in window
            f["phase_err"] = np.nan
    else:
        # no cadence in the history: the workload-aware features carry no
        # information and must not degenerate into a copy of magnitude
        f["resid_period"] = np.nan
        f["phase_err"] = np.nan

    f["onset_found"] = 1.0 if found else 0.0
    f["t_on_rel"] = (t_on - obs["t_event"]) * 1e3   # ms, diagnostic only (not a feature)
    return f
