"""Run MODEL.md §9 gates 2 and 3 on a dataset; cache the feature table.
Usage: python scripts/run_studies.py [events.h5]"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd
from dcsim.features import CONV, PHYS, WORK, ALL
from dcsim.studies import (feature_table, threshold_study, classifier_study,
                           latency_study, arc_placement_study)

h5 = sys.argv[1] if len(sys.argv) > 1 else "data/events_v0.2.h5"
csv = h5.replace(".h5", "_features.csv")
if os.path.exists(csv):
    df = pd.read_csv(csv)
else:
    df = feature_table(h5)
    df.to_csv(csv, index=False)
print(f"{len(df)//3} events x 3 windows; onset found: {df[df.W_ms==1.0].onset_found.mean():.3f}")

def show(title, obj):
    print(f"\n=== {title}")
    print(json.dumps(obj, indent=1, default=lambda o: round(float(o), 4) if isinstance(o, (np.floating, float)) else str(o)))

ts = threshold_study(df)
show("GATE 2 — threshold detectors (W = 1 ms)", ts)
cs = classifier_study(df)
show("GATE 3 — classifier ablation (W = 1 ms)", {k: {kk: vv for kk, vv in v.items() if kk != "cv_pred"} for k, v in cs.items()})
show("GATE 3 — decision latency (all features)", latency_study(df))
show("GATE 3 — series-arc placement", arc_placement_study(df))
from dcsim.studies import operating_curve
oc = operating_curve(df)
print(f"\n=== GATE 3 — operating curve: at false-trip <= 0.1%: missed = {oc['miss_at_ft_target']:.3f}, high_z missed = {oc['high_z_miss_at_ft_target']:.3f}")
# where does workload-awareness apply? train-background subset
d = df[df.W_ms==1.0].reset_index(drop=True)
tr = d.background=='train'
cs2 = classifier_study(df, feature_sets={"+physics": CONV+PHYS, "+workload-aware": ALL})
for name, r in cs2.items():
    pred = r['cv_pred']; ben = d.label.str.startswith('benign').values; trip = d.label.isin(['bolted_pp','resistive_pp','high_z']).values
    print(f"  {name:16s} periodic-background subset: false-trip {(pred[tr & ben]=='TRIP').mean():.3f}  missed {(pred[tr & trip]=='HOLD').mean():.3f}   | flat-background: false-trip {(pred[~tr & ben]=='TRIP').mean():.3f}  missed {(pred[~tr & trip]=='HOLD').mean():.3f}")
# high_z miss vs fault current per unit
hz = d[d.label=='high_z'].copy(); hz['if_pu'] = (800.0/hz.R_f)/(hz.P_rated/800.0)
pred = cs2['+workload-aware']['cv_pred'][hz.index]
for lo, hi in [(0,0.15),(0.15,0.3),(0.3,0.6),(0.6,10)]:
    m = (hz.if_pu>=lo)&(hz.if_pu<hi)
    print(f"  high_z fault current {lo:.2f}-{hi:.2f} p.u.: n={m.sum():3d} missed={(pred[m.values]=='HOLD').mean():.3f}")
