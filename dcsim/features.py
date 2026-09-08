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


def _history_edges(st, si, T, W, t_end, W_detect=1e-3):
    """v0.2.1. Rising-edge onsets in the slow-stream history before t_end.

    An edge onset is the first sample where the W_detect-step series
    s[k] = i[k+n] - i[k] leaves its noise band (robust sigma over the
    history) -- the same "first departure" rule detect_onset applies on the
    fast stream, so the two ends of a phase interval carry comparable bias.
    Crossings closer than 0.25 T are the same edge re-triggering and are
    merged. Returns (edge_times, step_over_W): the step reached W after each
    onset, used for the size residual."""
    dts = st[1] - st[0]
    m = st < t_end
    t, x = st[m], si[m]
    n_d = max(int(W_detect / dts), 1)
    n_w = max(int(W / dts), 1)
    if x.size <= n_d + 2:
        return np.array([]), np.array([])
    s = np.zeros_like(x)
    s[:-n_d] = x[n_d:] - x[:-n_d]
    sig = 1.4826 * np.median(np.abs(s - np.median(s))) + 1e-9
    thr = max(5.0 * sig, 0.25 * np.abs(s).max())
    above = s > thr
    rise = np.flatnonzero(above[1:] & ~above[:-1]) + 1
    edges, steps = [], []
    for k in rise:
        if edges and t[k] - edges[-1] < 0.25 * T:
            continue
        edges.append(t[k])
        k2 = min(k + n_w, x.size - 1)
        steps.append(x[k2] - x[k])
    return np.array(edges), np.array(steps)


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
    # v0.2.1 (B3): CAUSAL filter. sosfiltfilt was zero-phase: the backward
    # pass carried post-onset band energy into the pre-window baseline
    # (1 kHz corner -> ~160 us impulse response vs a 150 us pre-window), and a
    # relay cannot see the future. State is initialised at the pre-window
    # mean so the filter start-up transient does not inflate pre_i either.
    sos = signal.butter(4, [1e3, 100e3], btype="bandpass", fs=F_FAST, output="sos")
    zi = signal.sosfilt_zi(sos)
    bp_i, _ = signal.sosfilt(sos, fi - i_pre, zi=zi * 0.0)
    bp_v, _ = signal.sosfilt(sos, fv - v_pre, zi=zi * 0.0)
    n_skip = int(60e-6 * F_FAST)              # 60 us: let the 1 kHz section settle
    pre_i = bp_i[n_skip:n_pre].std() + 1e-9
    pre_v = bp_v[n_skip:n_pre].std() + 1e-9
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
        # v0.2.1 (B1, B2). The v0.2 estimate searched a +/-12 % window around
        # ONE previous edge, so phase_err was bounded at 0.12 by construction
        # and could not represent "landed at a random phase". It also located
        # that edge by argmax of a 1 ms difference series (mid-ramp) while
        # t_on is a noise-band onset on the fast stream: two different
        # estimators on the two ends of the interval.
        # Now: every rising edge in the history is located with a noise-band
        # onset rule (same principle as detect_onset), the scheduler phase is
        # the circular mean of those edges, and phase_err is the distance from
        # t_on to the nearest predicted edge, folded to [0, 0.5].
        edges, steps = _history_edges(st, si_, T, W, t_on - 0.5e-3)
        if edges.size >= 2:
            ph = np.exp(2j * np.pi * edges / T)
            t_ref = (np.angle(ph.mean()) / (2.0 * np.pi)) * T
            dphi = ((t_on - t_ref) / T) % 1.0
            f["phase_err"] = float(min(dphi, 1.0 - dphi))
            di_pred = float(np.median(steps))       # typical scheduled step over W
            f["resid_period"] = abs(di_end - di_pred) / I_rated
        else:
            f["resid_period"] = np.nan   # cadence known but too few edges to phase-lock
            f["phase_err"] = np.nan
    else:
        # no cadence in the history: the workload-aware features carry no
        # information and must not degenerate into a copy of magnitude
        f["resid_period"] = np.nan
        f["phase_err"] = np.nan

    f["onset_found"] = 1.0 if found else 0.0
    f["t_on_rel"] = (t_on - obs["t_event"]) * 1e3   # ms, diagnostic only (not a feature)
    return f
