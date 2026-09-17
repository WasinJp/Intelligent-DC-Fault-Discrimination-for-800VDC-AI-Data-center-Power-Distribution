"""Export the Simscape cross-check cases (MODEL.md §8 check (i)).
Usage: python scripts/simscape_cases.py [outdir]
Per case: ref_<case>.mat with the Python reference on a uniform 1 us grid over the
fine window (-0.2 .. +5 ms around the event), the exact initial state, the
per-case parameters (fault values and the smoothing flag), and the flag traces
(load_on48, conv_on). cases.json collects every case's parameters; params.json
holds the shared baseline. Cases:
  step       benign POL power step +40 % of P_rated over 2 ms
  high_z     800 V fault, R_f = 5 ohm, L_f = 2 uH
  high_z_48  48 V fault, R_f48 = 20 mohm, L_f48 = 0.5 uH
  bolted_48  48 V fault, R_f48 = 1 mohm, L_f48 = 0.5 uH
Each with smoothing off and on (suffix _sm) -> 8 runs.
Reference grid: 1 us vs 50 ns differ by <= 2e-4 on every channel except one
sample at the POL-UVLO edge in bolted_48 (see compare_simscape.py)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from scipy.io import savemat
from dcsim.model_v04 import PARAMS_BASELINE, run_uniform, pi_tune, _loss

out = sys.argv[1] if len(sys.argv) > 1 else "data/simscape"
os.makedirs(out, exist_ok=True)
dt, T, t0 = 1e-6, 7e-3, 2e-3
n = int(T / dt); t = np.arange(n) * dt
P0 = 0.5 * PARAMS_BASELINE["P_rated"]

def initial_state(p, P_gpu0):
    """Exact steady state, as model_v04.simulate initialises it."""
    K_p, K_i = pi_tune(p["C_out"], p["f_v"], p["zeta_v"])
    i_co0 = P_gpu0 / p["V_ref48"]
    P_req0 = P_gpu0 + _loss(P_gpu0, p["P_rated"], p["p_fix"], p["k2"])
    i_L0 = P_req0 / p["V_ref"]
    for _ in range(20):
        v_c0 = p["V_ref"] - p["R_droop"] * i_L0
        v_C0 = v_c0 - p["R_line"] * i_L0
        v_Cin0 = v_C0 - p["R_in"] * i_L0
        i_L0 = P_req0 / v_Cin0
    v_c0 = p["V_ref"] - p["R_droop"] * i_L0
    v_C0 = v_c0 - p["R_line"] * i_L0
    v_Cin0 = v_C0 - p["R_in"] * i_L0
    return dict(v_c=v_c0, i_L=i_L0, v_C=v_C0, i_f=0.0, i_Lin=i_L0, v_Cin=v_Cin0,
                P_cmd=P_req0, xi_v=i_co0 / K_i, i_co=i_co0, v_out=p["V_ref48"], i_f48=0.0,
                K_p=K_p, K_i=K_i)

def run(kind, smooth):
    p = {**PARAMS_BASELINE, "smooth_on": float(smooth)}
    P = np.full(n, P0); kw = {}
    if kind == "step":
        P = P0 + 0.4 * p["P_rated"] * np.clip((t - t0) / 2e-3, 0, 1)
    elif kind == "high_z":
        p.update(R_f=5.0, L_f=2e-6); kw = dict(fault_start=t0, fault_end=T)
    elif kind == "high_z_48":
        p.update(R_f48=20e-3, L_f48=0.5e-6); kw = dict(fault48_start=t0, fault48_end=T)
    elif kind == "bolted_48":
        p.update(R_f48=1e-3, L_f48=0.5e-6); kw = dict(fault48_start=t0, fault48_end=T)
    tt, o = run_uniform(p, dt, T, P_profile=P, **kw)
    return p, P, tt, o

cases = {}
for kind in ("step", "high_z", "high_z_48", "bolted_48"):
    for smooth in (0, 1):
        p, P, tt, o = run(kind, smooth)
        name = kind + ("_sm" if smooth else "")
        ic = initial_state(p, P0)
        m = (tt >= t0 - 0.2e-3) & (tt <= t0 + 5e-3)
        case = dict(name=name, kind=kind, smooth_on=float(smooth), R_f=p["R_f"], L_f=p["L_f"],
                    R_f48=p["R_f48"], L_f48=p["L_f48"],
                    fault_800V_active=(kind == "high_z"), fault_48V_active=(kind in ("high_z_48", "bolted_48")),
                    t_event=t0, P0=P0, initial_state={k: float(v) for k, v in ic.items()})
        cases[name] = case
        savemat(os.path.join(out, f"ref_{name}.mat"),
                dict(t=tt[m] - t0, P_gpu=P[m], i_L=o[1][m], v_bus=o[2][m], i_rack=o[14][m], v_out=o[9][m],
                     i_co=o[8][m], v_Cin=o[7][m], i_f=o[3][m], i_f48=o[10][m], P_in=o[13][m],
                     load_on48=o[12][m], conv_on=o[5][m],
                     case=json.dumps(case)))
        print(f"  wrote ref_{name}.mat  ({m.sum()} samples; POL UVLO trips: {'yes' if (o[12][m] < 0.5).any() else 'no'})")
K_p, K_i = pi_tune(PARAMS_BASELINE["C_out"], PARAMS_BASELINE["f_v"], PARAMS_BASELINE["zeta_v"])
shared = {k: float(v) for k, v in PARAMS_BASELINE.items() if k not in ("R_f", "L_f", "R_f48", "L_f48", "smooth_on")}
shared.update(K_p=K_p, K_i=K_i, P0=P0, t_event=t0, T_record=T, dt_reference=dt,
              note="per-case values (fault R/L, smooth_on, initial state) are in cases.json and in each ref_<case>.mat")
json.dump(shared, open(os.path.join(out, "params.json"), "w"), indent=1)
json.dump(cases, open(os.path.join(out, "cases.json"), "w"), indent=1)
print(f"params.json: {len(shared)} shared values; cases.json: {len(cases)} cases with per-case parameters and exact initial states")
