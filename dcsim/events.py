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

DT_COARSE = 2e-6      # s, history / post-event (fastest healthy tau_c = 16 us)
DT_FINE = 5e-8        # s, event window (fault-branch tau_f down to 0.2 us)
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
                   fine_pre=FINE_PRE, fine_post=FINE_POST):
    """Segmented time base (§8). Coarse from 0 to t_pre (history), the event
    anchor at t_event = t_pre, fine from t_event - fine_pre to
    t_event + fine_post, coarse to t_event + t_post. Returns dict with
    dt (n,), t (n,), idx_event, idx_fine_start, idx_fine_end."""
    assert abs(t_pre - t_event) < 1e-12, "anchor is placed at t_pre"
    n_c1 = int(round((t_pre - fine_pre) / dt_coarse))
    n_f = int(round((fine_pre + fine_post) / dt_fine))
    n_c2 = int(round((t_post - fine_post) / dt_coarse))
    dt = np.concatenate([np.full(n_c1, dt_coarse),
                         np.full(n_f, dt_fine),
                         np.full(n_c2, dt_coarse)])
    t = np.concatenate([[0.0], np.cumsum(dt)[:-1]])
    idx_fine_start = n_c1
    idx_event = n_c1 + int(round(fine_pre / dt_fine))
    idx_fine_end = n_c1 + n_f
    return dict(dt=dt, t=t, idx_event=idx_event,
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

    period = _lu(rng, 20e-3, 200e-3)
    duty = rng.uniform(0.3, 0.7)
    t_ramp_bg = _lu(rng, 0.5e-3, 10e-3)
    dP_bg = rng.uniform(0.10, 0.80) * P_rated
    jitter = rng.uniform(0.0, 0.05)
    P0 = rng.uniform(0.15, 0.6) * P_rated  # idle-ish floor (train) or base

    if background == "train":
        t_pre = 2.5 * period + 20e-3
    else:
        t_pre = 60e-3
        P0 = rng.uniform(0.3, 0.9) * P_rated
    t_event = t_pre
    sched = build_schedule(t_pre, t_event, T_POST)
    t = sched["t"]
    n = t.shape[0]

    # ----- build power profile
    edges = []
    composite = False
    if background == "train":
        if label == "benign_train":
            t_last_edge = t_event                       # the event IS the edge
        else:
            # event lands at a random phase; >=30% composite (inside a ramp)
            composite = rng.uniform() < 0.35
            if composite:
                t_last_edge = t_event - rng.uniform(0.0, min(t_ramp_bg, 3e-3))
            else:
                t_last_edge = t_event - rng.uniform(1.2 * t_ramp_bg, 0.9 * period)
                t_last_edge = t_event - (t_event - t_last_edge) % period
        P, edges = train_profile(t, P0, dP_bg, period, duty, t_ramp_bg, jitter,
                                 rng, t_last_edge)
    else:
        P = np.full(n, P0)
        if label in FAULTS:
            composite = rng.uniform() < 0.35
            if composite:
                ts = t_event - rng.uniform(0.0, min(t_ramp_bg, 3e-3))
                P = P + dP_bg * _ramp(t, ts, t_ramp_bg)
                edges = [ts]
    ev["composite"] = composite
    ev["period"] = period if background == "train" else 0.0
    ev["dP_bg"] = dP_bg
    ev["t_ramp_bg"] = t_ramp_bg
    ev["P0"] = P0

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
