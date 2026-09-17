"""v0.4 node study: feeder-only vs rack-only vs both, on the same events.
Usage: python scripts/run_node_study.py [events.h5 | "shard_glob*.h5"] [cache_dir]"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd
from dcsim.studies import node_study, threshold_study

h5 = sys.argv[1] if len(sys.argv) > 1 else "data/events_v04.h5"       # a glob of shard files also works
# second argument: cache folder. Give every dataset its own (data/nodes is v1-large's).
cache = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(h5), "nodes")
os.makedirs(cache, exist_ok=True)
res, tabs = node_study(h5, cache_dir=cache)
with open(os.path.join(cache, "node_study.json"), "w") as fh:
    json.dump(res, fh, indent=1)
fe = tabs["feeder"]
d = fe[fe.W_ms == 1.0]
print()
print("=== v0.4 predictions ===")
ts = threshold_study(fe)
print(f"Gate-2 gray zone (feeder), 800 V high-Z inside benign envelope: {ts['gray_zone_fraction']['high_z']*100:.1f}%"
      f"  (v1 on the v0.3 core: 66.5%)")
for bs, lab in ((0.0, "no bus storage"), (1.0, "bus storage")):
    for sm, lab2 in ((0.0, "smoothing off"), (1.0, "smoothing on")):
        sub = fe[(fe.bus_storage == bs) & (fe.smooth_on == sm)]
        if len(sub) and (sub[sub.W_ms == 1].label == "high_z").sum() >= 10:
            t2 = threshold_study(sub)
            print(f"  {lab:15s} / {lab2:13s}: gray zone {t2['gray_zone_fraction']['high_z']*100:.1f}%"
                  f"  (n benign {int((sub[sub.W_ms==1].label.str.startswith('benign')).sum())}, high-Z {int((sub[sub.W_ms==1].label=='high_z').sum())})")
hz = d[d.label == "high_z"].copy()
if len(hz) and "bus_storage" in hz.columns:
    print("high-Z (800 V) feeder onset-found: no bus storage %.3f | with bus storage %.3f" % (
        hz[hz.bus_storage == 0].onset_found.mean(), hz[hz.bus_storage == 1].onset_found.mean()))
    hs = hz[hz.bus_storage == 1]
    if len(hs) >= 9:
        hs = hs.assign(C_q=pd.qcut(hs.C_store, 3, labels=["low", "mid", "high"]))
        print("  with bus storage, onset-found by C_store tercile:", hs.groupby("C_q").onset_found.mean().round(3).to_dict())
print(f"feeder onset found: 800 V faults {d[d.label.isin(['bolted_pp','resistive_pp','high_z'])].onset_found.mean():.3f}"
      f" | 48 V faults {d[d.label.isin(['bolted_48','high_z_48'])].onset_found.mean():.3f}"
      f" | benign {d[d.label.str.startswith('benign')].onset_found.mean():.3f}")
ra = tabs["rack"]; dr = ra[ra.W_ms == 1.0]
for nm, dd in (("feeder", d), ("rack", dr)):
    tr = dd[dd.background == "train"]
    b1 = tr[(tr.label == "benign_train") & (tr.sched_tier == 1)].phase_err
    b2 = tr[(tr.label == "benign_train") & (tr.sched_tier == 2)].phase_err
    print(f"{nm:6s} cadence: has_period {tr.has_period.mean():.3f} | T1 within 3% {(np.abs(tr.T1_est/tr.T1-1)<0.03).mean():.3f}"
          f" | tier-2 found {int(((tr.T2>0)&(tr.T2_est>0)).sum())}/{int((tr.T2>0).sum())}"
          f" | scheduled tier-1 p95 {b1.quantile(.95):.3f} | tier-2 p95 {b2.quantile(.95):.3f}")
print(f"rack   onset found: 800 V faults {dr[dr.label.isin(['bolted_pp','resistive_pp','high_z'])].onset_found.mean():.3f}"
      f" | 48 V faults {dr[dr.label.isin(['bolted_48','high_z_48'])].onset_found.mean():.3f}"
      f" | benign {dr[dr.label.str.startswith('benign')].onset_found.mean():.3f}")
