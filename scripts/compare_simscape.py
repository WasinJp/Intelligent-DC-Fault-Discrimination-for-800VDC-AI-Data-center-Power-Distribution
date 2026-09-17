"""MODEL.md §8 check (i): compare a Simscape export with the Python reference.
Usage: python scripts/compare_simscape.py data/simscape/ref_<case>.mat data/simscape/sim_<case>.mat
The Simscape .mat must contain t (s, relative to the event), i_L, v_bus, i_rack, v_out
(column vectors; To Workspace with save format 'Array', or timeseries converted).

Pre-registered criterion (2026-09-17, revised the same day before any Simscape result):
  PASS requires all three of
  (1) discontinuity-excluded normalised RMS <= 1e-2 on all four channels. Exclusion
      windows come from the REFERENCE only: +/-5 us around any adjacent-sample jump larger
      than 0.1 p.u. (comparator-driven steps such as the POL UVLO edge). 5 us absorbs
      ~20x the observed reference-grid jitter (0.25-0.35 us) and is 1/20 of t_uvlo48, so
      a wrong UVLO delay or threshold cannot hide inside it.
  (2) every such edge in the reference has a matching edge in the Simscape run (largest
      |di| within +/-100 us of it) with |dt_edge| <= 5 us and a step of the same sign
      within 20 % of the reference step.
  (3) the raw RMS is reported alongside (informational).
Windows and tolerances are identical for every run and are not adjusted after the fact."""
import sys, json, os
import numpy as np
from scipy.io import loadmat

W_EX, W_SEARCH, DT_EDGE, JUMP = 5e-6, 100e-6, 5e-6, 0.1
ref = loadmat(sys.argv[1]); sim = loadmat(sys.argv[2])
prm = json.load(open(os.path.join(os.path.dirname(sys.argv[1]), "params.json")))
I_r = prm["P_rated"] / prm["V_ref"]; I48 = prm["P_rated"] / prm["V_ref48"]
scale = dict(i_L=I_r, v_bus=prm["V_ref"], i_rack=I48, v_out=prm["V_ref48"])
col = lambda d, k: np.asarray(d[k]).squeeze().astype(float)
tr = col(ref, "t"); ts = col(sim, "t")
ok = True; worst_ex = worst_raw = 0.0
for k, sc in scale.items():
    a = col(ref, k); bs = col(sim, k); b = np.interp(tr, ts, bs)
    raw = np.sqrt(np.mean((a - b) ** 2)) / sc
    jumps = np.flatnonzero(np.abs(np.diff(a)) / sc > JUMP)
    keep = np.ones(tr.size, bool)
    for j in jumps:
        keep &= ~((tr >= tr[j] - W_EX) & (tr <= tr[j] + W_EX))
    ex = np.sqrt(np.mean((a[keep] - b[keep])**2)) / sc
    worst_ex, worst_raw = max(worst_ex, ex), max(worst_raw, raw)
    line = f"  {k:7s} excluded-RMS = {ex:.2e}   raw-RMS = {raw:.2e}   edges: {jumps.size}"
    ok &= ex <= 1e-2
    for j in jumps:                                        # edge timing and size
        te, da = tr[j], (a[j + 1] - a[j]) / sc
        m = (ts >= te - W_SEARCH) & (ts <= te + W_SEARCH)
        if m.sum() < 3:
            line += f"  | edge @{te*1e6:.1f} us: NO MATCH"; ok = False; continue
        d = np.diff(bs[m]) / sc; jj = np.argmax(np.abs(d))
        tsim = ts[m][jj]; db = d[jj]
        good = abs(tsim - te) <= DT_EDGE and np.sign(db) == np.sign(da) and abs(db - da) <= 0.2 * abs(da)
        ok &= good
        line += f"  | edge @{te*1e6:.1f} us: dt = {(tsim-te)*1e6:+.2f} us, step {da:+.3f} vs {db:+.3f} p.u. {'ok' if good else 'FAIL'}"
    print(line)
print(f"worst excluded {worst_ex:.2e} (raw {worst_raw:.2e})  ->  {'PASS' if ok else 'FAIL'}"
      f"  (check (i): excluded-RMS <= 1e-2 on all channels, every edge within {DT_EDGE*1e6:.0f} us and 20 % in size)")
