"""dcsim.model — 800 VDC distribution segment physics core.

Implements MODEL.md v0.2. States: v_c, i_L, v_C, i_fault.
Pristine physics only — sensor synthesis lives in dcsim.synth (MODEL.md §7).

v0.2 additions over v0.1.1 (see MODEL.md revision log):
  * segmented time base: per-step dt array (§8), coarse outside events, fine inside
  * series-arc element in the load path (§4.6): i_load = P / (v - V_arc(t))
  * fault window and arc profile are step-indexed like P_profile
"""

import numpy as np
from numba import njit

# ---------------------------------------------------------------- parameters

PARAMS_BASELINE = dict(
    V_ref=800.0,        # V
    P_rated=200e3,      # W
    R_droop=16e-3,      # ohm (0.5%)
    tau_c=80e-6,        # s (~2 kHz control BW)
    C_bus=10e-3,        # F
    L_line=5e-6,        # H
    R_line=5e-3,        # ohm
    V_uvlo=640.0,       # V
    t_uvlo_delay=100e-6,  # s
    V_hyst=20.0,        # V
    I_lim=1.75 * 200e3 / 800.0,  # A (OPEN-1 clamp, 1.75 x I_rated)
    R_esr=8e-3,         # ohm (bus capacitor bank ESR)
    R_f=5e-3,           # ohm (fault branch, when active)
    L_f=2e-6,           # H
    arc_place=0.0,      # 0 = series arc in load path (downstream of C_bus),
                        # 1 = series arc in the busbar (upstream of C_bus)
)

PARAM_KEYS = ("V_ref", "R_droop", "tau_c", "C_bus", "L_line", "R_line",
              "V_uvlo", "t_uvlo_delay", "V_hyst", "I_lim", "R_esr", "R_f", "L_f",
              "arc_place")


def param_vector(p):
    """Pack params dict into the float64 vector consumed by the jitted core."""
    return np.array([p[k] for k in PARAM_KEYS], dtype=np.float64)


# ---------------------------------------------------------------- physics core

@njit(cache=True)
def _derivs(y, pv, P_cmd, V_arc, fault_on, load_on):
    """State derivatives per MODEL.md §4. y = [v_c, i_L, v_C, i_f]."""
    (V_ref, R_droop, tau_c, C_bus, L_line, R_line,
     V_uvlo, t_uvlo_delay, V_hyst, I_lim, R_esr, R_f, L_f, arc_place) = pv
    v_c, i_L, v_C, i_f = y
    V_arc_load = V_arc if arc_place < 0.5 else 0.0
    V_arc_line = V_arc if arc_place >= 0.5 else 0.0

    # 4.1 source converter: droop + first-order lag
    dv_c = (V_ref - R_droop * i_L - v_c) / tau_c

    # 4.4 CPL load bank with UVLO floor (shedding handled by load_on flag)
    # 4.6 series arc in the load path drops V_arc before the rack converters.
    # denominator uses v_C to break the ESR algebraic loop (error ~ R_esr*i_C)
    if load_on:
        v_eff = v_C - V_arc_load
        denom = v_eff if v_eff > V_uvlo else V_uvlo
        i_load = P_cmd / denom
    else:
        i_load = 0.0

    # bus node voltage (algebraic, cap ESR): v_bus = v_C + R_esr * i_C
    # freewheel diodes pin the node at ~0 V (OPEN-6)
    i_C = i_L - i_load - i_f
    v_bus = v_C + R_esr * i_C
    if v_bus < 0.0:
        v_bus = 0.0

    # 4.5 fault branch (freewheel clamp: bus cannot drive i_f below zero
    # once converter body diodes clamp reverse polarity — OPEN-6)
    if fault_on:
        di_f = (v_bus - R_f * i_f) / L_f
        if v_C <= 0.0 and di_f < 0.0 and i_f <= 0.0:
            di_f = 0.0
    else:
        di_f = 0.0

    # 4.2 busbar (with OPEN-1 source current clamp applied as di limit)
    di_L = (v_c - R_line * i_L - V_arc_line - v_bus) / L_line
    if i_L >= I_lim and di_L > 0.0:
        di_L = 0.0
    if i_L <= 0.0 and di_L < 0.0:   # unidirectional source shelf (OPEN-7)
        di_L = 0.0

    # 4.3 bus node KCL (capacitor state)
    dv_C = i_C / C_bus

    return np.array([dv_c, di_L, dv_C, di_f])


@njit(cache=True)
def simulate(pv, dt_arr, P_profile, Varc_profile, fault_start_idx, fault_end_idx):
    """Fixed-schedule RK4 over len(dt_arr) steps (§8 segmented time base).

    dt_arr[k]        step size used to advance from step k to k+1
    P_profile[k]     commanded load power at step k
    Varc_profile[k]  series-arc voltage at step k (0 when no arc)
    fault window     [fault_start_idx, fault_end_idx) in step index

    Returns t (n,), out (6, n): v_c, i_L, v_bus, i_f, i_load, load_on.
    UVLO shedding per MODEL.md §4.4; recovery restores commanded power
    directly (re-ramp omitted, OPEN-2).
    """
    (V_ref, R_droop, tau_c, C_bus, L_line, R_line,
     V_uvlo, t_uvlo_delay, V_hyst, I_lim, R_esr, R_f, L_f, arc_place) = pv

    n_steps = dt_arr.shape[0]
    y = np.empty(4)
    # steady-state init at P_profile[0]
    I0 = P_profile[0] / V_ref
    y[0] = V_ref - R_droop * I0
    y[1] = I0
    y[2] = y[0] - R_line * I0
    y[3] = 0.0

    t_out = np.empty(n_steps)
    out = np.empty((6, n_steps))
    load_on = True
    uvlo_timer = 0.0
    t = 0.0

    for k in range(n_steps):
        dt = dt_arr[k]
        P_cmd = P_profile[k]
        V_arc = Varc_profile[k]
        f_on = fault_start_idx <= k < fault_end_idx

        # observable bus voltage for supervisory logic
        if load_on:
            v_eff0 = y[2] - (V_arc if arc_place < 0.5 else 0.0)
            denom0 = v_eff0 if v_eff0 > V_uvlo else V_uvlo
            i_load0 = P_cmd / denom0
        else:
            i_load0 = 0.0
        v_bus_obs = y[2] + R_esr * (y[1] - i_load0 - y[3])
        if v_bus_obs < 0.0:
            v_bus_obs = 0.0

        # UVLO state machine
        if v_bus_obs < V_uvlo:
            uvlo_timer += dt
            if uvlo_timer >= t_uvlo_delay:
                load_on = False
        else:
            uvlo_timer = 0.0
            if (not load_on) and y[2] > V_uvlo + V_hyst:
                load_on = True

        # record state at step k (before advancing)
        t_out[k] = t
        out[0, k] = y[0]
        out[1, k] = y[1]
        out[2, k] = v_bus_obs
        out[3, k] = y[3]
        out[4, k] = i_load0
        out[5, k] = 1.0 if load_on else 0.0

        k1 = _derivs(y, pv, P_cmd, V_arc, f_on, load_on)
        k2 = _derivs(y + 0.5 * dt * k1, pv, P_cmd, V_arc, f_on, load_on)
        k3 = _derivs(y + 0.5 * dt * k2, pv, P_cmd, V_arc, f_on, load_on)
        k4 = _derivs(y + dt * k3, pv, P_cmd, V_arc, f_on, load_on)
        y = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        if not f_on:
            y[3] = 0.0
        if y[2] < 0.0:          # freewheel clamp (OPEN-6)
            y[2] = 0.0
        t += dt

    return t_out, out


# ---------------------------------------------------------------- helpers

def uniform_schedule(t_total, dt):
    """Convenience: uniform dt array for validation runs."""
    n = int(round(t_total / dt))
    return np.full(n, dt, dtype=np.float64)


def run_uniform(p, dt, t_total, P_profile=None, Varc=None,
                fault_start=None, fault_end=None):
    """Run the core on a uniform grid. Returns t, out."""
    pv = param_vector(p)
    dt_arr = uniform_schedule(t_total, dt)
    n = dt_arr.shape[0]
    if P_profile is None:
        P_profile = np.full(n, p["P_rated"])
    if Varc is None:
        Varc = np.zeros(n)
    fs = 10**9 if fault_start is None else int(round(fault_start / dt))
    fe = 10**9 if fault_end is None else int(round(fault_end / dt))
    return simulate(pv, dt_arr, P_profile, Varc, fs, fe)


# ---------------------------------------------------------------- validation

def check_droop_steady_state(p, tol=1e-4):
    """MODEL.md §8 validation (b): v_bus = V_ref - (R_droop+R_line) I."""
    _, out = run_uniform(p, 1e-6, 0.2)
    I = p["P_rated"] / out[2, -1]
    v_pred = p["V_ref"] - (p["R_droop"] + p["R_line"]) * I
    err = abs(out[2, -1] - v_pred) / p["V_ref"]
    return err, err < tol


def check_rlc_discharge(p, tol=1e-3):
    """MODEL.md §8 validation (a): C_bus discharge into R_f-L_f vs analytic.

    Source and load disconnected: series RLC, v_bus(0)=V0, i_f(0)=0.
    """
    C, R, L, V0 = p["C_bus"], p["R_f"], p["L_f"], p["V_ref"]
    dt, n = 5e-8, 4_000    # 0.2 ms: before v_C first zero (clamp never engages)
    q = {**p, "R_droop": 0.0, "tau_c": 1.0, "R_line": 0.0,
         "V_ref": V0, "V_uvlo": 1.0, "R_esr": 0.0,
         "t_uvlo_delay": 1.0, "V_hyst": 0.0, "I_lim": 0.0,
         "R_f": R, "L_f": L, "C_bus": C}
    t, out = run_uniform(q, dt, n * dt, P_profile=np.zeros(n),
                         fault_start=0.0, fault_end=n * dt)
    i_num = out[3]

    alpha = R / (2 * L)
    w0sq = 1.0 / (L * C)
    wd = np.sqrt(w0sq - alpha**2)          # baseline draw is underdamped
    i_ana = (V0 / (wd * L)) * np.exp(-alpha * t) * np.sin(wd * t)
    rms = np.sqrt(np.mean((i_num - i_ana) ** 2)) / np.max(np.abs(i_ana))
    return rms, rms < tol


def check_segmented_vs_uniform(p, tol=1e-3):
    """v0.2 validation (c): segmented schedule must reproduce the uniform
    fine-step solution inside the event window. High-Z fault (stiffest
    fault-branch case, tau_f = 0.2 us) injected at 1 ms."""
    from .events import build_schedule
    q = {**p, "R_f": 10.0, "L_f": 2e-6}
    pv = param_vector(q)
    t_f = 1.0e-3
    dt_u = 5e-8
    t_tot = 3e-3
    n_u = int(round(t_tot / dt_u))
    P_u = np.full(n_u, p["P_rated"])
    t_u, out_u = simulate(pv, np.full(n_u, dt_u), P_u, np.zeros(n_u),
                          int(round(t_f / dt_u)), n_u)
    sched = build_schedule(t_pre=t_f, t_event=t_f, t_post=2e-3,
                           dt_coarse=2e-6, dt_fine=dt_u,
                           fine_pre=0.2e-3, fine_post=2e-3)
    n_s = sched["dt"].shape[0]
    P_s = np.full(n_s, p["P_rated"])
    t_s, out_s = simulate(pv, sched["dt"], P_s, np.zeros(n_s),
                          sched["idx_event"], n_s)
    m = (t_u >= t_f) & (t_u <= t_f + 1.5e-3)
    v_s = np.interp(t_u[m], t_s, out_s[2])
    i_s = np.interp(t_u[m], t_s, out_s[1])
    err_v = np.sqrt(np.mean((out_u[2][m] - v_s) ** 2)) / p["V_ref"]
    err_i = np.sqrt(np.mean((out_u[1][m] - i_s) ** 2)) / (p["P_rated"] / p["V_ref"])
    err = max(err_v, err_i)
    return err, err < tol


def check_history_tier(p, tol=1e-3):
    """v0.3 validation (d): the DT_HIST history tier must reproduce the
    all-coarse (2 us) solution on the slow-stream timescale. A two-tier
    benign train (T1 = 0.3 s, EDP bursts) is run both ways at (i) the given
    parameters with smoothed 3 ms ramps and (ii) the stiffest corner of the
    §6 sweep (tau_c = 16 us, L = 1 uH, C = 1 mF, zeta ~ 0.2) with 0.5 ms
    ramps; line current and bus voltage, low-passed at 2 kHz (the slow-stream
    anti-alias), must agree to tol (normalised RMS). Returns the worse of the
    two. At DT_HIST = 10 us: ~1e-4 baseline, ~3.5e-4 stiff corner; 20 us
    passes the corner with no margin and 40 us fails it."""
    from .events import build_schedule, two_tier_profile
    from scipy import signal as _sig
    stiff = dict(p)
    stiff.update(tau_c=16e-6, L_line=1e-6, C_bus=1e-3, R_line=1e-3, R_esr=2e-3)
    stiff["R_droop"] = 0.004 * stiff["V_ref"] / (stiff["P_rated"] / stiff["V_ref"])
    worst = 0.0
    for q, ramp1, dP1 in ((p, 3e-3, 0.4), (stiff, 0.5e-3, 0.6)):
        T1, duty1 = 0.3, 0.5
        t_pre = 2.5 * T1 + 0.1
        edp = dict(T2=40e-3, duty2=0.5, dP2=0.15 * q["P_rated"], ramp2=ramp1, jit2=0.0, off2=0.03 * T1)
        pv = param_vector(q)
        outs = []
        for use_hist in (False, True):
            sched = build_schedule(t_pre, t_pre, 6e-3, fine_post=1e-3, use_hist=use_hist)
            t = sched["t"]
            P, _, _ = two_tier_profile(t, 0.3 * q["P_rated"], dP1 * q["P_rated"], T1, duty1, ramp1, 0.0,
                                       t_pre, np.random.default_rng(11), edp, jit_k0=0.0)
            tt, out = simulate(pv, sched["dt"], P, np.zeros(t.size), 10**9, 10**9)
            outs.append((tt, out))
        tu = np.arange(0.0, t_pre - 0.25, 20e-6)
        sos = _sig.butter(4, 2e3, fs=1.0 / 20e-6, output="sos")
        for ch, scale in ((1, q["P_rated"] / q["V_ref"]), (2, q["V_ref"])):
            a = _sig.sosfiltfilt(sos, np.interp(tu, outs[0][0], outs[0][1][ch]))
            b = _sig.sosfiltfilt(sos, np.interp(tu, outs[1][0], outs[1][1][ch]))
            worst = max(worst, np.sqrt(np.mean((a - b) ** 2)) / scale)
    return worst, worst < tol
