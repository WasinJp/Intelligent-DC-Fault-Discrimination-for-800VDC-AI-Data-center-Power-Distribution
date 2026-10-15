"""run_hil_operating_points.py -- the relay at the 0.1 % false-trip budget on the HIL front-end chains (check (k), part 2).

Input: the chain tables written by run_hil_frontend_study.py --save-tables (<dir>/features_<node>_<chain>.csv, one
decision window). Two questions, both on the TWO-NODE relay (feeder + rack features, onset at either node), scored
with the same machinery as the published relay result (studies._cv_predict, studies._threshold_at_budget):

  A. Budgeted operating point per chain, model trained on that chain (= "retrained on the HIL front end"), 5-fold
     out-of-fold, threshold chosen on the out-of-fold benign P(TRIP) at the budget (in-sample calibration, as
     run_operating_study.py section 2; optimistic by the same amount for every chain, so chains compare fairly).
     --nested uses studies.operating_points(nested=True) instead (held-out calibration; slower).
  B. Transfer: model trained on chain T, applied to every other chain with the SAME folds and T's budget threshold
     -> what the relay trained for one HIL step shows when the box runs another step (or the clean stream).
     False trips, missed (all TRIP classes), missed 800 V, missed high-Z, missed 48 V, per chain; mean +/- std over seeds.

Rows with window_short == 1 (late onset, no complete window) are scored as no onset (HOLD), as the relay would.

Usage (repo root, .venv):
  python scripts/run_hil_operating_points.py data/hil_frontend_full --chains ref,node_ideal,hil_2us,hil_5us,hil_10us --seeds 3
  python scripts/run_hil_operating_points.py data/hil_frontend_full --train ref,hil_2us,hil_5us --seeds 3
  A train entry "hil_2us+hil_5us" trains on the UNION of those chains' rows (every training event seen at both
  steps; folds are by event, so nothing leaks) -- step augmentation, for a relay that must hold across a step range.
Writes <dir>/hil_operating_points.md and .json.
"""
import sys, os, json, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd
from sklearn.model_selection import StratifiedKFold
from dcsim.studies import (_fit, _cv_predict, _threshold_at_budget, two_node_table, operating_points,
                           BENIGN, TRIP_CLASSES, TRIP_800, TRIP_48)


def load_chain(d, chain, W):
    fe = pd.read_csv(os.path.join(d, f"features_feeder_{chain}.csv"), dtype={"event": str}, float_precision="round_trip")
    ra = pd.read_csv(os.path.join(d, f"features_rack_{chain}.csv"), dtype={"event": str}, float_precision="round_trip")
    fe, ra = fe[fe.W_ms == W].sort_values("event").reset_index(drop=True), ra[ra.W_ms == W].sort_values("event").reset_index(drop=True)
    assert (fe.event.values == ra.event.values).all(), f"{chain}: feeder / rack tables misaligned"
    for t in (fe, ra):
        if "window_short" in t:
            t.loc[t.window_short > 0.5, "onset_found"] = 0.0
    both, cols = two_node_table(fe, ra)
    return both, cols


def metrics(fired, lab):
    ben, trp = np.isin(lab, BENIGN), np.isin(lab, TRIP_CLASSES)
    return dict(false_trip=float(fired[ben].mean()), missed=float((~fired[trp]).mean()),
                missed_800=float((~fired[np.isin(lab, TRIP_800)]).mean()),
                high_z_missed=float((~fired[lab == "high_z"]).mean()),
                missed_48=float((~fired[np.isin(lab, TRIP_48)]).mean()))


def oof_probs(tables, cols, train_chain, seed, n_splits=5):
    """Out-of-fold P(TRIP) for every chain, model fitted on train_chain's rows of each training fold (same folds for
    all chains; rows without a complete window are never trained on and get P = 0). train_chain "a+b" = union."""
    parts = [tables[c] for c in train_chain.split("+")]
    src = parts[0]
    labels = src.label.values
    out = {c: np.zeros(len(src)) for c in tables}
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for tr, te in skf.split(np.zeros(len(src)), labels):
        X = np.concatenate([t[cols].values[tr[t.onset_found.values[tr] > 0.5]].astype(np.float64) for t in parts])
        y = np.concatenate([t.decision.values[tr[t.onset_found.values[tr] > 0.5]] for t in parts])
        clf = _fit(X, y); i_trip = list(clf.classes_).index("TRIP")
        for c, t in tables.items():
            ok = t.onset_found.values > 0.5
            te_ok = te[ok[te]]
            if te_ok.size:
                out[c][te_ok] = clf.predict_proba(t[cols].values[te_ok].astype(np.float64))[:, i_trip]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir"); ap.add_argument("--W", type=float, default=0.25)
    ap.add_argument("--chains", default="ref,node_ideal,hil_1us,hil_2us,hil_5us,hil_10us,dac_replay")
    ap.add_argument("--train", default=None, help="train chains for the transfer block (default: all --chains)")
    ap.add_argument("--budget", type=float, default=1e-3); ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--nested", action="store_true", help="block A with held-out threshold calibration (studies.operating_points nested=True)")
    a = ap.parse_args()
    chains = [c for c in a.chains.split(",") if c]
    trains = [c for c in (a.train or a.chains).split(",") if c]
    t0 = time.time()
    tables, cols = {}, None
    for c in chains:
        tables[c], cols = load_chain(a.dir, c, a.W)
    ev = tables[chains[0]].event.values
    for c in chains:
        assert (tables[c].event.values == ev).all(), f"{c}: event set differs from {chains[0]}"
    lab = tables[chains[0]].label.values
    n_ben, n_trp = int(np.isin(lab, BENIGN).sum()), int(np.isin(lab, TRIP_CLASSES).sum())
    md = [f"# check (k), part 2 -- two-node relay at the {a.budget*100:g} % false-trip budget on the HIL front-end chains",
          f"\n{a.dir}: {len(ev)} events ({n_ben} benign, {n_trp} TRIP-class), W = {a.W} ms, 5 folds x {a.seeds} seeds, cols = feeder + rack ({len(cols)})\n"]
    res = dict(dir=a.dir, n_events=int(len(ev)), n_benign=n_ben, W_ms=a.W, budget=a.budget, seeds=a.seeds)

    # ---- A. per-chain operating point, trained on itself
    md.append(f"## A. Trained on the chain itself, out-of-fold, threshold at the budget ({'held-out' if a.nested else 'in-sample'} calibration)\n")
    md.append("| chain | false trips % | missed % (all TRIP) | missed 800 V % | high-Z missed % | missed 48 V % | threshold |")
    md.append("|---|---|---|---|---|---|---|")
    res["self"] = {}
    for c in chains:
        if a.nested:
            r = operating_points(tables[c], cols, budgets=(a.budget,), seeds=range(a.seeds), W_ms=a.W, nested=True, verbose=False)[a.budget]
        else:
            rows, ths = [], []
            for s in range(a.seeds):
                d = tables[c]
                p = _cv_predict(d, cols, 5, proba_class="TRIP", seed=s)
                th = _threshold_at_budget(p[np.isin(lab, BENIGN)], a.budget); ths.append(th)
                rows.append(metrics(p > th, lab))
            r = {k: dict(mean=float(np.mean([x[k] for x in rows])), std=float(np.std([x[k] for x in rows]))) for k in rows[0]}
            r["threshold"] = dict(mean=float(np.mean(ths)), std=float(np.std(ths)))
        res["self"][c] = r
        f = lambda k: f"{r[k]['mean']*100:.3f} +/- {r[k]['std']*100:.3f}"
        md.append(f"| {c} | {f('false_trip')} | {f('missed')} | {f('missed_800')} | {f('high_z_missed')} | {f('missed_48')} | {r['threshold']['mean']:.3f} |")
        print(f"A {c}: false {r['false_trip']['mean']*100:.3f} % missed {r['missed']['mean']*100:.3f} %  [{time.time()-t0:.0f} s]", flush=True)

    # ---- B. transfer: train on T, score every chain with T's threshold, same folds
    md.append(f"\n## B. Transfer -- model trained on one chain (rows), applied to every chain (columns) with the training chain's budget threshold\n")
    md.append("Cells: false trips % / missed % (all TRIP classes). The diagonal repeats A. Read a row as: the relay we would ship for that step, "
              "when the box runs the step of the column.\n")
    md.append("| trained on \\ scored on | " + " | ".join(chains) + " |"); md.append("|---|" + "---|" * len(chains))
    res["transfer"] = {}
    for tchain in trains:
        acc = {c: [] for c in chains}
        for s in range(a.seeds):
            p = oof_probs(tables, cols, tchain, s)
            cal = tchain.split("+")
            th = _threshold_at_budget(np.concatenate([p[c][np.isin(lab, BENIGN)] for c in cal]), a.budget)
            for c in chains:
                acc[c].append(metrics(p[c] > th, lab))
        res["transfer"][tchain] = {c: {k: dict(mean=float(np.mean([x[k] for x in acc[c]])), std=float(np.std([x[k] for x in acc[c]])))
                                       for k in acc[c][0]} for c in chains}
        md.append(f"| {tchain} | " + " | ".join(f"{res['transfer'][tchain][c]['false_trip']['mean']*100:.3f} / {res['transfer'][tchain][c]['missed']['mean']*100:.2f}" for c in chains) + " |")
        print(f"B trained on {tchain}: " + ", ".join(f"{c} {res['transfer'][tchain][c]['false_trip']['mean']*100:.3f}%" for c in chains) + f"  [{time.time()-t0:.0f} s]", flush=True)

    md.append("\nReading: A says what a relay retrained for each front end achieves at the budget (compare with the published two-node result on the clean "
              "stream, 0.03 / 0.42 / 0.63 % at 0.25 ms default threshold; 0.09 / 0.33 / 0.29 % at 1 ms budgeted). B says how much the step may differ "
              "between training and the box before the false-trip rate leaves the budget band. In-sample calibration is optimistic by the same amount "
              "in every cell; --nested gives the honest absolute numbers for the row you will quote.")
    txt = "\n".join(md)
    open(os.path.join(a.dir, "hil_operating_points.md"), "w", encoding="utf-8").write(txt)
    json.dump(res, open(os.path.join(a.dir, "hil_operating_points.json"), "w"), indent=1)
    print(txt)


if __name__ == "__main__":
    main()
