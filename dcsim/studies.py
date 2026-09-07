"""dcsim.studies — MODEL.md §9 gate 2 (threshold / gray-zone study) and
gate 3 (classifier study) on a generated dataset.

Decision classes for the protection architecture (figures/architecture.png):
  TRIP   bolted_pp, resistive_pp, high_z
  HOLD   benign_step, benign_train, benign_idle_drop
  ALERT  series_arc
"""

import h5py
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from .features import extract, CONV, PHYS, WORK, ALL
from .dataset import load_obs
from .events import BENIGN, FAULTS

DECISION = {"benign_step": "HOLD", "benign_train": "HOLD", "benign_idle_drop": "HOLD",
            "bolted_pp": "TRIP", "resistive_pp": "TRIP", "high_z": "TRIP",
            "series_arc": "ALERT"}
TRIP_CLASSES = ("bolted_pp", "resistive_pp", "high_z")


# ---------------------------------------------------------------- features

def feature_table(h5path, windows=(0.25e-3, 0.5e-3, 1.0e-3), verbose=True):
    """Extract features for every event at each decision window.
    Returns a DataFrame with one row per (event, window)."""
    rows = []
    with h5py.File(h5path, "r") as h:
        ev = h["events"]
        keys = sorted(ev.keys())
        for n, k in enumerate(keys):
            e = ev[k]
            obs = load_obs(e)
            pr = e["params"].attrs
            base = dict(event=k, label=e.attrs["label"], background=e.attrs["background"],
                        composite=bool(e.attrs["composite"]),
                        P_rated=pr["P_rated"], C_bus=pr["C_bus"], L_line=pr["L_line"],
                        noise_frac=pr["noise_frac"], adc_bits=pr["adc_bits"],
                        R_f=pr.get("ev_R_f", np.nan), arc_place=pr.get("ev_arc_place", np.nan),
                        t_ramp=pr.get("ev_t_ramp", pr.get("ev_t_ramp_bg", np.nan)))
            for W in windows:
                f = extract(obs, pr["I_rated"], pr["V_ref"], W=W)
                rows.append({**base, "W_ms": W * 1e3, **f})
            if verbose and (n + 1) % 200 == 0:
                print(f"  features {n + 1}/{len(keys)}", flush=True)
    df = pd.DataFrame(rows)
    df["decision"] = df["label"].map(DECISION)
    return df


# ---------------------------------------------------------------- gate 2

def threshold_study(df, W_ms=1.0, ft_target=1e-3, miss_target=1e-2):
    """Conventional detectors on CONV features. For each detector, sweep the
    threshold(s) and report (a) the best achievable missed-trip rate at
    zero false trips, per fault class; (b) whether any setting reaches the
    MODEL.md targets; (c) the gray-zone fraction: fault events lying inside
    the benign envelope in (di_max, didt_max)."""
    d = df[df.W_ms == W_ms]
    ben = d[d.label.isin(BENIGN)]
    trip = d[d.label.isin(TRIP_CLASSES)]
    out = {}
    m_env = ben.di_max.quantile(1.0 - ft_target)     # threshold giving FT <= target
    d_env = ben.didt_max.quantile(1.0 - ft_target)
    m_max, d_max = ben.di_max.max(), ben.didt_max.max()

    def miss(sub, cond):
        return 1.0 - cond(sub).mean() if len(sub) else np.nan

    v_env = ben.v_min.min()          # deepest benign sag -> v-collapse threshold
    for det, cond in {
        "magnitude": lambda s: s.di_max > m_max,
        "di/dt": lambda s: s.didt_max > d_max,
        "v-collapse": lambda s: s.v_min < v_env,
        "dual AND": lambda s: (s.di_max > m_max) & (s.didt_max > d_max),
        "Layer 1 (mag OR di/dt OR v-collapse)":
            lambda s: (s.di_max > m_max) | (s.didt_max > d_max) | (s.v_min < v_env),
    }.items():
        out[det] = {c: miss(trip[trip.label == c], cond) for c in TRIP_CLASSES}
        out[det]["all_trip"] = miss(trip, cond)
    # gray-zone fraction: inside benign envelope on BOTH axes
    inside = (trip.di_max <= m_max) & (trip.didt_max <= d_max) & (trip.v_min >= v_env)
    gz = {c: float(inside[trip.label == c].mean()) for c in TRIP_CLASSES}
    gz["all_trip"] = float(inside.mean())
    # sweep a joint OR detector to see whether targets are reachable at all
    reach = False
    best = (1.0, 1.0)
    for qm in np.linspace(0.90, 1.0, 41):
        for qd in np.linspace(0.90, 1.0, 41):
            tm, td = ben.di_max.quantile(qm), ben.didt_max.quantile(qd)
            ft = ((ben.di_max > tm) | (ben.didt_max > td) | (ben.v_min < v_env)).mean()
            ms = 1.0 - ((trip.di_max > tm) | (trip.didt_max > td) | (trip.v_min < v_env)).mean()
            if ft <= ft_target and ms <= miss_target:
                reach = True
            if ft <= ft_target and ms < best[1]:
                best = (ft, ms)
    return dict(miss_at_zero_ft=out, gray_zone_fraction=gz,
                envelope=dict(di_max=m_max, didt_max=d_max, v_min=v_env),
                targets_reachable=reach, best_miss_at_ft_target=best)


# ---------------------------------------------------------------- gate 3

def _metrics(y_true, y_pred, labels):
    ben = np.isin(labels, BENIGN)
    trp = np.isin(labels, TRIP_CLASSES)
    arc = labels == "series_arc"
    ft = float((y_pred[ben] == "TRIP").mean()) if ben.any() else np.nan
    miss = float((y_pred[trp] == "HOLD").mean()) if trp.any() else np.nan
    arc_det = float((y_pred[arc] == "ALERT").mean()) if arc.any() else np.nan
    per = {c: float((y_pred[labels == c] == "HOLD").mean()) for c in TRIP_CLASSES}
    return dict(false_trip=ft, missed=miss, arc_detect=arc_det, missed_per_class=per,
                acc=float((y_true == y_pred).mean()))


def _fit(Xtr, ytr):
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                         max_leaf_nodes=15, l2_regularization=0.5,
                                         random_state=0)
    return clf.fit(Xtr, ytr)


def classifier_study(df, W_ms=1.0, feature_sets=None, n_splits=5, holdout_P=400e3):
    """Ablation over feature sets with stratified CV and a domain-shift
    holdout (train on P_rated < holdout_P, test on >= holdout_P)."""
    if feature_sets is None:
        feature_sets = {"conventional": CONV, "+physics": CONV + PHYS, "+workload-aware": ALL}
    d = df[df.W_ms == W_ms].reset_index(drop=True)
    y = d["decision"].values
    labels = d["label"].values
    res = {}
    for name, cols in feature_sets.items():
        X = d[cols].values.astype(np.float64)
        pred = np.empty_like(y, dtype=object)
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        for tr, te in skf.split(X, labels):
            pred[te] = _fit(X[tr], y[tr]).predict(X[te])
        cv = _metrics(y, pred, labels)
        # composite subset
        comp = d.composite.values & np.isin(labels, TRIP_CLASSES)
        cv["missed_composite"] = float((pred[comp] == "HOLD").mean()) if comp.any() else np.nan
        # domain shift
        tr = d.P_rated.values < holdout_P
        te = ~tr
        p2 = _fit(X[tr], y[tr]).predict(X[te])
        ds = _metrics(y[te], p2, labels[te])
        res[name] = dict(cv=cv, domain_shift=ds, cv_pred=pred)
    return res


def latency_study(df, windows=(0.25, 0.5, 1.0), cols=ALL, n_splits=5):
    out = {}
    for W in windows:
        d = df[df.W_ms == W].reset_index(drop=True)
        y, labels = d["decision"].values, d["label"].values
        X = d[cols].values.astype(np.float64)
        pred = np.empty_like(y, dtype=object)
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        for tr, te in skf.split(X, labels):
            pred[te] = _fit(X[tr], y[tr]).predict(X[te])
        out[W] = _metrics(y, pred, labels)
    return out


def arc_placement_study(df, W_ms=1.0, cols=ALL, n_splits=5):
    """Series-arc detectability split by placement (line vs load path)."""
    d = df[df.W_ms == W_ms].reset_index(drop=True)
    y, labels = d["decision"].values, d["label"].values
    X = d[cols].values.astype(np.float64)
    pred = np.empty_like(y, dtype=object)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    for tr, te in skf.split(X, labels):
        pred[te] = _fit(X[tr], y[tr]).predict(X[te])
    arc = labels == "series_arc"
    out = {}
    for place, name in ((1.0, "busbar (upstream of C_bus)"), (0.0, "load path (downstream of C_bus)")):
        m = arc & (d.arc_place.values == place)
        out[name] = dict(n=int(m.sum()), detected=float((pred[m] == "ALERT").mean()),
                         onset_found=float(d.onset_found.values[m].mean()))
    return out


def operating_curve(df, W_ms=1.0, cols=ALL, n_splits=5):
    """Classifier false-trip vs missed-trip curve by sweeping the TRIP
    probability threshold (cross-validated probabilities). Also returns
    the miss rate at the MODEL.md false-trip target (0.1%)."""
    d = df[df.W_ms == W_ms].reset_index(drop=True)
    y, labels = d["decision"].values, d["label"].values
    X = d[cols].values.astype(np.float64)
    p_trip = np.zeros(len(d))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    for tr, te in skf.split(X, labels):
        clf = _fit(X[tr], y[tr])
        k = list(clf.classes_).index("TRIP")
        p_trip[te] = clf.predict_proba(X[te])[:, k]
    ben = np.isin(labels, BENIGN)
    trp = np.isin(labels, TRIP_CLASSES)
    ths = np.unique(np.concatenate([[0.0, 1.0], p_trip]))
    ft = np.array([(p_trip[ben] > t).mean() for t in ths])
    ms = np.array([(p_trip[trp] <= t).mean() for t in ths])
    ok = ft <= 1e-3
    miss_at_target = float(ms[ok].min()) if ok.any() else np.nan
    hz = labels == "high_z"
    t_star = ths[ok][np.argmin(ms[ok])] if ok.any() else 1.0
    return dict(thresholds=ths, false_trip=ft, missed=ms, p_trip=p_trip,
                miss_at_ft_target=miss_at_target,
                high_z_miss_at_ft_target=float((p_trip[hz] <= t_star).mean()))
