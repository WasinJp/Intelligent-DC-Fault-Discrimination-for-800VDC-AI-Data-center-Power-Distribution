"""Diagnose a failing check-(i) case: which quantity departs from the Python reference FIRST, and what
the Simscape control internals were doing at that moment. Called by simscape/run_all_cases.m on FAIL.
Usage: python scripts/diagnose_simscape.py data/simscape/ref_<case>.mat data/simscape/sim_<case>.mat"""
import sys, os, json
import numpy as np
from scipy.io import loadmat
ref, sim = loadmat(sys.argv[1]), loadmat(sys.argv[2])
prm = json.load(open(os.path.join(os.path.dirname(sys.argv[1]), "params.json")))
Pr, I8, I48 = prm["P_rated"], prm["P_rated"] / prm["V_ref"], prm["P_rated"] / prm["V_ref48"]
col = lambda d, k: np.asarray(d[k]).squeeze().astype(float)
tr, ts = col(ref, "t"), col(sim, "t")
pairs = [("i_L", "i_L", I8), ("v_bus", "v_bus", prm["V_ref"]), ("i_rack", "i_rack", I48), ("v_out", "v_out", prm["V_ref48"]),
         ("P_in", "dbg_P_in", Pr), ("i_co", "dbg_i_co", I48), ("v_Cin", "dbg_v_Cin", prm["V_ref"]), ("load_on48", "dbg_load_on48", 1.0)]
TH = 2e-3
print(f"  --- diagnosis: first time |Simscape - Python| exceeds {TH:g} p.u. (event at t = 0)")
rows = []
for kr, ks, sc in pairs:
    if kr in ref and ks in sim:
        d = np.abs(np.interp(tr, ts, col(sim, ks)) - col(ref, kr)) / sc
        bad = np.flatnonzero(d > TH)
        rows.append((tr[bad[0]] * 1e3 if bad.size else np.inf, kr, d.max(), tr[np.argmax(d)] * 1e3))
for t0, k, dm, tm in sorted(rows):
    print(f"      {k:10s} " + (f"departs at {t0:+7.3f} ms" if np.isfinite(t0) else "never departs      ") + f"   max diff {dm:.2e} p.u. at {tm:+.3f} ms")
have = [k for k in ("dbg_P_cmd", "dbg_P_req", "dbg_P_in", "dbg_i_ref", "dbg_sat", "dbg_i_co", "dbg_xi", "dbg_d_xi", "dbg_v_out_sensed", "dbg_P_gpu", "dbg_load_on48") if k in sim]
if not have:
    print("      (no dbg_* signals in the Simscape file: model built before 2026-09-18g)"); sys.exit(0)
print("  --- Simscape control internals (P in p.u. of P_rated, currents in A) | Python: P_in, i_co")
print("      t(ms)    P_gpu   P_req   P_cmd    P_in |  i_ref     sat    i_co |        xi   d_xi  v_sensed | py P_in  py i_co")
g = lambda k, i: col(sim, k)[i] if k in sim else np.nan
for tt in (-0.15, 0.02, 0.05, 0.1, 0.2, 0.3, 0.6, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
    i, j = int(np.argmin(np.abs(ts * 1e3 - tt))), int(np.argmin(np.abs(tr * 1e3 - tt)))
    print(f"    {tt:7.2f}  {g('dbg_P_gpu',i)/Pr:7.3f} {g('dbg_P_req',i)/Pr:7.3f} {g('dbg_P_cmd',i)/Pr:7.3f} {g('dbg_P_in',i)/Pr:7.3f} |"
          f" {g('dbg_i_ref',i):6.0f} {g('dbg_sat',i):7.0f} {g('dbg_i_co',i):7.0f} | {g('dbg_xi',i):.4e} {g('dbg_d_xi',i):6.3f} {g('dbg_v_out_sensed',i):9.4f} |"
          f" {col(ref,'P_in')[j]/Pr:7.3f} {col(ref,'i_co')[j]:8.0f}")
if "dbg_d_xi" in sim:
    dx = col(sim, "dbg_d_xi")
    for a, b in ((-0.2, 0), (0, 1), (1, 3), (3, 5)):
        m = (ts * 1e3 >= a) & (ts * 1e3 < b)
        print(f"      voltage-loop integrator running {np.mean(dx[m] != 0) * 100:5.1f} % of the samples in [{a:+.1f}, {b:+.1f}) ms")
