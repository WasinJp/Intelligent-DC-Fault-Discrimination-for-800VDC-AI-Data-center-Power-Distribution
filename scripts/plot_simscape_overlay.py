"""Overlay figure for check (i): Python core vs Simscape, feeder and rack node, one case.
Usage: python scripts/plot_simscape_overlay.py [case] [out.png]        (default: high_z_48 -> figures/fig5_simscape_overlay.png)
Needs data/simscape/ref_<case>.mat (Python) and sim_<case>.mat (written by simscape/crosscheck.m)."""
import sys, os, json
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.io import loadmat
root = os.path.join(os.path.dirname(__file__), "..")
case = sys.argv[1] if len(sys.argv) > 1 else "high_z_48"
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "figures", "fig5_simscape_overlay.png")
d = os.path.join(root, "data", "simscape")
ref, sim = loadmat(os.path.join(d, f"ref_{case}.mat")), loadmat(os.path.join(d, f"sim_{case}.mat"))
prm = json.load(open(os.path.join(d, "params.json")))
I8, I48 = prm["P_rated"] / prm["V_ref"], prm["P_rated"] / prm["V_ref48"]
col = lambda m, k: np.asarray(m[k]).squeeze().astype(float)
tr, ts = col(ref, "t") * 1e3, col(sim, "t") * 1e3
chans = [("i_L", I8, "feeder current  i_L  (p.u.)"), ("v_bus", prm["V_ref"], "800 V bus  v_bus  (p.u.)"),
         ("i_rack", I48, "rack busbar current  i_rack  (p.u.)"), ("v_out", prm["V_ref48"], "48 V bus  v_out  (p.u.)")]
fig, ax = plt.subplots(3, 2, figsize=(11, 8.2), gridspec_kw=dict(height_ratios=[3, 3, 1.6]), sharex=True)
for n, (k, sc, lab) in enumerate(chans):
    a = ax[n // 2][n % 2]
    a.plot(tr, col(ref, k) / sc, color="#1f4e79", lw=2.4, label="Python core (RK4, 11 states)")
    a.plot(ts, col(sim, k) / sc, color="#e07b00", lw=1.1, ls="--", label="Simscape Electrical (independent build)")
    e = np.sqrt(np.mean((np.interp(tr, ts, col(sim, k)) - col(ref, k)) ** 2)) / sc
    a.set_ylabel(lab); a.grid(alpha=.3); a.axvline(0, color="k", lw=.6, alpha=.5)
    a.text(.98, .06, f"normalised RMS difference {e:.1e}", transform=a.transAxes, ha="right", fontsize=9,
           bbox=dict(fc="white", ec="0.7", boxstyle="round,pad=0.25"))
ax[0][0].legend(loc="center right", fontsize=8.5, framealpha=.95)
for m, (pair, title) in enumerate(((chans[:2], "feeder node"), (chans[2:], "rack node"))):
    a = ax[2][m]
    for (k, sc, _), c_ in zip(pair, ("#444444", "#9a9a9a")):
        a.plot(tr, (np.interp(tr, ts, col(sim, k)) - col(ref, k)) / sc * 100, color=c_, lw=.9, label=k)
    a.axhspan(-1, 1, color="#2e8b57", alpha=.10); a.set_ylim(-1.2, 1.2)
    a.set_ylabel("Simscape − Python\n(% of rated)"); a.set_xlabel("time after the event (ms)"); a.grid(alpha=.3)
    a.legend(loc="upper right", fontsize=8, ncol=2, title=f"{title}; green band = ±1 % criterion", title_fontsize=8)
fig.suptitle(f"Check (i): independent Simscape implementation vs the Python core — case '{case}'", fontsize=12, y=.995)
fig.tight_layout(); os.makedirs(os.path.dirname(out), exist_ok=True); fig.savefig(out, dpi=170)
print("wrote", os.path.normpath(out))
