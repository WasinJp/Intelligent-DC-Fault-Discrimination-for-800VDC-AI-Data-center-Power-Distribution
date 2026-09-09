"""OPEN-14 hold-and-confirm study.
Usage: python scripts/run_confirm_study.py [events.h5]
Reads the dataset, computes stage-1 (0.25 ms) and stage-2 (2.5 / 4.5 ms) features
(cached next to the dataset), and reports the two-stage comparison over 10 seeds."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd
from dcsim.confirm import confirm_table, two_stage_study, W2S

h5 = sys.argv[1] if len(sys.argv) > 1 else "data/events_v1.h5"
csv = h5.replace(".h5", "_confirm.csv")
df = confirm_table(h5, cache=csv)
d = df
print(f"{len(d)} events; onset found {d.onset_found.mean():.3f}")
print("\nconfirmation features by class (medians, 4.5 ms window):")
cols = ["ring_decay_W4.5", "settle_W4.5", "di_late_W4.5", "i2t_W4.5"]
print(d.groupby("label")[cols].median().round(4).to_string())
res = two_stage_study(df)
with open(h5.replace(".h5", "_confirm.json"), "w") as fh:
    json.dump(res, fh, indent=1)
print("\n=== OPEN-14 two-stage study, 10 seeds, mean ± std (%) ===")
print(f"{'configuration':30s} {'false trip':>12s} {'missed':>12s} {'high-Z':>12s} {'confirm %':>10s} {'of benign':>10s} {'of faults':>10s}")
for n, r in res.items():
    f = lambda k: f"{r[k]['mean']*100:5.2f}±{r[k]['std']*100:4.2f}"
    cf = f"{r['confirm_frac']['mean']*100:9.1f}" if 'confirm_frac' in r else f"{'-':>9s}"
    cb = f"{r['confirm_frac_benign']['mean']*100:9.1f}" if 'confirm_frac_benign' in r else f"{'-':>9s}"
    ct = f"{r['confirm_frac_faults']['mean']*100:9.1f}" if 'confirm_frac_faults' in r else f"{'-':>9s}"
    print(f"{n:30s} {f('false_trip'):>12s} {f('missed'):>12s} {f('high_z_missed'):>12s} {cf:>10s} {cb:>10s} {ct:>10s}")
print("\nPre-registered test: '+conf' must beat '(no conf)' on false trips by more than the")
print("paired std without raising missed; otherwise the confirmation stage is dropped (Layer 3 takes the residue).")
