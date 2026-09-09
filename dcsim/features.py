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
# v0.2.2: resid_period removed from WORK. It is |di_end - di_pred| and on any
# unscheduled event di_pred ~ 0, so it is |di_end| under another name (0.92
# correlation with di_max); 10-seed CV showed it costs 0.3-0.6 pt of missed
# faults. It is still computed and written as a diagnostic column.
WORK = ["has_period", "period_strength", "phase_err"]
ALL = CONV + PHYS + WORK

F_FAST = 2e6
F_SLOW = 5e3     # v1: 5 kSa/s (2 kHz anti-alias) -- ample for ms-scale edge timing over seconds of history


def _movavg(x, n):
    if n <= 1:
        return x
    c = np.cumsum(np.insert(x, 0, 0.0))
    y = (c[n:] - c[:-n]) / n
    return np.concatenate([np.full(n - 1, y[0]), y])


def detect_onset(fi, fv, n_pre, fs_i, fs_v, n_sm=10):
    """First sample after the pre-window where smoothed |di| or |dv|
    leaves the noise band. n_sm: smoothing window in samples (5 us at the
    stream rate). Returns (k_on, i_pre, v_pre, sig_i, sig_v, found)."""
    i_pre, v_pre = fi[:n_pre].mean(), fv[:n_pre].mean()
    si = _movavg(fi, n_sm)
    sv = _movavg(fv, n_sm)
    sig_i = si[:n_pre].std() + 1e-9
    sig_v = sv[:n_pre].std() + 1e-9
    thr_i = max(5.0 * sig_i, 0.004 * fs_i)
    thr_v = max(5.0 * sig_v, 0.004 * fs_v)
    hit = (np.abs(si[n_pre:] - i_pre) > thr_i) | (np.abs(sv[n_pre:] - v_pre) > thr_v)
    idx = np.flatnonzero(hit)
    if idx.size == 0:
        return n_pre, i_pre, v_pre, sig_i, sig_v, False
    return n_pre + int(idx[0]), i_pre, v_pre, sig_i, sig_v, True


def _cadence_candidates(t_hist, i_hist, lag_min=15e-3, lag_max=None, thr=0.15,
                        prom=0.08, max_tiers=3):
    """v1 (OPEN-9). Up to max_tiers fundamental periods from the autocorrelation
    of the slow-stream history. Peaks need height >= thr and prominence >= prom.
    A peak is a new fundamental unless its lag ratio to a shorter fundamental
    is within 0.06 of an integer >= 2 (any order). Candidates are returned sorted by
    period descending (tier 1 = longest), as (period, strength) pairs."""
    x = i_hist - i_hist.mean()
    if x.std() < 1e-9 or t_hist.size < 100:
        return []
    n = x.size
    X = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(X * np.conj(X))[:n]
    ac /= ac[0] + 1e-30
    dt = t_hist[1] - t_hist[0]
    span = t_hist[-1] - t_hist[0]
    if lag_max is None:
        lag_max = 0.45 * span
    k0, k1 = int(lag_min / dt), min(int(lag_max / dt), n - 1)
    if k1 <= k0 + 2:
        return []
    seg = ac[k0:k1]
    peaks, props = signal.find_peaks(seg, height=thr, prominence=prom)
    if peaks.size == 0:
        return []
    lags = (k0 + peaks) * dt
    heights = props["peak_heights"]
    order = np.argsort(lags)
    fund = []                         # (lag, height)
    for i in order:
        L, h = lags[i], heights[i]
        harmonic = False
        for (L0, _) in fund:
            r = L / L0
            # v0.3.1: no upper cap on the harmonic order. A 20 ms burst comb
            # reaches 0.8 at its 10th harmonic and outranked a 2 s iteration
            # peak of 0.6; tolerance is absolute on the ratio so a genuine
            # long period at ratio 107.7 is not swallowed.
            if round(r) >= 2 and abs(r - round(r)) < 0.06:
                harmonic = True
                break
        if not harmonic:
            fund.append((L, h))
    fund.sort(key=lambda p: -p[1])
    fund = fund[:max_tiers]
    fund.sort(key=lambda p: -p[0])    # tier 1 = longest period
    return [(float(L), float(h)) for L, h in fund]


def _period_from_history(t_hist, i_hist, lag_min=15e-3, lag_max=None, thr=0.25):
    """Tier-1 period only (longest fundamental). Kept for callers that want
    a single cadence; returns (period, strength) or (0, 0)."""
    c = _cadence_candidates(t_hist, i_hist, lag_min, lag_max, thr, max_tiers=1)
    return c[0] if c else (0.0, 0.0)


def _edges_two_level(t, x, T, n_w, n_sm=10):
    """Two-level rising-edge onsets on one contiguous series (t, x). See
    _history_edges for the rule. Returns (edges, steps, state) where state is
    the boolean high/low classification per sample."""
    if x.size < 50:
        return np.array([]), np.array([]), np.zeros(x.size, bool)
    x = _movavg(x, max(n_sm, 1))                 # v1: 2 ms smoothing before level analysis
    lo, hi = np.percentile(x, 15), np.percentile(x, 85)
    noise = 1.4826 * np.median(np.abs(np.diff(x))) / np.sqrt(2.0) + 1e-9
    if hi - lo < 4.0 * noise:                    # no two-level structure
        return np.array([]), np.array([]), np.zeros(x.size, bool)
    mid, hyst = 0.5 * (lo + hi), 0.15 * (hi - lo)
    low = x[x < mid]
    sig_lo = 1.4826 * np.median(np.abs(low - np.median(low))) + 1e-9
    state = np.zeros(x.size, bool)
    st_ = x[0] > mid
    edges, steps = [], []
    for k in range(1, x.size):
        if not st_ and x[k] > mid + hyst:
            j = k
            while j > 0 and x[j] > lo + 3.0 * sig_lo:
                j -= 1
            if not edges or t[j] - edges[-1] > 0.25 * T:
                edges.append(t[j])
                k2 = min(j + n_w, x.size - 1)
                steps.append(x[k2] - x[j])
            st_ = True
        elif st_ and x[k] < mid - hyst:
            st_ = False
        state[k] = st_
    state[0] = x[0] > mid
    return np.array(edges), np.array(steps), state


def _history_edges(st, si, T, W, t_end):
    """Rising-edge onsets in the slow-stream history before t_end.

    v0.2.2: two-level model. A scheduler train has a low state and a high
    state; a rising edge is an upward crossing of the midpoint between them
    (with hysteresis), walked back to the last sample inside the low-state
    noise band, which is the onset -- the same "departure from noise" notion
    detect_onset uses on the fast stream. Ring-back after a FALLING edge is
    a bump on the low level and cannot reach the midpoint, so it is never
    logged as a rising edge. Returns (edge_times, step_over_W)."""
    dts = st[1] - st[0]
    m = st < t_end
    t, x = st[m], si[m]
    n_w = max(int(W / dts), 1)
    e, s_, _ = _edges_two_level(t, x, T, n_w)
    return e, s_


def _tier2_from_segments(t, x, state1, T1, dts, lag_min=15e-3, thr=0.25, prom=0.08):
    """v1. Tier-2 period from the tier-1 compute-phase segments: each high
    segment is mean-removed, its normalised autocorrelation computed, and the
    curves averaged over segments (a 0.1 p.u. burst on a 0.5 p.u. iteration
    wave is ~2 % of the full-history variance and invisible there). Returns
    (T2, strength) or (0, 0)."""
    idx = np.flatnonzero(np.diff(state1.astype(int)) != 0) + 1
    bounds = np.concatenate([[0], idx, [x.size]])
    segs = [(a, b) for a, b in zip(bounds[:-1], bounds[1:])
            if state1[a] and (b - a) * dts >= 0.1]
    if not segs:
        return 0.0, 0.0
    # v0.3.1: lag window from the LONGEST segment. The shortest is always a
    # partial phase (history start, or the current phase cut at the event)
    # and using it lost 41 % of 100-200 ms burst periods. Each segment
    # contributes autocorrelation only up to 0.45 of its own length.
    kmax = max(b - a for a, b in segs)
    k0 = int(lag_min / dts)
    k1 = int(0.45 * kmax)
    if k1 <= k0 + 2:
        return 0.0, 0.0
    acc = np.zeros(k1 - k0)
    cnt = np.zeros(k1 - k0)
    nseg = 0
    for a, b in segs:
        r = x[a:b] - x[a:b].mean()
        if r.std() < 1e-9:
            continue
        n = r.size
        R = np.fft.rfft(r, 2 * n)
        ac = np.fft.irfft(R * np.conj(R))[:n]
        ac /= ac[0] + 1e-30
        k1s = min(k1, int(0.45 * n))
        if k1s <= k0:
            continue
        acc[:k1s - k0] += ac[k0:k1s]
        cnt[:k1s - k0] += 1
        nseg += 1
    if nseg == 0:
        return 0.0, 0.0
    m_ok = cnt > 0
    acc[m_ok] /= cnt[m_ok]
    acc = acc[m_ok]
    peaks, props = signal.find_peaks(acc, height=thr, prominence=prom)
    if peaks.size == 0:
        return 0.0, 0.0
    h = props["peak_heights"]
    kp = k0 + peaks[h >= 0.85 * h.max()].min()
    T2 = kp * dts
    if T2 > 0.4 * T1:
        return 0.0, 0.0
    return float(T2), float(acc[kp - k0])


def _learn_cadence(st, si, W, t_end):
    """v1 (OPEN-9). Learn up to two cadence tiers from the slow-stream history
    before t_end. Tier 1 (longest period) is located on the full history.
    Tier 2 (shorter) is searched inside tier-1 high-state segments, each
    segment referenced to its own floor, so the iteration square wave does
    not swamp either the period search or the two-level edge model. Returns
    list of dicts {T, strength, edges, steps}, tier 1 first; empty if none."""
    dts = st[1] - st[0]
    m = st < t_end
    t, x = st[m], si[m]
    if t.size < 200:
        return []
    n_w = max(int(W / dts), 1)
    cands = _cadence_candidates(t, x)
    if not cands:
        return []
    # v0.3.1: envelope search. The iteration wave is the ENVELOPE of the EDP
    # bursts. Take the shortest strong cadence T_s, smooth the history over
    # 2*T_s (kills the burst comb and all its harmonics), and search the
    # smoothed history for a longer fundamental. If one exists, it is tier 1
    # and T_s is tier 2; otherwise the tallest candidate is the only tier.
    T_s = min(c[0] for c in cands)
    n_env = max(int(2.0 * T_s / dts), 3)
    x_env = _movavg(x, n_env)
    env = _cadence_candidates(t, x_env, lag_min=3.0 * T_s, max_tiers=1)
    if env and env[0][0] > 2.5 * T_s:
        T1, s1 = env[0]
        T2_hint = T_s
    else:
        # tallest candidate; fall through the list until two edges appear
        by_h = sorted(cands, key=lambda c: -c[1])
        T1, s1 = by_h[0]
        T2_hint = 0.0
    tiers = []
    e1, st1, state1 = _edges_two_level(t, x, T1, n_w)
    if e1.size < 2 and T2_hint == 0.0:
        for T1b, s1b in sorted(cands, key=lambda c: -c[0]):
            e1b, st1b, state1b = _edges_two_level(t, x, T1b, n_w)
            if e1b.size >= 2:
                T1, s1, e1, st1, state1 = T1b, s1b, e1b, st1b, state1b
                break
    tiers.append(dict(T=T1, strength=s1, edges=e1, steps=st1))
    T2, s2 = _tier2_from_segments(t, x, state1, T1, dts)
    if T2 == 0.0 and T2_hint > 0 and T2_hint < 0.4 * T1:
        T2, s2 = T2_hint, [c[1] for c in cands if c[0] == T2_hint][0]
    if T2 > 0:
        idx = np.flatnonzero(np.diff(state1.astype(int)) != 0) + 1
        bounds = np.concatenate([[0], idx, [x.size]])
        e2, st2 = [], []
        for a, b in zip(bounds[:-1], bounds[1:]):
            if not state1[a] or (b - a) * dts < 2.0 * T2:
                continue
            seg = x[a:b] - np.percentile(x[a:b], 10)
            ee, ss, _ = _edges_two_level(t[a:b], seg, T2, n_w, n_sm=3)
            e2.extend(ee.tolist()); st2.extend(ss.tolist())
        if len(e2) >= 2:
            e2 = np.array(e2)
            # EDP bursts are phase-locked to their own compute phase, which starts
            # at a jittered iteration edge -- bursts in different phases are NOT
            # coherent modulo T2. The phase reference must come from the current
            # phase; learn the first-burst offset from previous phases as fallback.
            starts = [t[a] for a, b in zip(bounds[:-1], bounds[1:]) if state1[a]]
            cur_start = starts[-1] if (starts and state1[-1]) else np.nan
            offs = []
            for s0 in starts[:-1] if state1[-1] else starts:
                nxt = e2[e2 > s0]
                if nxt.size:
                    offs.append(nxt.min() - s0)
            off2 = float(np.median(offs)) if offs else np.nan
            cur = e2[e2 > cur_start] if not np.isnan(cur_start) else np.array([])
            tiers.append(dict(T=T2, strength=s2, edges=e2, steps=np.array(st2),
                              phase_start=cur_start, edges_current=cur, off2=off2))
    return tiers


def extract(obs, I_rated, V_ref, W=1e-3):
    """Compute the feature dict for decision window W (s) after onset."""
    fi, fv, ft = obs["fast_i"].astype(np.float64), obs["fast_v"].astype(np.float64), obs["fast_t"]
    si_, sv_, st = obs["slow_i"].astype(np.float64), obs["slow_v"].astype(np.float64), obs["slow_t"]
    # v0.3.2 (OPEN-12): all windows are times; sample counts follow the stream rate
    fs = float(obs.get("fs_fast", F_FAST))
    n_pre = max(int(0.15e-3 * fs), 4)
    n5 = max(int(5e-6 * fs), 1)               # 5 us smoothing (onset detector, early windows)
    n10 = max(int(10e-6 * fs), 1)             # 10 us smoothing (decision window)
    k_on, i_pre, v_pre, sig_i, sig_v, found = detect_onset(fi, fv, n_pre, obs["fs_i"], obs["fs_v"], n_sm=n5)
    nW = max(int(W * fs), 4)
    k1 = min(k_on + nW, fi.size)
    wi, wv = fi[k_on:k1], fv[k_on:k1]
    smi = _movavg(wi, n10)
    smv = _movavg(wv, n10)

    f = {}
    # ---- CONV
    n_tail = max(int(0.1 * nW), min(10, nW))
    di_end = smi[-n_tail:].mean() - i_pre
    f["di_end"] = di_end / I_rated
    f["di_max"] = (np.abs(smi - i_pre)).max() / I_rated
    d = np.diff(smi) * fs * 1e-6             # A/us
    f["didt_max"] = np.abs(d).max() / I_rated if d.size else 0.0

    # ---- PHYS
    a = np.abs(smi - i_pre)
    tgt = abs(di_end)
    if tgt > 3 * sig_i:
        k10 = np.argmax(a >= 0.1 * tgt)
        k90 = np.argmax(a >= 0.9 * tgt)
        f["t_rise"] = max(k90 - k10, 1) / fs * 1e3    # ms
    else:
        f["t_rise"] = W * 1e3
    n50 = max(int(50e-6 * fs), 1)
    e0, e1 = max(k_on - n50, 0), min(k_on + n50, fi.size)
    smv_all = _movavg(fv, n5)
    smi_all = _movavg(fi, n5)
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
    f_hi = min(100e3, 0.4 * fs)               # band top follows the anti-alias corner
    sos = signal.butter(4, [1e3, f_hi], btype="bandpass", fs=fs, output="sos")
    zi = signal.sosfilt_zi(sos)
    bp_i, _ = signal.sosfilt(sos, fi - i_pre, zi=zi * 0.0)
    bp_v, _ = signal.sosfilt(sos, fv - v_pre, zi=zi * 0.0)
    n_skip = min(int(60e-6 * fs), n_pre - 3)  # 60 us: let the 1 kHz section settle
    pre_i = bp_i[n_skip:n_pre].std() + 1e-9
    pre_v = bp_v[n_skip:n_pre].std() + 1e-9
    kh = min(k_on + int(0.3 * nW), fi.size - 4)
    f["spec_i"] = np.log10(bp_i[kh:k1].std() / pre_i + 1e-9) if k1 > kh + 1 else 0.0
    f["spec_v"] = np.log10(bp_v[kh:k1].std() / pre_v + 1e-9) if k1 > kh + 1 else 0.0

    # ---- WORK (slow-stream history before onset)
    # v1 (OPEN-9): up to two learned cadences; phase_err is the distance to the
    # nearest predicted rising edge of EITHER tier, folded to [0, 0.5]. The
    # added alibi coverage of a second tier is real and is measured, not hidden.
    t_on = ft[k_on]
    tiers = _learn_cadence(st, si_, W, t_on - 0.5e-3)
    f["has_period"] = 1.0 if tiers else 0.0
    f["period_strength"] = tiers[0]["strength"] if tiers else 0.0
    f["n_tiers"] = float(len(tiers))
    f["T1_est"] = tiers[0]["T"] if tiers else 0.0
    f["T2_est"] = tiers[1]["T"] if len(tiers) > 1 else 0.0
    pe = []
    for ti in tiers:
        e, T = ti["edges"], ti["T"]
        if "phase_start" in ti:                       # tier 2: current compute phase only
            if np.isnan(ti["phase_start"]):
                pe.append(np.nan)                     # not in a compute phase -> no EDP alibi
                continue
            cur = ti["edges_current"]
            if cur.size >= 1:
                ph = np.exp(2j * np.pi * cur / T)
                t_ref = (np.angle(ph.mean()) / (2.0 * np.pi)) * T
            elif not np.isnan(ti["off2"]):
                t_ref = ti["phase_start"] + ti["off2"]
            else:
                pe.append(np.nan)
                continue
            dphi = ((t_on - t_ref) / T) % 1.0
            pe.append(float(min(dphi, 1.0 - dphi)))
            continue
        if e.size < 2:
            pe.append(np.nan)
            continue
        ph = np.exp(2j * np.pi * e / T)
        t_ref = (np.angle(ph.mean()) / (2.0 * np.pi)) * T
        dphi = ((t_on - t_ref) / T) % 1.0
        pe.append(float(min(dphi, 1.0 - dphi)))
    f["phase_err_t1"] = pe[0] if len(pe) > 0 else np.nan
    f["phase_err_t2"] = pe[1] if len(pe) > 1 else np.nan
    valid = [p for p in pe if not np.isnan(p)]
    f["phase_err"] = min(valid) if valid else np.nan
    if tiers and tiers[0]["steps"].size:
        f["resid_period"] = abs(di_end - float(np.median(tiers[0]["steps"]))) / I_rated   # diagnostic
    else:
        f["resid_period"] = np.nan

    f["onset_found"] = 1.0 if found else 0.0
    f["fs_fast"] = fs                                    # diagnostic
    f["adc_bits_used"] = float(obs.get("adc_bits", np.nan))
    f["t_on_rel"] = (t_on - obs["t_event"]) * 1e3   # ms, diagnostic only (not a feature)
    return f
