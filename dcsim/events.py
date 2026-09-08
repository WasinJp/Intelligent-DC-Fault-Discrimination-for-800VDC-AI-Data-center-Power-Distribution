"""dcsim.events — parameter draws, event taxonomy and time-base schedule.

Implements MODEL.md §5 (event models), §6 (sweep ranges), §8 (segmented
time base) and §9 gate 1 (sanity gate). Every event is fully determined by
(MODEL.md version, master seed): all draws come from a seeded substream.
"""

import numpy as np
from .model import PARAMS_BASELINE

LABELS = ("benign_step", "benign_train", "benign_idle_drop",
          "bolted_pp", "resistive_pp", "high_z", "series_arc")
BENIGN = LABELS[:3]
FAULTS = LABELS[3:]

DT_COARSE = 2e-6      # s, near-event history / post-event (fastest healthy tau_c = 16 us)
DT_HIST = 1e-5        # s, deep history tier (v1 workload): 10 us, RK4-stable at tau_c >= 16 us,
                      #    >= 20 steps per period of the fastest healthy L-C resonance (5 kHz)
HIST_MARGIN = 0.2     # s, the last 200 ms before the event always run at DT_COARSE
DT_FINE = 5e-8        # s, event window (fault-branch tau_f down to 0.2 us)

WORKLOAD_VERSION = "v1"   # "v0.2": single 20-200 ms train (dataset v0.2 reproduction)
                          # "v1"  : two-tier cadence -- iteration (0.3-3 s) + EDP-peak (20-200 ms),
                          #         smoothed / unsmoothed regimes, interval jitter <= 2 %  (EVIDENCE.md)
FINE_PRE = 0.2e-3     # s, fine window starts this long before the anchor
FINE_POST = 5e-3      # s, fine window length after the anchor
T_POST = 10e-3        # s, total simulated time after anchor
FAULT_DURATION = 5e-3  # s, fault branch active (SSCB clears by then)


# ---------------------------------------------------------------- draws

def _lu(rng, lo, hi):
    """log-uniform draw."""
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


def draw_system(rng):
    """One system parameter draw per MODEL.md §6 sweep ranges."""
    p = dict(PARAMS_BASELINE)
    p["V_ref"] = rng.uniform(760.0, 840.0)
    p["P_rated"] = _lu(rng, 100e3, 1e6)
    I_rated = p["P_rated"] / p["V_ref"]
    p["R_droop"] = rng.uniform(0.002, 0.05) * p["V_ref"] / I_rated
    p["tau_c"] = _lu(rng, 16e-6, 320e-6)
    p["C_bus"] = _lu(rng, 1e-3, 50e-3)
    p["L_line"] = _lu(rng, 1e-6, 50e-6)
    p["R_line"] = _lu(rng, 1e-3, 20e-3)
    p["R_esr"] = _lu(rng, 2e-3, 20e-3)
    p["V_uvlo"] = rng.uniform(600.0, 700.0) * p["V_ref"] / 800.0
    p["I_lim"] = rng.uniform(1.5, 2.0) * I_rated
    # sensor front-end (§6, §7)
    p["noise_frac"] = _lu(rng, 0.0005, 0.005)
    p["adc_bits"] = int(rng.choice([12, 14, 16]))
    p["I_rated"] = I_rated
    return p


def sanity_gate(p, zeta_min=0.15):
    """§9 gate 1 (analytic part). Linearized source-R/L/C/CPL characteristic
        s^2 + (R/L - P/(C V^2)) s + (1/LC)(1 - R P/V^2) = 0,  R = R_line + R_droop
    Requires the damping ratio zeta >= zeta_min (a designed system is not
    marginally damped) and R P / V^2 < 1. Returns (ok, zeta)."""
    R = p["R_line"] + p["R_droop"]
    a = R / p["L_line"] - p["P_rated"] / (p["C_bus"] * p["V_ref"] ** 2)
    w0 = np.sqrt((1.0 - R * p["P_rated"] / p["V_ref"] ** 2)
                 / (p["L_line"] * p["C_bus"])) if R * p["P_rated"] / p["V_ref"] ** 2 < 1 else 0.0
    zeta = a / (2.0 * w0) if w0 > 0 else -1.0
    return zeta >= zeta_min, zeta


# ---------------------------------------------------------------- schedule

def build_schedule(t_pre, t_event, t_post, dt_coarse=DT_COARSE, dt_fine=DT_FINE,
                   fine_pre=FINE_PRE, fine_post=FINE_POST,
                   dt_hist=DT_HIST, hist_margin=HIST_MARGIN, use_hist=True):
    """Segmented time base (§8). [history tier at dt_hist, v1] -> coarse to
    t_pre (last hist_margin seconds) -> fine from t_event - fine_pre to
    t_event + fine_post -> coarse to t_event + t_post. The history tier is
    used only when t_pre exceeds hist_margin + fine_pre. Returns dict with
    dt (n,), t (n,), idx_event, idx_fine_start, idx_fine_end, idx_hist_end."""
    assert abs(t_pre - t_event) < 1e-12, "anchor is placed at t_pre"
    t_hist = t_pre - fine_pre - hist_margin
    if use_hist and t_hist > 0:
        n_h = int(round(t_hist / dt_hist))
        n_c1 = int(round(hist_margin / dt_coarse))
    else:
        n_h = 0
        n_c1 = int(round((t_pre - fine_pre) / dt_coarse))
    n_f = int(round((fine_pre + fine_post) / dt_fine))
    n_c2 = int(round((t_post - fine_post) / dt_coarse))
    dt = np.concatenate([np.full(n_h, dt_hist),
                         np.full(n_c1, dt_coarse),
                         np.full(n_f, dt_fine),
                         np.full(n_c2, dt_coarse)])
    t = np.concatenate([[0.0], np.cumsum(dt)[:-1]])
    idx_fine_start = n_h + n_c1
    idx_event = idx_fine_start + int(round(fine_pre / dt_fine))
    idx_fine_end = idx_fine_start + n_f
    return dict(dt=dt, t=t, idx_event=idx_event, idx_hist_end=n_h,
                idx_fine_start=idx_fine_start, idx_fine_end=idx_fine_end)


# ---------------------------------------------------------------- profiles

def _ramp(t, t0, t_ramp):
    return np.clip((t - t0) / t_ramp, 0.0, 1.0)


def train_profile(t, P0, dP, period, duty, t_ramp, jitter_frac, rng, t_last_edge):
    """Periodic step train (§5 benign_train). Rising edges at
    t_last_edge - k*period (+ jitter); each pulse lasts duty*period.
    Returns P(t) and the list of rising-edge times (jittered)."""
    P = np.full_like(t, P0)
    edges = []
    k = 0
    while True:
        te = t_last_edge - k * period
        if te < -period:
            break
        j = rng.uniform(-jitter_frac, jitter_frac) * period if k > 0 else 0.0
        te_j = te + j
        edges.append(te_j)
        P += dP * (_ramp(t, te_j, t_ramp) - _ramp(t, te_j + duty * period, t_ramp))
        k += 1
    return P, sorted(edges)


def two_tier_profile(t, P0, dP1, T1, duty1, ramp1, jit1, t_grid1, rng,
                      edp=None, jit_k0=None, pin2=None):
    """v1 workload (EVIDENCE.md §1-3). Tier 1: iteration square wave with
    rising edges on the grid t_grid1 - k*T1, each perturbed by U(-jit1, jit1)*T1
    (phase-locked cadence, interval jitter); compute phase lasts duty1*T1,
    then a falling edge (same jitter). Tier 2 (optional, dict edp with keys
    T2, duty2, dP2, ramp2, jit2, off2): EDP-peak bursts riding on every
    compute phase, starting off2 after the rising edge, period T2.
    jit_k0: if given, the jitter (in s) applied to the k = 0 rising edge
    instead of a random draw -- lets the caller place a scheduled event
    exactly at the anchor. pin2: if given, the tier-2 burst whose nominal
    time is nearest pin2 is placed exactly at pin2 (unjittered).
    Returns P(t), rising-edge times of tier 1, rising-edge times of tier 2."""
    P = np.full_like(t, P0)
    e1, e2 = [], []
    t_max = t[-1]
    k = 0
    while True:
        tr = t_grid1 - k * T1
        if tr < -T1:
            break
        j = rng.uniform(-jit1, jit1) * T1
        if k == 0 and jit_k0 is not None:
            j = jit_k0
        tr_j = tr + j
        tf_j = tr_j + duty1 * T1 + rng.uniform(-jit1, jit1) * T1
        e1.append(tr_j)
        P += dP1 * (_ramp(t, tr_j, ramp1) - _ramp(t, tf_j, ramp1))
        if edp is not None:
            T2, d2, dP2, r2, j2, off2 = (edp["T2"], edp["duty2"], edp["dP2"],
                                         edp["ramp2"], edp["jit2"], edp["off2"])
            m = 0
            while True:
                b = tr_j + off2 + m * T2
                if b + d2 * T2 > tf_j - r2:
                    break
                b_j = b + rng.uniform(-j2, j2) * T2
                if pin2 is not None and abs(b - pin2) < 0.5 * T2:
                    b_j = pin2
                if b_j < t_max + T2:
                    e2.append(b_j)
                    P += dP2 * (_ramp(t, b_j, r2) - _ramp(t, b_j + d2 * T2, r2))
                m += 1
        k += 1
    return P, sorted(e1), sorted(e2)


def arc_noise(n, dt, f_lo, f_hi, rms, rng):
    """Band-limited 1/f-weighted noise (§4.6) on a uniform grid."""
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, dt)
    w = np.zeros_like(f)
    m = (f >= f_lo) & (f <= f_hi)
    w[m] = 1.0 / np.sqrt(f[m] / f_lo)
    y = np.fft.irfft(X * w, n)
    y *= rms / (np.std(y) + 1e-30)
    return y



# ---------------------------------------------------------------- workload generators

def _workload_v02(rng, label, background, P_rated):
    """Dataset v0.2 workload, unchanged: single 20-200 ms train, per-edge
    jitter U(0, 5 %), event edge unjittered. Kept for exact reproduction."""
    period = _lu(rng, 20e-3, 200e-3)
    duty = rng.uniform(0.3, 0.7)
    t_ramp_bg = _lu(rng, 0.5e-3, 10e-3)
    dP_bg = rng.uniform(0.10, 0.80) * P_rated
    jitter = rng.uniform(0.0, 0.05)
    P0 = rng.uniform(0.15, 0.6) * P_rated
    if background == "train":
        t_pre = 2.5 * period + 20e-3
    else:
        t_pre = 60e-3
        P0 = rng.uniform(0.3, 0.9) * P_rated
    t_event = t_pre
    sched = build_schedule(t_pre, t_event, T_POST, use_hist=False)
    t = sched["t"]
    edges = []
    composite = False
    if background == "train":
        if label == "benign_train":
            t_last_edge = t_event
        else:
            composite = rng.uniform() < 0.35
            if composite:
                t_last_edge = t_event - rng.uniform(0.0, min(t_ramp_bg, 3e-3))
            else:
                t_last_edge = t_event - rng.uniform(1.2 * t_ramp_bg, 0.9 * period)
                t_last_edge = t_event - (t_event - t_last_edge) % period
        P, edges = train_profile(t, P0, dP_bg, period, duty, t_ramp_bg, jitter,
                                 rng, t_last_edge)
    else:
        P = np.full(t.shape[0], P0)
        if label in FAULTS:
            composite = rng.uniform() < 0.35
            if composite:
                ts = t_event - rng.uniform(0.0, min(t_ramp_bg, 3e-3))
                P = P + dP_bg * _ramp(t, ts, t_ramp_bg)
                edges = [ts]
    wl = dict(period=period if background == "train" else 0.0, dP_bg=dP_bg,
              t_ramp_bg=t_ramp_bg, P0=P0, workload="v0.2", smoothed=False,
              T1=period if background == "train" else 0.0, T2=0.0, sched_tier=0,
              jit1=jitter)
    return P, edges, sched, t_event, composite, wl


def _workload_v1(rng, label, background, P_rated):
    """Dataset v1 workload (EVIDENCE.md §1-3, OPEN-9/10).

    Regime (50/50): unsmoothed -- idle-to-near-TDP steps, free ramp 0.5-10 ms;
    smoothed -- GPU power smoothing active (MPF <= 90 % TDP, EDP 1.1x), step
    0.10-0.35 p.u. with a programmed ramp 2-20 ms.
    Tier 1: iteration cadence 0.3-3 s, duty 0.3-0.7, interval jitter <= 2 %.
    Tier 2 (p = 0.6): EDP-peak bursts inside compute phases, 20 ms to
    min(200 ms, duty*T1/3), amplitude 0.05-0.25 p.u.
    benign_train lands on the next rising edge of tier 1 or tier 2 (sched_tier).
    """
    smoothed = rng.uniform() < 0.5
    if smoothed:
        dP1 = rng.uniform(0.10, 0.35) * P_rated
        ramp1 = _lu(rng, 2e-3, 20e-3)
    else:
        dP1 = rng.uniform(0.30, 0.80) * P_rated
        ramp1 = _lu(rng, 0.5e-3, 10e-3)
    T1 = _lu(rng, 0.3, 3.0)
    duty1 = rng.uniform(0.3, 0.7)
    jit1 = rng.uniform(0.0, 0.02)
    P0 = rng.uniform(0.15, 0.6) * P_rated
    P0 = min(P0, 0.95 * P_rated - dP1)          # keep peak inside the sweep
    edp = None
    if background == "train" and rng.uniform() < 0.6:
        T2_hi = min(200e-3, duty1 * T1 / 3.0)
        if T2_hi > 20e-3:
            edp = dict(T2=_lu(rng, 20e-3, T2_hi), duty2=rng.uniform(0.3, 0.7),
                       dP2=rng.uniform(0.05, 0.25) * P_rated,
                       ramp2=_lu(rng, 0.5e-3, 5e-3), jit2=rng.uniform(0.0, 0.02),
                       off2=rng.uniform(0.02, 0.10) * T1)
    if background == "train":
        t_pre = 2.5 * T1 + 0.1
    else:
        t_pre = 60e-3
        P0 = rng.uniform(0.3, 0.9) * P_rated
    t_event = t_pre
    sched = build_schedule(t_pre, t_event, T_POST)
    t = sched["t"]
    edges, edges2 = [], []
    composite = False
    sched_tier = 0
    if background == "train":
        if label == "benign_train":
            if edp is not None and rng.uniform() < 0.5:
                # event = an EDP rising edge: choose burst index m inside a compute phase
                sched_tier = 2
                m = int(rng.integers(0, max(1, int((duty1 * T1 - edp["off2"]) / edp["T2"]))))
                # tier-1 rising edge such that burst m lands at t_event (before burst jitter)
                t_grid1 = t_event - edp["off2"] - m * edp["T2"]
                P, edges, edges2 = two_tier_profile(t, P0, dP1, T1, duty1, ramp1, jit1,
                                                    t_grid1, rng, edp, jit_k0=0.0, pin2=t_event)
            else:
                sched_tier = 1
                j0 = rng.uniform(-jit1, jit1) * T1
                t_grid1 = t_event - j0                       # grid such that jittered edge = t_event
                P, edges, edges2 = two_tier_profile(t, P0, dP1, T1, duty1, ramp1, jit1,
                                                    t_grid1, rng, edp, jit_k0=j0)
        else:
            composite = rng.uniform() < 0.35
            for _ in range(50):
                t_grid1 = t_event - rng.uniform(0.0, 1.0) * T1
                P, edges, edges2 = two_tier_profile(t, P0, dP1, T1, duty1, ramp1, jit1,
                                                    t_grid1, rng, edp)
                allr = np.array(edges + edges2)
                allr = allr[(allr > 0) & (allr < t_event)]
                if allr.size == 0:
                    continue
                d = t_event - allr.max()
                r_near = ramp1 if (allr.max() in edges) else (edp["ramp2"] if edp else ramp1)
                if composite and d <= min(r_near, 3e-3):
                    break
                if (not composite) and d >= 1.2 * r_near:
                    break
    else:
        P = np.full(t.shape[0], P0)
        if label in FAULTS:
            composite = rng.uniform() < 0.35
            if composite:
                ts = t_event - rng.uniform(0.0, min(ramp1, 3e-3))
                P = P + dP1 * _ramp(t, ts, ramp1)
                edges = [ts]
    wl = dict(period=T1 if background == "train" else 0.0, dP_bg=dP1, t_ramp_bg=ramp1,
              P0=P0, workload="v1", smoothed=bool(smoothed),
              T1=T1 if background == "train" else 0.0,
              T2=(edp["T2"] if edp else 0.0), dP2=(edp["dP2"] if edp else 0.0),
              ramp2=(edp["ramp2"] if edp else 0.0),
              sched_tier=sched_tier, jit1=jit1, duty1=duty1)
    return P, edges, edges2, sched, t_event, composite, wl


# ---------------------------------------------------------------- events

def draw_event(label, seed):
    """Draw one event: system params, background workload, event params and
    the profiles needed by the core. Returns dict (see keys below).
    Retries the system draw until the sanity gate passes; the number of
    rejected draws is recorded (gate-1 log)."""
    rng = np.random.default_rng(seed)
    n_rejected = 0
    while True:
        p = draw_system(rng)
        ok, margin = sanity_gate(p)
        if ok:
            break
        n_rejected += 1
    p["zeta"] = margin

    ev = dict(label=label, seed=seed, n_rejected=n_rejected)
    P_rated = p["P_rated"]

    # background workload: flat or periodic train
    if label == "benign_train":
        background = "train"
    elif label == "benign_step":
        background = "flat"
    else:
        background = "train" if rng.uniform() < 0.5 else "flat"
    ev["background"] = background

    if WORKLOAD_VERSION == "v0.2":
        P, edges, sched, t_event, composite, wl = _workload_v02(rng, label, background, P_rated)
        edges2 = []
    else:
        P, edges, edges2, sched, t_event, composite, wl = _workload_v1(rng, label, background, P_rated)
    t = sched["t"]
    n = t.shape[0]
    ev["composite"] = composite
    ev.update(wl)
    dP_bg, t_ramp_bg, P0 = wl["dP_bg"], wl["t_ramp_bg"], wl["P0"]
    ev["edges2"] = edges2

    # ----- the event itself
    Varc = np.zeros(n)
    f_start, f_end = 10**9, 10**9
    p["R_f"], p["L_f"] = 5e-3, 2e-6
    p["arc_place"] = 0.0
    if label == "benign_step":
        dP = rng.uniform(0.10, 0.80) * P_rated * (1 if rng.uniform() < 0.8 else -1)
        dP = float(np.clip(dP, -0.9 * P0, 1.8 * P_rated - P0))
        t_ramp = _lu(rng, 0.5e-3, 10e-3)
        P = P + dP * _ramp(t, t_event, t_ramp)
        ev.update(dP=dP, t_ramp=t_ramp)
    elif label == "benign_train":
        if ev.get("sched_tier", 0) == 2:
            ev.update(dP=ev["dP2"], t_ramp=ev.get("ramp2", t_ramp_bg))
        else:
            ev.update(dP=dP_bg, t_ramp=t_ramp_bg)
    elif label == "benign_idle_drop":
        frac = rng.uniform(0.50, 0.85)
        t_ramp = _lu(rng, 1e-3, 5e-3)
        Pnow = P[sched["idx_event"]]
        P = np.where(t >= t_event, P - frac * Pnow * _ramp(t, t_event, t_ramp), P)
        ev.update(dP=-frac * Pnow, t_ramp=t_ramp)
    elif label in ("bolted_pp", "resistive_pp", "high_z"):
        if label == "bolted_pp":
            p["R_f"] = _lu(rng, 1e-3, 20e-3)
        elif label == "resistive_pp":
            p["R_f"] = _lu(rng, 20e-3, 1.0)
        else:
            p["R_f"] = _lu(rng, 1.0, 10.0)
        p["L_f"] = _lu(rng, 0.5e-6, 10e-6)
        f_start = sched["idx_event"]
        f_end = min(n, f_start + int(round(FAULT_DURATION / DT_FINE)))
        ev.update(R_f=p["R_f"], L_f=p["L_f"])
    elif label == "series_arc":
        V_arc0 = rng.uniform(15.0, 40.0)
        m_arc = rng.uniform(0.05, 0.25)
        f_hi = _lu(rng, 50e3, 1e6)
        t_on = _lu(rng, 0.1e-3, 2e-3)
        place = 1.0 if rng.uniform() < 0.5 else 0.0   # 1 = line (upstream of C_bus)
        p["arc_place"] = place
        # noise generated on a uniform 20 MSa/s grid across the fine window
        # and on the coarse grid after it; stitched by interpolation in time
        eta = np.zeros(n)
        i0, i1 = sched["idx_fine_start"], sched["idx_fine_end"]
        eta[i0:i1] = arc_noise(i1 - i0, DT_FINE, 1e3, f_hi, m_arc * V_arc0, rng)
        eta[i1:] = arc_noise(n - i1, DT_COARSE, 1e3, min(f_hi, 0.4 / DT_COARSE),
                             m_arc * V_arc0, rng)
        Varc = (V_arc0 + eta) * _ramp(t, t_event, t_on)
        Varc = np.where(t >= t_event, Varc, 0.0)
        ev.update(V_arc0=V_arc0, m_arc=m_arc, f_arc_hi=f_hi, t_arc_on=t_on,
                  arc_place=place)
    else:
        raise ValueError(label)

    ev.update(params=p, sched=sched, P=P, Varc=Varc,
              fault_start=f_start, fault_end=f_end, edges=edges,
              t_event=t_event)
    return ev
