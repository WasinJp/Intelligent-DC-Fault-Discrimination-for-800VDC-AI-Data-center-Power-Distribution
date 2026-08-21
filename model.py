"""dcsim.model — 800 VDC distribution segment physics core.

Implements MODEL.md v0.1 exactly. States: v_c, i_L, v_bus, i_fault.
Pristine physics only — sensor synthesis lives elsewhere (MODEL.md section 7).
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
)


def param_vector(p):
    """Pack params dict into the float64 vector consumed by the jitted core."""
    keys = ("V_ref", "R_droop", "tau_c", "C_bus", "L_line", "R_line",
            "V_uvlo", "t_uvlo_delay", "V_hyst", "I_lim", "R_esr", "R_f", "L_f")
    return np.array([p[k] for k in keys], dtype=np.float64)


# ---------------------------------------------------------------- physics core

@njit(cache=True)
def _derivs(t, y, pv, P_cmd, fault_on, load_on):
    """State derivatives per MODEL.md section 4. y = [v_c, i_L, v_bus, i_f]."""
    (V_ref, R_droop, tau_c, C_bus, L_line, R_line,
     V_uvlo, t_uvlo_delay, V_hyst, I_lim, R_esr, R_f, L_f) = pv
    v_c, i_L, v_C, i_f = y

    # 4.1 source converter: droop + first-order lag
    dv_c = (V_ref - R_droop * i_L - v_c) / tau_c

    # 4.4 CPL load bank with UVLO floor (shedding handled by load_on flag)
    # denominator uses v_C to break the ESR algebraic loop (error ~ R_esr*i_C)
    if load_on:
        denom = v_C if v_C > V_uvlo else V_uvlo
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
    di_L = (v_c - R_line * i_L - v_bus) / L_line
    if i_L >= I_lim and di_L > 0.0:
        di_L = 0.0

    # 4.3 bus node KCL (capacitor state)
    dv_C = i_C / C_bus

    return np.array([dv_c, di_L, dv_C, di_f])


@njit(cache=True)
def simulate(pv, dt, n_steps, P_profile, fault_start_idx, fault_end_idx):
    """Fixed-step RK4 over n_steps. P_profile: commanded power per step.

    Returns t, v_c, i_L, v_bus, i_f, i_load arrays plus load_shed mask.
    UVLO shedding per MODEL.md 4.4: shed after v_bus < V_uvlo persists
    t_uvlo_delay; recover after v_bus > V_uvlo + V_hyst (re-ramp omitted in
    skeleton — recovery restores commanded power directly, flagged OPEN-2).
    """
    (V_ref, R_droop, tau_c, C_bus, L_line, R_line,
     V_uvlo, t_uvlo_delay, V_hyst, I_lim, R_esr, R_f, L_f) = pv

    y = np.empty(4)
    # steady-state init at P_profile[0]
    I0 = P_profile[0] / V_ref
    y[0] = V_ref - R_droop * I0
    y[1] = I0
    y[2] = y[0] - R_line * I0
    y[3] = 0.0

    t_out = np.empty(n_steps)
    out = np.empty((5, n_steps))
    load_on = True
    uvlo_timer = 0.0

    for k in range(n_steps):
        t = k * dt
        P_cmd = P_profile[k]
        f_on = fault_start_idx <= k < fault_end_idx

        # observable bus voltage for supervisory logic
        denom0 = y[2] if y[2] > V_uvlo else V_uvlo
        i_load0 = (P_cmd / denom0) if load_on else 0.0
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

        k1 = _derivs(t, y, pv, P_cmd, f_on, load_on)
        k2 = _derivs(t, y + 0.5 * dt * k1, pv, P_cmd, f_on, load_on)
        k3 = _derivs(t, y + 0.5 * dt * k2, pv, P_cmd, f_on, load_on)
        k4 = _derivs(t, y + dt * k3, pv, P_cmd, f_on, load_on)
        y = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        if not f_on:
            y[3] = 0.0
        if y[2] < 0.0:          # freewheel clamp (OPEN-6)
            y[2] = 0.0

        denom = y[2] if y[2] > V_uvlo else V_uvlo
        i_load = (P_cmd / denom) if load_on else 0.0

        t_out[k] = t
        out[0, k] = y[0]
        out[1, k] = y[1]
        vb = y[2] + R_esr * (y[1] - i_load - y[3])          # v_bus observable
        out[2, k] = vb if vb > 0.0 else 0.0
        out[3, k] = y[3]
        out[4, k] = i_load

    return t_out, out


# ---------------------------------------------------------------- events

def benign_step(p, dP, t_ramp, t0, t_total, dt):
    """MODEL.md section 5 `benign_step`: P(t) = P0 + dP * min(1,(t-t0)/t_ramp)."""
    n = int(round(t_total / dt))
    t = np.arange(n) * dt
    P0 = p["P_rated"]
    ramp = np.clip((t - t0) / t_ramp, 0.0, 1.0)
    return P0 + dP * ramp, n


def bolted_fault_window(t_f, t_clear, t_total, dt):
    n = int(round(t_total / dt))
    return int(round(t_f / dt)), int(round(t_clear / dt)), n


# ---------------------------------------------------------------- validation

def check_droop_steady_state(p, tol=1e-6):
    """MODEL.md section 8 validation (b): v_bus = V_ref - (R_droop+R_line) I."""
    pv = param_vector(p)
    P = np.full(200_000, p["P_rated"])
    _, out = simulate(pv, 1e-6, 200_000, P, 10**9, 10**9)
    I = p["P_rated"] / out[2, -1]
    v_pred = p["V_ref"] - (p["R_droop"] + p["R_line"]) * I
    err = abs(out[2, -1] - v_pred) / p["V_ref"]
    return err, err < 1e-4


def check_rlc_discharge(p, tol=1e-3):
    """MODEL.md section 8 validation (a): C_bus discharge into R_f-L_f vs analytic.

    Source and load disconnected: series RLC, v_bus(0)=V0, i_f(0)=0.
    """
    C, R, L, V0 = p["C_bus"], p["R_f"], p["L_f"], p["V_ref"]
    dt, n = 5e-8, 4_000    # 0.2 ms: before v_C first zero (clamp never engages)
    pv = param_vector({**p, "R_droop": 0.0, "tau_c": 1.0, "R_line": 0.0,
                       "V_ref": V0, "V_uvlo": 1.0, "R_esr": 0.0,
                       "t_uvlo_delay": 1.0, "V_hyst": 0.0, "I_lim": 0.0,
                       "R_f": R, "L_f": L, "C_bus": C})
    P = np.zeros(n)
    t, out = simulate(pv, dt, n, P, 0, n)
    i_num = out[3]

    alpha = R / (2 * L)
    w0sq = 1.0 / (L * C)
    wd = np.sqrt(w0sq - alpha**2)          # baseline draw is underdamped
    i_ana = (V0 / (wd * L)) * np.exp(-alpha * t) * np.sin(wd * t)
    rms = np.sqrt(np.mean((i_num - i_ana) ** 2)) / np.max(np.abs(i_ana))
    return rms, rms < tol
