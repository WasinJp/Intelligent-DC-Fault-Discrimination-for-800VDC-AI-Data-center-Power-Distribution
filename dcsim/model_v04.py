"""dcsim.model_v04 — 800 VDC distribution segment WITH the rack conversion stage.

Implements MODEL.md v0.4 (see MODEL_v0.4_conversion_stage_spec.md). The v0.3
core (dcsim.model) is left untouched so dataset v1 remains reproducible;
dcsim.dataset selects the core by MODEL_VERSION.

States y (11):
   0 v_c     source converter output voltage (droop + lag)          [v0.3]
   1 i_L     feeder current                                          [v0.3]
   2 v_C     800 V bus capacitor voltage (distribution capacitance)  [v0.3, new meaning]
   3 i_f     800 V fault-branch current                              [v0.3]
   4 i_Lin   rack input inductor current (draw from the 800 V bus)
   5 v_Cin   rack input storage capacitor voltage ("65 J/GPU" element)
   6 P_cmd   ramp-rate-limited bus-side power command (charge-management front end)
   7 xi_v    outer 48 V voltage-loop integrator
   8 i_co    converter output current (inner current loop, first-order lag)
   9 v_out   48 V bus capacitor voltage
  10 i_f48   48 V fault-branch current

v0.4.1 topology (corrects v0.4): the rack input is a passive L_in-C_in filter
(C_in small: bulk/EMI, 0.1-5 mF) behind an ORing stage (i_Lin >= 0, the
shelf cannot back-feed the bus). The large energy storage sits on the 48 V
OUTPUT side as C_out (65 J/GPU at 50 V is ~3.7 F per 72-GPU rack). The
converter is averaged: P_in = P_out + P_loss(P_out). With smoothing ON the
converter's INPUT power draw is rate-limited (P_cmd chases the loop's demand
at <= S_max); the output can then deliver at most eta*P_cmd and the output
storage supplies the deficit. With smoothing OFF the converter delivers what
the voltage loop asks, up to I_lim_out, and draws it instantly.
Bus-side storage (a capacitance shelf, or a BBU without reverse blocking) is
a separate sweep flag: it is added to C_bus, directly on the bus, and CAN
feed a bus fault.

Outputs out (15, n): v_c, i_L, v_bus, i_f, i_in, conv_on, i_Lin, v_Cin,
i_co, v_out_node, i_f48, i_pol, load_on48, P_in, i_rack.
Feeder observables: i_L, v_bus. Rack-node observables: i_rack (load-side
48 V busbar current = i_pol + i_f48, downstream of the storage), v_out_node.
"""

import numpy as np
from numba import njit

# ---------------------------------------------------------------- parameters

PARAMS_BASELINE = dict(
    # --- 800 V side (v0.3 names; C_bus is now distribution capacitance only)
    V_ref=800.0, P_rated=132e3, R_droop=16e-3 * 200e3 / 132e3, tau_c=80e-6,
    C_bus=0.5e-3, L_line=5e-6, R_line=5e-3, R_esr=8e-3,
    V_uvlo=640.0, t_uvlo_delay=100e-6, V_hyst=20.0,
    I_lim=1.75 * 132e3 / 800.0, R_f=5e-3, L_f=2e-6, arc_place=0.0,
    # --- rack input filter (passive; ORing prevents back-feed)
    L_in=5e-6, R_in=3e-3, C_in=1e-3, R_in_esr=8e-3,
    # --- converter-input ramp-rate limiter (power smoothing); output storage supplies the deficit
    smooth_on=1.0, S_max=100e3 / 1e-3, tau_r=200e-6,
    # --- converter loss model P_loss = p_fix*P_rated + k2*P_out^2/P_rated
    p_fix=0.01012, k2=0.01028,
    # --- 48 V bus and control
    V_ref48=50.0, C_out=3.7, R_out_esr=0.3e-3, f_v=100.0, zeta_v=0.7, tau_i=20e-6,
    I_lim_out=1.4 * 132e3 / 50.0,
    V_uvlo48=40.0, t_uvlo48=100e-6, V_hyst48=2.0,
    R_f48=2e-3, L_f48=0.5e-6,
)

PARAM_KEYS = ("V_ref", "P_rated", "R_droop", "tau_c", "C_bus", "L_line", "R_line", "R_esr",
              "V_uvlo", "t_uvlo_delay", "V_hyst", "I_lim", "R_f", "L_f", "arc_place",
              "L_in", "R_in", "C_in", "R_in_esr",
              "smooth_on", "S_max", "tau_r",
              "p_fix", "k2",
              "V_ref48", "C_out", "R_out_esr", "K_p", "K_i", "tau_i", "I_lim_out",
              "V_uvlo48", "t_uvlo48", "V_hyst48", "R_f48", "L_f48")


def pi_tune(C_out, f_v, zeta):
    """Outer voltage-loop PI on a capacitor plant with an ideal inner current
    loop: closed loop s^2 C + K_p s + K_i = 0 -> w_n = sqrt(K_i/C),
    zeta = K_p / (2 sqrt(K_i C))."""
    w = 2.0 * np.pi * f_v
    K_i = C_out * w * w
    K_p = 2.0 * zeta * np.sqrt(K_i * C_out)
    return K_p, K_i


def param_vector(p):
    q = dict(p)
    if "K_p" not in q or "K_i" not in q:
        q["K_p"], q["K_i"] = pi_tune(q["C_out"], q["f_v"], q.get("zeta_v", 0.7))
    return np.array([q[k] for k in PARAM_KEYS], dtype=np.float64)


# ---------------------------------------------------------------- physics core

@njit(cache=True)
def _loss(P_out, P_rated, p_fix, k2):
    return p_fix * P_rated + k2 * P_out * P_out / P_rated


@njit(cache=True)
def _derivs(y, pv, P_gpu, V_arc, fault_on, fault48_on, conv_on, load_on48):
    (V_ref, P_rated, R_droop, tau_c, C_bus, L_line, R_line, R_esr,
     V_uvlo, t_uvlo_delay, V_hyst, I_lim, R_f, L_f, arc_place,
     L_in, R_in, C_in, R_in_esr,
     smooth_on, S_max, tau_r,
     p_fix, k2,
     V_ref48, C_out, R_out_esr, K_p, K_i, tau_i, I_lim_out,
     V_uvlo48, t_uvlo48, V_hyst48, R_f48, L_f48) = pv
    v_c, i_L, v_C, i_f, i_Lin, v_Cin, P_cmd, xi_v, i_co, v_out, i_f48 = y
    V_arc_load = V_arc if arc_place < 0.5 else 0.0     # series arc in the rack path (input side)
    V_arc_line = V_arc if arc_place >= 0.5 else 0.0

    # ---- 48 V side
    i_pol = 0.0
    if load_on48:
        i_pol = P_gpu / (v_out if v_out > V_uvlo48 else V_uvlo48)
    i_Cout = i_co - i_pol - i_f48
    v_out_node = v_out + R_out_esr * i_Cout
    if v_out_node < 0.0:
        v_out_node = 0.0
    err = V_ref48 - v_out
    i_ref = K_p * err + K_i * xi_v
    sat = i_ref
    if sat > I_lim_out:
        sat = I_lim_out
    if sat < 0.0:
        sat = 0.0
    # what the loop asks for at the input (demand), before any rate limit
    P_out_dem = v_out * sat
    if P_out_dem < 0.0:
        P_out_dem = 0.0
    P_req = P_out_dem + _loss(P_out_dem, P_rated, p_fix, k2) if conv_on else 0.0
    # ---- converter-input ramp-rate limiter (v0.4.1): P_cmd chases P_req at <= S_max
    dP_cmd = 0.0
    if smooth_on > 0.5:
        r = (P_req - P_cmd) / tau_r
        if r > S_max:
            r = S_max
        if r < -S_max:
            r = -S_max
        dP_cmd = r
        P_in_now = P_cmd if conv_on else 0.0
        # output is bounded by what the input delivers: P_out_max = P_in - loss(P_out_max)
        P_out_max = P_in_now - p_fix * P_rated
        if P_out_max < 0.0:
            P_out_max = 0.0
        i_co_max = P_out_max / (v_out if v_out > 1.0 else 1.0)
        if sat > i_co_max:
            sat = i_co_max
    else:
        P_in_now = P_req
    dxi = err if (sat == i_ref) else 0.0                # anti-windup: hold integrator when clamped
    di_co = (sat - i_co) / tau_i if conv_on else (0.0 - i_co) / tau_i
    dv_out = i_Cout / C_out
    di_f48 = 0.0
    if fault48_on:
        di_f48 = (v_out_node - R_f48 * i_f48) / L_f48
        if v_out <= 0.0 and di_f48 < 0.0 and i_f48 <= 0.0:
            di_f48 = 0.0

    # ---- input node: converter draws P_in_now from the storage/filter capacitor
    v_in_eff = v_Cin - V_arc_load
    i_in = P_in_now / (v_in_eff if v_in_eff > V_uvlo else V_uvlo) if conv_on else 0.0
    i_Cin = i_Lin - i_in
    v_Cin_node = v_Cin + R_in_esr * i_Cin

    # ---- 800 V bus node (algebraic, cap ESR)
    i_C = i_L - i_Lin - i_f
    v_bus = v_C + R_esr * i_C
    if v_bus < 0.0:
        v_bus = 0.0

    # ---- passive input filter with ORing (no back-feed)
    di_Lin = (v_bus - R_in * i_Lin - v_Cin_node) / L_in
    if i_Lin <= 0.0 and di_Lin < 0.0:
        di_Lin = 0.0
    dv_Cin = i_Cin / C_in

    # ---- 800 V fault branch and feeder (v0.3)
    di_f = 0.0
    if fault_on:
        di_f = (v_bus - R_f * i_f) / L_f
        if v_C <= 0.0 and di_f < 0.0 and i_f <= 0.0:
            di_f = 0.0
    dv_c = (V_ref - R_droop * i_L - v_c) / tau_c
    di_L = (v_c - R_line * i_L - V_arc_line - v_bus) / L_line
    if i_L >= I_lim and di_L > 0.0:
        di_L = 0.0
    if i_L <= 0.0 and di_L < 0.0:
        di_L = 0.0
    dv_C = i_C / C_bus

    return np.array([dv_c, di_L, dv_C, di_f, di_Lin, dv_Cin, dP_cmd, dxi, di_co, dv_out, di_f48])


@njit(cache=True)
def simulate(pv, dt_arr, P_profile, Varc_profile, fault_start_idx, fault_end_idx,
             fault48_start_idx, fault48_end_idx):
    """Fixed-schedule RK4 (§8). P_profile is the GPU (POL-level) power demand.
    Two UVLO state machines: the converter's input (on v_Cin, v0.3 thresholds)
    and the POL stage (on v_out). Returns t (n,), out (14, n)."""
    (V_ref, P_rated, R_droop, tau_c, C_bus, L_line, R_line, R_esr,
     V_uvlo, t_uvlo_delay, V_hyst, I_lim, R_f, L_f, arc_place,
     L_in, R_in, C_in, R_in_esr,
     smooth_on, S_max, tau_r,
     p_fix, k2,
     V_ref48, C_out, R_out_esr, K_p, K_i, tau_i, I_lim_out,
     V_uvlo48, t_uvlo48, V_hyst48, R_f48, L_f48) = pv

    n_steps = dt_arr.shape[0]
    # ---- steady-state init at P_profile[0]
    P0 = P_profile[0]
    i_co0 = P0 / V_ref48
    P_req0 = P0 + _loss(P0, P_rated, p_fix, k2)
    y = np.empty(11)
    y[9] = V_ref48
    y[8] = i_co0
    y[7] = i_co0 / K_i
    y[6] = P_req0
    # bus-side: i_L = i_Lin = P_req0 / v_Cin; solve the small droop chain iteratively
    i_L0 = P_req0 / V_ref
    for _ in range(20):
        v_c0 = V_ref - R_droop * i_L0
        v_C0 = v_c0 - R_line * i_L0
        v_Cin0 = v_C0 - R_in * i_L0
        i_L0 = P_req0 / v_Cin0
    v_c0 = V_ref - R_droop * i_L0
    v_C0 = v_c0 - R_line * i_L0
    v_Cin0 = v_C0 - R_in * i_L0
    y[0], y[1], y[2], y[3] = v_c0, i_L0, v_C0, 0.0
    y[4], y[5], y[10] = i_L0, v_Cin0, 0.0

    t_out = np.empty(n_steps)
    out = np.empty((15, n_steps))
    conv_on = True
    load_on48 = True
    uvlo_t = 0.0
    uvlo48_t = 0.0
    t = 0.0
    for k in range(n_steps):
        dt = dt_arr[k]
        P_gpu = P_profile[k]
        V_arc = Varc_profile[k]
        f_on = fault_start_idx <= k < fault_end_idx
        f48_on = fault48_start_idx <= k < fault48_end_idx

        # ---- observables for the supervisory logic (from current state)
        i_pol0 = 0.0
        if load_on48:
            i_pol0 = P_gpu / (y[9] if y[9] > V_uvlo48 else V_uvlo48)
        v_out_obs = y[9] + R_out_esr * (y[8] - i_pol0 - y[10])
        if v_out_obs < 0.0:
            v_out_obs = 0.0
        P_out0 = y[9] * y[8]
        if P_out0 < 0.0:
            P_out0 = 0.0
        P_req0 = P_out0 + _loss(P_out0, P_rated, p_fix, k2) if conv_on else 0.0
        P_in0 = (y[6] if smooth_on > 0.5 else P_req0) if conv_on else 0.0
        v_in_eff0 = y[5] - (V_arc if arc_place < 0.5 else 0.0)
        i_in0 = P_in0 / (v_in_eff0 if v_in_eff0 > V_uvlo else V_uvlo) if conv_on else 0.0
        v_bus_obs = y[2] + R_esr * (y[1] - y[4] - y[3])
        if v_bus_obs < 0.0:
            v_bus_obs = 0.0
        v_Cin_obs = y[5] + R_in_esr * (y[4] - i_in0)

        # ---- UVLO state machines
        if v_Cin_obs < V_uvlo:
            uvlo_t += dt
            if uvlo_t >= t_uvlo_delay:
                conv_on = False
        else:
            uvlo_t = 0.0
            if (not conv_on) and y[5] > V_uvlo + V_hyst:
                conv_on = True
        if v_out_obs < V_uvlo48:
            uvlo48_t += dt
            if uvlo48_t >= t_uvlo48:
                load_on48 = False
        else:
            uvlo48_t = 0.0
            if (not load_on48) and y[9] > V_uvlo48 + V_hyst48:
                load_on48 = True

        # ---- record
        t_out[k] = t
        out[0, k] = y[0]; out[1, k] = y[1]; out[2, k] = v_bus_obs; out[3, k] = y[3]
        out[4, k] = i_in0; out[5, k] = 1.0 if conv_on else 0.0
        out[6, k] = y[4]; out[7, k] = y[5]; out[8, k] = y[8]; out[9, k] = v_out_obs
        out[10, k] = y[10]; out[11, k] = i_pol0; out[12, k] = 1.0 if load_on48 else 0.0
        out[13, k] = P_in0
        out[14, k] = i_pol0 + y[10]                        # load-side 48 V busbar current (rack node)

        # ---- RK4
        k1 = _derivs(y, pv, P_gpu, V_arc, f_on, f48_on, conv_on, load_on48)
        k2_ = _derivs(y + 0.5 * dt * k1, pv, P_gpu, V_arc, f_on, f48_on, conv_on, load_on48)
        k3 = _derivs(y + 0.5 * dt * k2_, pv, P_gpu, V_arc, f_on, f48_on, conv_on, load_on48)
        k4 = _derivs(y + dt * k3, pv, P_gpu, V_arc, f_on, f48_on, conv_on, load_on48)
        y = y + (dt / 6.0) * (k1 + 2 * k2_ + 2 * k3 + k4)
        if not f_on:
            y[3] = 0.0
        if not f48_on:
            y[10] = 0.0
        if y[2] < 0.0:
            y[2] = 0.0
        if y[9] < 0.0:
            y[9] = 0.0
        if y[5] < 0.0:
            y[5] = 0.0
        t += dt
    return t_out, out


# ---------------------------------------------------------------- helpers

def uniform_schedule(t_total, dt):
    n = int(round(t_total / dt))
    return np.full(n, dt, dtype=np.float64)


def run_uniform(p, dt, t_total, P_profile=None, Varc=None,
                fault_start=None, fault_end=None, fault48_start=None, fault48_end=None):
    pv = param_vector(p)
    dt_arr = uniform_schedule(t_total, dt)
    n = dt_arr.shape[0]
    if P_profile is None:
        P_profile = np.full(n, p["P_rated"])
    if Varc is None:
        Varc = np.zeros(n)
    fs = 10**9 if fault_start is None else int(round(fault_start / dt))
    fe = 10**9 if fault_end is None else int(round(fault_end / dt))
    fs48 = 10**9 if fault48_start is None else int(round(fault48_start / dt))
    fe48 = 10**9 if fault48_end is None else int(round(fault48_end / dt))
    return simulate(pv, dt_arr, P_profile, Varc, fs, fe, fs48, fe48)


def sanity_gate_48(p, zeta_min=0.15):
    """Gate 1 extension: the 48 V voltage loop with the POL constant-power load.
    Closed loop s^2 C_out + (K_p - P/V^2) s + K_i = 0 must have zeta >= zeta_min."""
    K_p, K_i = pi_tune(p["C_out"], p["f_v"], p.get("zeta_v", 0.7))
    g = p["P_rated"] / p["V_ref48"] ** 2
    a = K_p - g
    if a <= 0.0:
        return False, -1.0
    zeta = a / (2.0 * np.sqrt(K_i * p["C_out"]))
    return zeta >= zeta_min, float(zeta)


# ---------------------------------------------------------------- validation

def check_converter_steady_state(p, tol=1e-3):
    """(e): v_out = V_ref48 and P_in = P_gpu + P_loss at rated load."""
    _, out = run_uniform(p, 1e-6, 0.05)
    P = p["P_rated"]
    P_loss = p["p_fix"] * P + p["k2"] * P * P / P
    err_v = abs(out[9, -1] - p["V_ref48"]) / p["V_ref48"]
    P_in = out[13, -1]
    err_p = abs(P_in - (P + P_loss)) / P
    err = max(err_v, err_p)
    return err, err < tol


def check_voltage_loop_step(p, tol=1e-2):
    """(f): converter output current response to a POL power step vs the exact
    linearised closed loop (PI voltage loop, capacitor plant, CPL incremental
    conductance g = P/V^2 at the new operating point; inner loop treated as
    ideal):  i_co(s) = dI (K_p s + K_i) / (s (C s^2 + (K_p - g) s + K_i)).
    Smoothing off, inner loop fast, ESR zero. Compared over 3 ms."""
    from scipy import signal as _sig
    q = {**p, "smooth_on": 0.0, "tau_i": 5e-6, "R_out_esr": 0.0}
    dt, T, t0 = 5e-7, 6e-3, 1e-3
    n = int(T / dt)
    P0, P1 = 0.5 * q["P_rated"], 0.8 * q["P_rated"]
    P = np.where(np.arange(n) * dt < t0, P0, P1)
    t, out = run_uniform(q, dt, T, P_profile=P)
    K_p, K_i = pi_tune(q["C_out"], q["f_v"], q.get("zeta_v", 0.7))
    C, V = q["C_out"], q["V_ref48"]
    g = P1 / V**2
    dI = (P1 - P0) / V
    tt = t[t >= t0] - t0
    sys = _sig.TransferFunction([K_p, K_i], [C, K_p - g, K_i])
    _, step = _sig.step(sys, T=tt)
    i_ana = P0 / V + dI * step
    m = tt <= 3e-3
    i_num = out[8][t >= t0][m]
    rms = np.sqrt(np.mean((i_num - i_ana[m])**2)) / dI
    return rms, rms < tol


def check_ramp_energy_balance(p, tol=1e-2):
    """(g) v0.4.1: with the converter-input ramp limiter active, (i) the output
    storage node balances -- energy delivered to the load minus energy
    delivered by the converter equals the energy released by C_out (KCL x v,
    exact); (ii) the converter input power slew never exceeds S_max; (iii)
    after the ramp the input tracks the demand. Worst of the three."""
    q = {**p, "smooth_on": 1.0, "S_max": 20e3 / 1e-3, "tau_r": 100e-6, "R_out_esr": 0.0}
    dt, T, t0 = 5e-7, 60e-3, 2e-3
    n = int(T / dt)
    P0, P1 = 0.4 * q["P_rated"], 0.9 * q["P_rated"]
    P = np.where(np.arange(n) * dt < t0, P0, P1)
    t, out = run_uniform(q, dt, T, P_profile=P)
    v_out, i_co, i_pol, P_in = out[9], out[8], out[11], out[13]
    m = (t >= t0) & (t <= t0 + 40e-3)
    # cumulative balance at every sample (the cap discharges then recharges;
    # the net over the whole window is ~0 and would pass trivially)
    E_net = np.cumsum(v_out[m] * (i_pol[m] - i_co[m])) * dt
    E_cap = 0.5 * q["C_out"] * (v_out[m][0]**2 - v_out[m]**2)
    swing = max(np.max(np.abs(E_cap)), 1e-9)
    err_e = np.max(np.abs(E_net - E_cap)) / swing
    P_s = np.convolve(P_in, np.ones(100) / 100, mode="same")
    slew = np.max(np.abs(np.diff(P_s[m]))) / dt
    err_s = max(0.0, (slew - q["S_max"]) / q["S_max"])
    m2 = t >= t0 + 40e-3
    P_req = v_out[m2] * i_co[m2]
    P_req = P_req + q["p_fix"] * q["P_rated"] + q["k2"] * P_req**2 / q["P_rated"]
    err_t = np.max(np.abs(P_in[m2] - P_req)) / q["P_rated"]
    err = max(err_e, err_s, err_t)
    return err, err < tol


def check_fault48_limit(p, tol=5e-2):
    """(h): into a bolted 48 V fault the converter output current saturates at
    I_lim_out (within tau_i overshoot), and before UVLO the fault current
    follows the R-L analytic from the capacitor bank."""
    q = {**p, "smooth_on": 0.0, "R_out_esr": 0.0}
    dt, T, t0 = 5e-8, 1.5e-3, 0.3e-3
    t, out = run_uniform(q, dt, T, fault48_start=t0, fault48_end=T)
    m = (t >= t0 + 5 * q["tau_i"]) & (t <= t0 + 0.8e-3)
    err_lim = abs(out[8][m].max() - q["I_lim_out"]) / q["I_lim_out"]
    # fault current early rise: di/dt = v_out / L_f48 before the cap sags appreciably
    m2 = (t >= t0) & (t <= t0 + 2e-6)
    slope = np.polyfit(t[m2], out[10][m2], 1)[0]
    err_slope = abs(slope - q["V_ref48"] / q["L_f48"]) / (q["V_ref48"] / q["L_f48"])
    err = max(err_lim, err_slope)
    return err, err < tol


def check_history_tier(p, tol=1e-3):
    """(d) for v0.4: DT_HIST history tier vs all-2 us reference on a two-tier
    train at baseline and at the stiffest sweep corner (tau_c 16 us,
    tau_i 10 us, L_in 1 uH, C_in 1 mF, C_bus 0.1 mF), after the 2 kHz
    slow-stream anti-alias, on the feeder AND rack observables."""
    from .events import build_schedule, two_tier_profile
    from scipy import signal as _sig
    stiff = dict(p)
    stiff.update(tau_c=16e-6, tau_i=10e-6, L_line=1e-6, C_bus=0.1e-3, L_in=1e-6, C_in=0.1e-3,
                 R_line=1e-3, R_esr=2e-3, R_in=1e-3, R_in_esr=2e-3, f_v=2e3, C_out=0.2)
    stiff["R_droop"] = 0.004 * stiff["V_ref"] / (stiff["P_rated"] / stiff["V_ref"])
    worst = 0.0
    for q, ramp1, dP1, sm in ((p, 3e-3, 0.4, 1.0), (stiff, 0.5e-3, 0.6, 0.0)):
        q = {**q, "smooth_on": sm}
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
            tt, out = simulate(pv, sched["dt"], P, np.zeros(t.size), 10**9, 10**9, 10**9, 10**9)
            outs.append((tt, out))
        tu = np.arange(0.0, t_pre - 0.25, 20e-6)
        sos = _sig.butter(4, 2e3, fs=1.0 / 20e-6, output="sos")
        for ch, scale in ((1, q["P_rated"] / q["V_ref"]), (2, q["V_ref"]),
                          (8, q["P_rated"] / q["V_ref48"]), (9, q["V_ref48"])):
            a = _sig.sosfiltfilt(sos, np.interp(tu, outs[0][0], outs[0][1][ch]))
            b = _sig.sosfiltfilt(sos, np.interp(tu, outs[1][0], outs[1][1][ch]))
            worst = max(worst, np.sqrt(np.mean((a - b) ** 2)) / scale)
    return worst, worst < tol


def decay_gate(p, ratio_max=0.5):
    """Gate 1 numeric part (v0.4.1): the two-stage 800 V input (C_bus, L_in-C_in,
    CPL) and the 48 V loop are checked by simulation. A 10 % load step at
    rated power; bus voltage and 48 V voltage ripple (peak-to-peak after
    removing the slow trend) in the last 2 ms of an 8 ms record must be below
    ratio_max of the ripple in the first 2 ms after the step. Returns
    (ok, worst_ratio)."""
    dt, T, t0 = 1e-6, 10e-3, 1e-3
    n = int(T / dt)
    P = np.where(np.arange(n) * dt < t0, 0.9 * p["P_rated"], p["P_rated"])
    t, out = run_uniform(p, dt, T, P_profile=P)
    worst = 0.0
    for ch in (2, 9):
        x = out[ch]
        if not np.all(np.isfinite(x)):
            return False, 1e9
        sm = np.convolve(x, np.ones(200) / 200, mode="same")
        r = x - sm
        a = (t >= t0 + 0.2e-3) & (t <= t0 + 2.2e-3)
        b = (t >= T - 2.3e-3) & (t <= T - 0.3e-3)          # keep clear of the convolution edge
        pp_a = np.ptp(r[a])
        pp_b = np.ptp(r[b])
        floor = 1e-3 * (p["V_ref"] if ch == 2 else p["V_ref48"])   # ripple below 0.1 % of nominal is quiet
        if pp_b > floor:
            worst = max(worst, pp_b / max(pp_a, floor))
    if out[5].min() < 0.5 or out[12].min() < 0.5:        # converter or load tripped on a 10 % step
        return False, 1e9
    return worst <= ratio_max, float(worst)
