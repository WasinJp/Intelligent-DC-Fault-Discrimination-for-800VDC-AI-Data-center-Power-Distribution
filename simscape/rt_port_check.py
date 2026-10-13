"""rt_port_check.py — validate the MATLAB port (dcsim_rt_step.m / dcsim_rt_derivs.m) without MATLAB.

The two MATLAB files are transliterated below line by line (same names, same order of operations, same clamps).
Test 1: the transliteration vs dcsim.model_v04.simulate on the eight check-(i) cases at 1 us and at 10 us —
        expected difference exactly 0.0 on every sample of i_L, v_bus, i_rack, v_out (same arithmetic, same order).
Test 2: the fixed-step run at dt in {1, 2, 5, 10, 20} us scored by scripts/compare_simscape.py against the 1 us
        reference — the plant half of HIL plan check (k), i.e. the table MATLAB's rt_sweep will reproduce up to
        last-bit rounding.
Usage (repo root): python /path/to/rt_port_check.py [data/simscape]
"""
import sys, os, json, subprocess
import numpy as np
from scipy.io import loadmat, savemat
sys.path.insert(0, os.getcwd())
from dcsim.model_v04 import PARAMS_BASELINE, param_vector, run_uniform, PARAM_KEYS

datadir = sys.argv[1] if len(sys.argv) > 1 else "data/simscape"
shared = json.load(open(os.path.join(datadir, "params.json")))
cases = json.load(open(os.path.join(datadir, "cases.json")))


# ----------------------------------------------------------------- transliteration of dcsim_rt_derivs.m
def rt_derivs(y, pv, P_gpu, V_arc, fault_on, fault48_on, conv_on, load_on48, qs800, qs48):
    V_ref = pv[0]; P_rated = pv[1]; R_droop = pv[2]; tau_c = pv[3]; C_bus = pv[4]; L_line = pv[5]
    R_line = pv[6]; R_esr = pv[7]; V_uvlo = pv[8]; I_lim = pv[11]; R_f = pv[12]; L_f = pv[13]
    arc_place = pv[14]; L_in = pv[15]; R_in = pv[16]; C_in = pv[17]; R_in_esr = pv[18]
    smooth_on = pv[19]; S_max = pv[20]; tau_r = pv[21]; p_fix = pv[22]; k2 = pv[23]
    V_ref48 = pv[24]; C_out = pv[25]; R_out_esr = pv[26]; K_p = pv[27]; K_i = pv[28]; tau_i = pv[29]
    I_lim_out = pv[30]; V_uvlo48 = pv[31]; R_f48 = pv[34]; L_f48 = pv[35]
    v_c, i_L, v_C, i_f, i_Lin, v_Cin, P_cmd, xi_v, i_co, v_out, i_f48 = y
    if arc_place < 0.5: V_arc_load = V_arc; V_arc_line = 0.0
    else: V_arc_load = 0.0; V_arc_line = V_arc
    i_pol = 0.0
    if load_on48 > 0.5:
        i_pol = P_gpu / v_out if v_out > V_uvlo48 else P_gpu / V_uvlo48
    if qs48 > 0.5 and fault48_on > 0.5:
        i_f48 = (v_out + R_out_esr * (i_co - i_pol)) / (R_f48 + R_out_esr)
        if i_f48 < 0.0: i_f48 = 0.0
    i_Cout = i_co - i_pol - i_f48
    v_out_node = v_out + R_out_esr * i_Cout
    if v_out_node < 0.0: v_out_node = 0.0
    err = V_ref48 - v_out
    i_ref = K_p * err + K_i * xi_v
    sat = i_ref
    if sat > I_lim_out: sat = I_lim_out
    if sat < 0.0: sat = 0.0
    P_out_dem = v_out * sat
    if P_out_dem < 0.0: P_out_dem = 0.0
    if conv_on > 0.5: P_req = P_out_dem + (p_fix * P_rated + k2 * P_out_dem * P_out_dem / P_rated)
    else: P_req = 0.0
    dP_cmd = 0.0
    if smooth_on > 0.5:
        r = (P_req - P_cmd) / tau_r
        if r > S_max: r = S_max
        if r < -S_max: r = -S_max
        dP_cmd = r
        P_in_now = P_cmd if conv_on > 0.5 else 0.0
        P_out_max = P_in_now - p_fix * P_rated
        if P_out_max < 0.0: P_out_max = 0.0
        i_co_max = P_out_max / v_out if v_out > 1.0 else P_out_max / 1.0
        if sat > i_co_max: sat = i_co_max
    else:
        P_in_now = P_req
    dxi = err if sat == i_ref else 0.0
    di_co = (sat - i_co) / tau_i if conv_on > 0.5 else (0.0 - i_co) / tau_i
    dv_out = i_Cout / C_out
    di_f48 = 0.0
    if fault48_on > 0.5 and qs48 < 0.5:
        di_f48 = (v_out_node - R_f48 * i_f48) / L_f48
        if v_out <= 0.0 and di_f48 < 0.0 and i_f48 <= 0.0: di_f48 = 0.0
    v_in_eff = v_Cin - V_arc_load
    if conv_on > 0.5:
        i_in = P_in_now / v_in_eff if v_in_eff > V_uvlo else P_in_now / V_uvlo
    else:
        i_in = 0.0
    i_Cin = i_Lin - i_in
    v_Cin_node = v_Cin + R_in_esr * i_Cin
    if qs800 > 0.5 and fault_on > 0.5:
        i_f = (v_C + R_esr * (i_L - i_Lin)) / (R_f + R_esr)
        if i_f < 0.0: i_f = 0.0
    i_C = i_L - i_Lin - i_f
    v_bus = v_C + R_esr * i_C
    if v_bus < 0.0: v_bus = 0.0
    di_Lin = (v_bus - R_in * i_Lin - v_Cin_node) / L_in
    if i_Lin <= 0.0 and di_Lin < 0.0: di_Lin = 0.0
    dv_Cin = i_Cin / C_in
    di_f = 0.0
    if fault_on > 0.5 and qs800 < 0.5:
        di_f = (v_bus - R_f * i_f) / L_f
        if v_C <= 0.0 and di_f < 0.0 and i_f <= 0.0: di_f = 0.0
    dv_c = (V_ref - R_droop * i_L - v_c) / tau_c
    di_L = (v_c - R_line * i_L - V_arc_line - v_bus) / L_line
    if i_L >= I_lim and di_L > 0.0: di_L = 0.0
    if i_L <= 0.0 and di_L < 0.0: di_L = 0.0
    dv_C = i_C / C_bus
    return np.array([dv_c, di_L, dv_C, di_f, di_Lin, dv_Cin, dP_cmd, dxi, di_co, dv_out, di_f48])


# ----------------------------------------------------------------- transliteration of dcsim_rt_step.m
def rt_step(y, st, pv, dt, P_gpu, V_arc, f_on, f48_on, brk_f, brk_r, qs_dt_min, uvlo_tol=0.0):
    y = y.copy()
    R_esr = pv[7]; V_uvlo = pv[8]; t_uvlo_delay = pv[9]; V_hyst = pv[10]; R_f = pv[12]; L_f = pv[13]
    arc_place = pv[14]; R_in_esr = pv[18]; smooth_on = pv[19]; p_fix = pv[22]; k2 = pv[23]; P_rated = pv[1]
    R_out_esr = pv[26]; V_uvlo48 = pv[31]; t_uvlo48 = pv[32]; V_hyst48 = pv[33]; R_f48 = pv[34]; L_f48 = pv[35]
    qs_ratio = 0.5
    conv_on, load_on48, uvlo_t, uvlo48_t = st
    if brk_f < 0.5: y[1] = 0.0
    f48_eff = f48_on; load_eff = load_on48
    if brk_r < 0.5: f48_eff = 0.0; load_eff = 0.0; y[10] = 0.0
    q8 = 0.0; q4 = 0.0
    if f_on > 0.5 and dt >= qs_dt_min and dt > qs_ratio * L_f / (R_f + R_esr): q8 = 1.0
    if f48_eff > 0.5 and dt >= qs_dt_min and dt > qs_ratio * L_f48 / (R_f48 + R_out_esr): q4 = 1.0
    if q8 > 0.5:
        y[3] = (y[2] + R_esr * (y[1] - y[4])) / (R_f + R_esr)
        if y[3] < 0.0: y[3] = 0.0
    if q4 > 0.5:
        i_pq = 0.0
        if load_eff > 0.5:
            i_pq = P_gpu / y[9] if y[9] > V_uvlo48 else P_gpu / V_uvlo48
        y[10] = (y[9] + R_out_esr * (y[8] - i_pq)) / (R_f48 + R_out_esr)
        if y[10] < 0.0: y[10] = 0.0
    i_pol0 = 0.0
    if load_eff > 0.5:
        i_pol0 = P_gpu / y[9] if y[9] > V_uvlo48 else P_gpu / V_uvlo48
    v_out_obs = y[9] + R_out_esr * (y[8] - i_pol0 - y[10])
    if v_out_obs < 0.0: v_out_obs = 0.0
    P_out0 = y[9] * y[8]
    if P_out0 < 0.0: P_out0 = 0.0
    P_req0 = (P_out0 + (p_fix * P_rated + k2 * P_out0 * P_out0 / P_rated)) if conv_on > 0.5 else 0.0
    if conv_on > 0.5:
        P_in0 = y[6] if smooth_on > 0.5 else P_req0
    else:
        P_in0 = 0.0
    v_in_eff0 = y[5] - V_arc if arc_place < 0.5 else y[5]
    if conv_on > 0.5:
        i_in0 = P_in0 / v_in_eff0 if v_in_eff0 > V_uvlo else P_in0 / V_uvlo
    else:
        i_in0 = 0.0
    v_bus_obs = y[2] + R_esr * (y[1] - y[4] - y[3])
    if v_bus_obs < 0.0: v_bus_obs = 0.0
    v_Cin_obs = y[5] + R_in_esr * (y[4] - i_in0)
    if v_Cin_obs < V_uvlo:
        uvlo_t = uvlo_t + dt
        if uvlo_t >= t_uvlo_delay - uvlo_tol * dt: conv_on = 0.0
    else:
        uvlo_t = 0.0
        if conv_on < 0.5 and y[5] > V_uvlo + V_hyst: conv_on = 1.0
    if v_out_obs < V_uvlo48:
        uvlo48_t = uvlo48_t + dt
        if uvlo48_t >= t_uvlo48 - uvlo_tol * dt: load_on48 = 0.0
    else:
        uvlo48_t = 0.0
        if load_on48 < 0.5 and y[9] > V_uvlo48 + V_hyst48: load_on48 = 1.0
    load_eff = 0.0 if brk_r < 0.5 else load_on48
    i_rack = i_pol0 + y[10]
    v_out_rec = v_out_obs
    if brk_r < 0.5: i_rack = 0.0; v_out_rec = 0.0
    obs = np.array([y[0], y[1], v_bus_obs, y[3], i_in0, conv_on, y[4], y[5], y[8], v_out_rec, y[10], i_pol0, load_on48, P_in0, i_rack])
    k1 = rt_derivs(y, pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4)
    k2_ = rt_derivs(y + 0.5 * dt * k1, pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4)
    k3 = rt_derivs(y + 0.5 * dt * k2_, pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4)
    k4 = rt_derivs(y + dt * k3, pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4)
    y = y + (dt / 6.0) * (k1 + 2.0 * k2_ + 2.0 * k3 + k4)
    if f_on < 0.5: y[3] = 0.0
    if f48_eff < 0.5: y[10] = 0.0
    if brk_f < 0.5: y[1] = 0.0
    if y[2] < 0.0: y[2] = 0.0
    if y[9] < 0.0: y[9] = 0.0
    if y[5] < 0.0: y[5] = 0.0
    return y, np.array([conv_on, load_on48, uvlo_t, uvlo48_t]), obs


def rt_pv(shared, c):            # dcsim_rt_pv.m
    s = dict(shared); s.update(R_f=c["R_f"], L_f=c["L_f"], R_f48=c["R_f48"], L_f48=c["L_f48"], smooth_on=c["smooth_on"])
    return np.array([s[k] for k in PARAM_KEYS], dtype=np.float64)


def rt_profile(c, shared, t):    # dcsim_rt_profile.m
    P = c["P0"] * np.ones_like(t)
    if c["kind"] == "step":
        r = np.clip((t - c["t_event"]) / 2e-3, 0, 1)
        P = c["P0"] + 0.4 * shared["P_rated"] * r
    return P


def rt_loop(c, shared, dt, qs_dt_min=1.5e-6, uvlo_tol=0.0):   # run_rt_case.m, mode 'loop'
    pv = rt_pv(shared, c); T = shared["T_record"]; t0 = c["t_event"]
    n = int(round(T / dt)); k_f = int(round(t0 / dt))
    ic = c["initial_state"]
    y = np.array([ic[k] for k in ("v_c", "i_L", "v_C", "i_f", "i_Lin", "v_Cin", "P_cmd", "xi_v", "i_co", "v_out", "i_f48")])
    st = np.array([1.0, 1.0, 0.0, 0.0])
    t_abs = np.arange(n) * dt
    Pg = rt_profile(c, shared, t_abs)
    f800 = float(c["fault_800V_active"]); f48 = float(c["fault_48V_active"])
    obs = np.zeros((n, 15))
    for k in range(n):
        on = 1.0 if (k >= k_f and k < n) else 0.0
        y, st, o = rt_step(y, st, pv, dt, Pg[k], 0.0, f800 * on, f48 * on, 1.0, 1.0, qs_dt_min, uvlo_tol)
        obs[k] = o
    return t_abs, obs


def python_ref(c, shared, dt):   # the real core, same schedule as simscape_cases.run()
    p = {**PARAMS_BASELINE, "smooth_on": float(c["smooth_on"]), "R_f": c["R_f"], "L_f": c["L_f"], "R_f48": c["R_f48"], "L_f48": c["L_f48"]}
    T = shared["T_record"]; t0 = c["t_event"]; n = int(round(T / dt)); t = np.arange(n) * dt
    P = rt_profile(c, shared, t)
    kw = {}
    if c["fault_800V_active"]: kw = dict(fault_start=t0, fault_end=T)
    if c["fault_48V_active"]: kw = dict(fault48_start=t0, fault48_end=T)
    tt, o = run_uniform(p, dt, T, P_profile=P, **kw)
    return tt, o


names = ["step", "step_sm", "high_z", "high_z_sm", "high_z_48", "high_z_48_sm", "bolted_48", "bolted_48_sm"]
print("TEST 1 — transliterated MATLAB port vs dcsim.model_v04.simulate (max |diff| over the record, 4 observables)")
for dt in (1e-6, 10e-6):
    worst = 0.0
    for nm in names:
        c = cases[nm]
        t_abs, obs = rt_loop(c, shared, dt)
        tt, o = python_ref(c, shared, dt)
        d = max(np.abs(obs[:, 1] - o[1]).max(), np.abs(obs[:, 2] - o[2]).max(), np.abs(obs[:, 14] - o[14]).max(), np.abs(obs[:, 9] - o[9]).max())
        worst = max(worst, d)
        print(f"  dt = {dt*1e6:4.0f} us  {nm:13s}  max|diff| = {d:.3e}")
    print(f"  -> dt = {dt*1e6:.0f} us: worst {worst:.3e}  {'IDENTICAL' if worst == 0.0 else 'DIFFERS'}")

print("\nTEST 2 — fixed-step run scored by scripts/compare_simscape.py against the 1 us reference (plant half of check (k))")
dts = [1e-6, 2e-6, 5e-6, 10e-6, 20e-6]
for utol in (0.0, 0.5):
  print(f"\n  uvlo_tol = {utol}  ({'Python-identical accumulate-and-compare' if utol == 0 else 'grid-robust step counting (HIL setting)'})")
  table = {}
  for dt in dts:
      outdir = os.path.join(datadir, "rt_py", f"dt_{dt*1e6:g}us"); os.makedirs(outdir, exist_ok=True)
      for nm in names:
          c = cases[nm]; t0 = c["t_event"]
          t_abs, obs = rt_loop(c, shared, dt, uvlo_tol=utol)
          m = (t_abs >= t0 - 0.2e-3 - 1e-9) & (t_abs <= t0 + 5e-3 + 1e-9)
          f = os.path.join(outdir, f"sim_{nm}.mat")
          savemat(f, dict(t=t_abs[m] - t0, i_L=obs[m, 1], v_bus=obs[m, 2], i_rack=obs[m, 14], v_out=obs[m, 9]))
          txt = subprocess.run([sys.executable, "scripts/compare_simscape.py", os.path.join(datadir, f"ref_{nm}.mat"), f], capture_output=True, text=True).stdout
          last = [l for l in txt.strip().splitlines() if l.startswith("worst excluded")][-1]
          w = float(last.split()[2]); ok = "PASS" in last and "FAIL" not in last
          table[(nm, dt)] = (w, ok)
  print(f"{'case':13s}" + "".join(f"{dt*1e6:>12.0f} us" for dt in dts))
  for nm in names:
      print(f"{nm:13s}" + "".join(f"{table[(nm, dt)][0]:10.1e} {'P' if table[(nm, dt)][1] else 'F'} " for dt in dts))
  print("(P = PASS by the pre-registered criterion: excluded-RMS <= 1e-2 on all four channels, every edge within 5 us and 20 %)")
