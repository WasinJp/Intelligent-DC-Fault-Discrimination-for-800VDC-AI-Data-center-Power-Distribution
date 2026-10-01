"""budget_study.py — inference-budget study for FIRMWARE_SPEC.md §7.4 (decision table in docs/TIMING.md).

  python firmware/tools/budget_study.py --cache data/nodes_v1xl6k --relay both --iters auto,100,150,300
         [--window 0.25] [--seeds 10] [--budget 1e-3] [--out firmware/docs/timing_study]

Settings: "auto" is studies._fit exactly (max_iter 300 with sklearn early_stopping='auto', which is ON
above 10 000 rows and stops the v1xl tables at 70-100 iterations); a number N builds exactly N trees
(early_stopping=False). Same learning_rate 0.06, max_leaf_nodes 15, l2 0.5, random_state 0. Each is
scored with studies.operating_points(nested=True): 5-fold x --seeds seeds, the P(TRIP) threshold chosen
inside each outer fold on inner-CV probabilities of the training part only at the --budget false-trip
budget, then applied to the held-out fold (run_operating_study.py §3). Relay: "both" = feeder + rack
(30 features, studies.two_node_table), "feeder" / "rack" = one node (15 features). Rows: W_ms == --window.
Features are not changed. One JSON per (relay, max_iter) in --out; make_timing_md.py builds the table."""
import argparse
import json
import os
import sys
import time
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from sklearn.ensemble import HistGradientBoostingClassifier   # noqa: E402
import dcsim.studies as studies                               # noqa: E402
from dcsim.features import ALL                                # noqa: E402

N_ITER_LOG = []


def make_fit(max_iter, early_stopping):
    """max_iter trees with sklearn early stopping 'auto' (the studies' _fit: ON above 10 000 rows, so
    the v1xl tables stop at 70-100 iterations) or False (max_iter trees are really built)."""
    def _fit(Xtr, ytr):
        clf = HistGradientBoostingClassifier(max_iter=max_iter, learning_rate=0.06, max_leaf_nodes=15,
                                             l2_regularization=0.5, random_state=0,
                                             early_stopping=early_stopping).fit(Xtr, ytr)
        N_ITER_LOG.append(int(clf.n_iter_))
        return clf
    return _fit


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--relay", default="both", choices=["both", "feeder", "rack"])
    ap.add_argument("--iters", default="100,150,300")
    ap.add_argument("--window", type=float, default=0.25)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--budget", type=float, default=1e-3)
    ap.add_argument("--out", default=os.path.join(ROOT, "firmware", "docs", "timing_study"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fe = pd.read_csv(os.path.join(a.cache, "features_feeder.csv"), float_precision="round_trip")
    ra = pd.read_csv(os.path.join(a.cache, "features_rack.csv"), float_precision="round_trip")
    if a.relay == "both":
        df, cols = studies.two_node_table(fe, ra)
    else:
        df, cols = (fe if a.relay == "feeder" else ra), ALL
    d = df[np.isclose(df.W_ms, a.window)].reset_index(drop=True)
    print(f"{a.relay}: {len(d)} rows at W = {a.window} ms, {len(cols)} features, seeds {a.seeds}, budget {a.budget}", flush=True)
    for tag in a.iters.split(","):
        # "auto" = studies._fit exactly (max_iter 300, early_stopping 'auto'); a number = that many trees, no early stopping
        it = 300 if tag == "auto" else int(tag)
        N_ITER_LOG.clear()
        studies._fit = make_fit(it, "auto" if tag == "auto" else False)
        t0 = time.time()
        op = studies.operating_points(d, cols, budgets=(a.budget,), seeds=range(a.seeds), nested=True,
                                      W_ms=a.window, verbose=True)[a.budget]
        dt = time.time() - t0
        res = dict(relay=a.relay, setting=tag, max_iter=it, early_stopping="auto" if tag == "auto" else "off",
                   window_ms=a.window, budget=a.budget, seeds=a.seeds, n_rows=len(d),
                   n_fits=len(N_ITER_LOG), n_iter_mean=float(np.mean(N_ITER_LOG)), n_iter_min=int(min(N_ITER_LOG)),
                   n_iter_max=int(max(N_ITER_LOG)), seconds=round(dt, 1),
                   **{k: op[k] for k in ("false_trip", "missed", "missed_800", "high_z_missed", "missed_48", "threshold")},
                   n_benign=op["n_benign"], rows=op["rows"])
        path = os.path.join(a.out, f"{a.relay}_it{tag}.json")
        with open(path, "w") as f:
            json.dump(res, f, indent=1)
        f = lambda k: f"{op[k]['mean']*100:.3f} +/- {op[k]['std']*100:.3f} %"
        print(f"  setting {tag}: n_iter {res['n_iter_mean']:.0f} ({res['n_iter_min']}-{res['n_iter_max']}), "
              f"FT {f('false_trip')}, missed-800 {f('missed_800')}, high-Z {f('high_z_missed')}, missed-48 {f('missed_48')}, "
              f"threshold {op['threshold']['mean']:.3f}  [{dt:.0f} s] -> {path}", flush=True)


if __name__ == "__main__":
    main()
