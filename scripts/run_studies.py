"""Run MODEL.md §9 gates 2 and 3 on a dataset; cache the feature table.
Usage: python scripts/run_studies.py [events.h5]"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd
from dcsim.features import CONV, PHYS, WORK, ALL
from dcsim.studies import GATED   # v0.2.2
from dcsim.studies import (feature_table, threshold_study, classifier_study,
                           latency_study, arc_placement_study, repeated_study)

h5 = sys.argv[1] if len(sys.argv) > 1 else "data/events_v0.2.h5"
csv = h5.replace(".h5", "_features.csv")

# v0.2.1 (B4): the cache is keyed on the feature-extractor source. Editing
# features.py used to load stale features silently.
import hashlib
_feat_src = os.path.join(os.path.dirname(__file__), "..", "dcsim", "features.py")
_feat_hash = hashlib.sha256(open(_feat_src, "rb").read()).hexdigest()[:16]
_meta = csv + ".meta"
_stale = True
if os.path.exists(csv) and os.path.exists(_meta):
    _stale = open(_meta).read().strip() != _feat_hash
if _stale:
    if os.path.exists(csv):
        print(f"features.py changed (or no meta) -> regenerating {csv}")
    df = feature_table(h5)
    df.to_csv(csv, index=False)
    open(_meta, "w").write(_feat_hash)
else:
    df = pd.read_csv(csv)
print(f"{len(df)//3} events x 3 windows; onset found: {df[df.W_ms==1.0].onset_found.mean():.3f}")
_d1 = df[df.W_ms == 1.0]
_pe = _d1.groupby("label")["phase_err"].agg(["median", "max"]).round(3)
print("phase_err by label (v0.2.1 check: max must approach 0.5 for faults, NOT 0.12):")
print(_pe.to_string())
if "sched_tier" in _d1.columns and (_d1.sched_tier > 0).any():                       # v1 workload
    _bt = _d1[_d1.label == "benign_train"]
    print("\nv1 cadence: scheduled events by tier (phase_err median / p95 / max):")
    for tier in (1, 2):
        b = _bt[_bt.sched_tier == tier].phase_err.dropna()
        if len(b):
            print(f"  tier {tier}: n={len(b):3d}  {b.median():.3f} / {b.quantile(.95):.3f} / {b.max():.3f}")
    _tr = _d1[_d1.background == "train"]
    _has2 = _tr.T2 > 0
    print(f"  tier-1 period within 3 %: {(np.abs(_tr.T1_est/_tr.T1 - 1) < 0.03).mean():.3f}"
          f" | tier-2 present {_has2.sum()}, found {(_has2 & (_tr.T2_est > 0)).sum()},"
          f" false {((~_has2) & (_tr.T2_est > 0)).sum()}")
    _oth = _tr[_tr.label != "benign_train"]
    print(f"  alibi cost: unscheduled events with phase_err < 0.05: {(_oth.phase_err < 0.05).mean():.3f}"
          f" (one uniform tier would give 0.100)")
    print(f"  regimes: smoothed {int(_d1.smoothed.sum())} / unsmoothed {int((~_d1.smoothed.astype(bool)).sum())}")

def show(title, obj):
    print(f"\n=== {title}")
    print(json.dumps(obj, indent=1, default=lambda o: round(float(o), 4) if isinstance(o, (np.floating, float)) else str(o)))

ts = threshold_study(df)
show("GATE 2 — threshold detectors (W = 1 ms)", ts)
cs = classifier_study(df)
show("GATE 3 — classifier ablation (W = 1 ms)", {k: {kk: vv for kk, vv in v.items() if kk != "cv_pred"} for k, v in cs.items()})
rs = repeated_study(df)                                                  # v0.2.2 (D3)
print("\n=== GATE 3 — repeated CV, 10 fold seeds, mean ± std (%)  <-- quote THIS table")
print(f"{'feature set':18s} {'false trip':>12s} {'missed':>12s} {'high-Z':>12s} | {'periodic FT':>12s} {'periodic miss':>13s} | {'flat FT':>12s} {'flat miss':>12s}")
for n, v in rs.items():
    f = lambda k: f"{v[k]['mean']*100:5.2f}±{v[k]['std']*100:4.2f}"
    print(f"{n:18s} {f('false_trip'):>12s} {f('missed'):>12s} {f('high_z_missed'):>12s} | {f('periodic_false_trip'):>12s} {f('periodic_missed'):>13s} | {f('flat_false_trip'):>12s} {f('flat_missed'):>12s}")
show("GATE 3 — decision latency (all features)", latency_study(df))
show("GATE 3 — series-arc placement", arc_placement_study(df))
from dcsim.studies import operating_curve
oc = operating_curve(df)
print(f"\n=== GATE 3 — operating curve: at false-trip <= 0.1%: missed = {oc['miss_at_ft_target']:.3f}, high_z missed = {oc['high_z_miss_at_ft_target']:.3f}")
# where does workload-awareness apply? train-background subset
d = df[df.W_ms==1.0].reset_index(drop=True)
tr = d.background=='train'
cs2 = classifier_study(df, feature_sets={"+physics": CONV+PHYS, "+workload-aware": ALL,
                                          "+workload (gated)": GATED})   # v0.2.2
for name, r in cs2.items():
    pred = r['cv_pred']; ben = d.label.str.startswith('benign').values; trip = d.label.isin(['bolted_pp','resistive_pp','high_z']).values
    print(f"  {name:18s} periodic-background subset: false-trip {(pred[tr & ben]=='TRIP').mean():.3f}  missed {(pred[tr & trip]=='HOLD').mean():.3f}   | flat-background: false-trip {(pred[~tr & ben]=='TRIP').mean():.3f}  missed {(pred[~tr & trip]=='HOLD').mean():.3f}")
# high_z miss vs fault current per unit
hz = d[d.label=='high_z'].copy(); hz['if_pu'] = (hz.V_ref/hz.R_f)/hz.I_rated   # v0.2.1 (B5)
pred = cs2['+workload-aware']['cv_pred'][hz.index]
for lo, hi in [(0,0.15),(0.15,0.3),(0.3,0.6),(0.6,10)]:
    m = (hz.if_pu>=lo)&(hz.if_pu<hi)
    print(f"  high_z fault current {lo:.2f}-{hi:.2f} p.u.: n={m.sum():3d} missed={(pred[m.values]=='HOLD').mean():.3f}")
# v0.2.2: second sensing-floor driver -- bus capacitance hides the fault front from the feeder
hz['C_q'] = pd.qcut(hz.C_bus, 3, labels=['low C_bus', 'mid C_bus', 'high C_bus'])
for q in ['low C_bus', 'mid C_bus', 'high C_bus']:
    m = (hz.C_q == q).values
    print(f"  high_z {q:10s} (median {hz.C_bus[m].median()*1e3:.1f} mF): n={m.sum():3d} missed={(pred[m]=='HOLD').mean():.3f}")
