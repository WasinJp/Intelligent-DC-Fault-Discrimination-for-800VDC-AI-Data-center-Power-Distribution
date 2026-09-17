"""v1-large operating study (HANDOFF §2 items 1-3). Works from the cached node tables only
(data/nodes/features_feeder.csv, features_rack.csv) - no h5 needed, ~15 min.

Usage: python scripts/run_operating_study.py [cache_dir] [--quick]
  1. Gate-2 percentile rows (OPEN-11): max / 99.9th / 99th percentile of the benign envelope.
  2. Two-node operating curve at false-trip budgets 0.1 / 0.05 / 0.02 %, in-sample threshold.
  3. The same with held-out (nested) threshold calibration.
  4. Two-node relay by decision window (0.25 / 0.5 / 1 ms), default threshold.
Writes <cache_dir>/operating_study.json.

PRE-REGISTERED 2026-09-18, before the first run (v1-large, 5 001 benign, 1 000 TRIP-class faults):
  P1  In-sample, budget 0.1 %: missed 0.33 +/- 0.15 % reproduces the hand computation within one std.
  P2  Nested, budget 0.1 %: realised false trips land in 0.05-0.20 % (mean above the in-sample value,
      because the budget is no longer enforced on the scored data); missed <= 0.7 %.
  P3  Budget 0.02 % is one benign event in-sample and ZERO in a ~4 000-event calibration fold, so the
      nested threshold is the single highest benign probability: nested missed >= 2x in-sample missed.
  P4  Gate 2 gray zone for 800 V high-Z faults: 72 / 57 / 36.5 % at 0 / 0.26 / 2.5 % false trips.
  P5  (added 2026-09-18 before its first run) The node-study table is scored on the 1 ms window but the
      claim is a decision at 0.25 ms. Two-node relay at 0.25 ms, default threshold: false trips <= 0.10 %,
      missed 800 V <= 0.6 %, missed 48 V <= 1.3 % - i.e. within about one std of the 1 ms row.
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd
from dcsim.studies import threshold_study, two_node_table, operating_points, _cv_predict, BENIGN, TRIP_800, TRIP_48

args = [a for a in sys.argv[1:] if not a.startswith("--")]
cache = args[0] if args else "data/nodes"
seeds = range(2) if "--quick" in sys.argv else range(10)
fe = pd.read_csv(os.path.join(cache, "features_feeder.csv"))
ra = pd.read_csv(os.path.join(cache, "features_rack.csv"))
assert (fe.event.values == ra.event.values).all() and (fe.W_ms.values == ra.W_ms.values).all(), "node tables misaligned"
n_ev = fe.event.nunique(); n_ben = int(fe[fe.W_ms == 1.0].label.isin(BENIGN).sum())
print(f"{n_ev} events, {n_ben} benign, seeds {list(seeds)}")
res = dict(n_events=n_ev, n_benign=n_ben, seeds=list(seeds))

print("\n=== 1. Gate 2 percentile rows (feeder, Layer-1 OR detector) ===")
ts = threshold_study(fe)
res["gate2_percentile_rows"] = ts["percentile_rows"]
print(f"  {'setting':8s} {'false trips':>12s} {'missed all':>11s} {'gray high_z':>12s} {'gray high_z_48':>15s} {'gray bolted_48':>15s}")
for name, r in ts["percentile_rows"].items():
    g = r["gray_zone"]
    print(f"  {name:8s} {r['false_trip']*100:11.2f}% {r['missed_all']*100:10.1f}% {g['high_z']*100:11.1f}% "
          f"{g.get('high_z_48', np.nan)*100:14.1f}% {g.get('bolted_48', np.nan)*100:14.1f}%")

both, cols = two_node_table(fe, ra)
fmt = lambda d, k: f"{d[k]['mean']*100:5.2f} ± {d[k]['std']*100:4.2f}"
for tag, nested in (("2. in-sample threshold", False), ("3. held-out (nested) calibration", True)):
    print(f"\n=== {tag}: feeder + rack, 1 ms window, 5-fold x {len(seeds)} seeds ===")
    t0 = time.time()
    op = operating_points(both, cols, seeds=seeds, nested=nested, verbose=False)
    res["nested" if nested else "in_sample"] = {f"{b:g}": v for b, v in op.items()}
    print(f"  {'budget':>8s} {'false trips':>14s} {'missed':>14s} {'missed 800 V':>14s} {'high-Z':>14s} {'missed 48 V':>14s}   threshold")
    for b, v in op.items():
        print(f"  {b*100:7.2f}% {fmt(v,'false_trip'):>14s} {fmt(v,'missed'):>14s} {fmt(v,'missed_800'):>14s} "
              f"{fmt(v,'high_z_missed'):>14s} {fmt(v,'missed_48'):>14s}   {v['threshold']['mean']:.3f}")
    print(f"  [{time.time()-t0:.0f} s]")
print(f"\n=== 4. two-node relay by decision window, default threshold, 5-fold x {len(seeds)} seeds ===")
print(f"  {'window':>8s} {'false trips':>14s} {'missed 800 V':>14s} {'high-Z':>14s} {'missed 48 V':>14s}")
res["by_window"] = {}
for W in (0.25, 0.5, 1.0):
    d = both[both.W_ms == W].reset_index(drop=True); lab = d.label.values
    m = dict(false_trip=np.isin(lab, BENIGN), missed_800=np.isin(lab, TRIP_800), high_z_missed=lab == "high_z", missed_48=np.isin(lab, TRIP_48))
    rows = []
    for sd in seeds:
        p = _cv_predict(d, cols, 5, seed=sd)
        rows.append([(p[m["false_trip"]] == "TRIP").mean()] + [(p[m[k]] == "HOLD").mean() for k in ("missed_800", "high_z_missed", "missed_48")])
    r = np.array(rows)
    v = {k: dict(mean=float(r[:, i].mean()), std=float(r[:, i].std())) for i, k in enumerate(m)}
    res["by_window"][f"{W:g}"] = v
    print(f"  {W:5.2f} ms {fmt(v,'false_trip'):>14s} {fmt(v,'missed_800'):>14s} {fmt(v,'high_z_missed'):>14s} {fmt(v,'missed_48'):>14s}", flush=True)
with open(os.path.join(cache, "operating_study.json"), "w") as fh:
    json.dump(res, fh, indent=1)
print(f"\nwrote {os.path.join(cache, 'operating_study.json')}")
