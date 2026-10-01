"""train_model.py — train the relay models on a node feature-table cache and export them
(FIRMWARE_SPEC.md §6.3).

  python firmware/tools/train_model.py --cache data/nodes_v1large044 [--window 0.25]
         [--models feeder,rack,both] [--out-dir firmware/host/models]
         [--header firmware/common/fx_model_data.h]
         [--features firmware/host/tests/fixtures/reference_features.csv
          --scores firmware/host/tests/fixtures/reference_scores.csv]

Classifier: dcsim.studies._fit = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
max_leaf_nodes=15, l2_regularization=0.5, random_state=0). Inputs: studies.ALL (feeder, rack)
or ALL + ALL_rack (both, studies.two_node_table); targets studies.DECISION; rows of the chosen
decision window with onset_found > 0.5 (the rule of studies._cv_predict). The window defaults
to 0.25 ms, the relay's decision window (§0, §3); the node study's tables were scored at 1 ms.
Writes <out-dir>/<name>.joblib (not committed), <out-dir>/models.json (training-set hashes,
sizes) and calls export_model for the header (and the reference scores when --features/--scores
are given)."""
import argparse
import hashlib
import json
import os
import sys
import time
import numpy as np
import pandas as pd
import joblib
import sklearn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))
from dcsim.features import ALL                       # noqa: E402
from dcsim.studies import _fit, two_node_table       # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier   # noqa: E402
import export_model                                  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True, help="dir with features_feeder.csv and features_rack.csv")
    ap.add_argument("--window", type=float, default=0.25, help="decision window in ms (rows W_ms == window)")
    ap.add_argument("--models", default="feeder,rack,both")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "firmware", "host", "models"))
    ap.add_argument("--header", default=os.path.join(ROOT, "firmware", "common", "fx_model_data.h"))
    ap.add_argument("--features")
    ap.add_argument("--scores")
    ap.add_argument("--max-iter", type=int, default=300,
                    help="HistGradientBoosting max_iter (300 = studies._fit; other values for the §7.4 budget study)")
    ap.add_argument("--early-stopping", default="auto", choices=["auto", "off"],
                    help="sklearn early_stopping: 'auto' (studies._fit; ON above 10 000 rows, so v1xl tables stop at "
                         "70-100 iterations) or 'off' (max_iter trees are really built)")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    paths = {n: os.path.join(a.cache, f"features_{n}.csv") for n in ("feeder", "rack")}
    tabs = {n: pd.read_csv(p, float_precision="round_trip") for n, p in paths.items()}   # exact float parse
    both, both_cols = two_node_table(tabs["feeder"], tabs["rack"])
    specs = {"feeder": (tabs["feeder"], ALL), "rack": (tabs["rack"], ALL), "both": (both, both_cols)}
    meta = dict(generated=time.strftime("%Y-%m-%dT%H:%M:%S"), sklearn=sklearn.__version__, cache=a.cache,
                window_ms=a.window, max_iter=a.max_iter, early_stopping=a.early_stopping, tables={n: dict(path=p, sha256=sha256(p), rows=len(tabs[n])) for n, p in paths.items()},
                classifier="HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15, "
                           "l2_regularization=0.5, random_state=0)", models={})
    models = {}
    for name in a.models.split(","):
        df, cols = specs[name]
        d = df[np.isclose(df.W_ms, a.window)].reset_index(drop=True)
        ok = d["onset_found"].values > 0.5
        X = d[cols].values.astype(np.float64)[ok]
        y = d["decision"].values[ok]
        t0 = time.time()
        if a.max_iter == 300 and a.early_stopping == "auto":
            clf = _fit(X, y)                        # the studies' classifier, unchanged
        else:
            clf = HistGradientBoostingClassifier(max_iter=a.max_iter, learning_rate=0.06, max_leaf_nodes=15,
                                                 l2_regularization=0.5, random_state=0,
                                                 early_stopping=(a.early_stopping == "auto") and "auto").fit(X, y)
        dt = time.time() - t0
        path = os.path.join(a.out_dir, f"{name}.joblib")
        joblib.dump(clf, path)
        models[name] = clf
        counts = {c: int((y == c).sum()) for c in clf.classes_}
        meta["models"][name] = dict(joblib=os.path.relpath(path, ROOT), n_rows=int(ok.sum()), n_rows_total=len(d),
                                    class_counts=counts, n_iter=int(clf.n_iter_), features=list(cols),
                                    train_seconds=round(dt, 1), train_accuracy=float((clf.predict(X) == y).mean()))
        print(f"{name}: {ok.sum()} rows {counts}, {clf.n_iter_} iterations, {dt:.1f} s, train acc {meta['models'][name]['train_accuracy']:.4f}")
    info = export_model.export_header(models, a.header)
    for name, i in info.items():
        meta["models"][name].update(i)
    if a.features and a.scores:
        meta["reference_scores_max_dev_exported_tables"] = export_model.reference_scores(models, a.features, a.scores)
    with open(os.path.join(a.out_dir, "models.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote", os.path.join(a.out_dir, "models.json"))


if __name__ == "__main__":
    main()
