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

# v0.2.2: gated Layer-2 spec -- two models routed on has_period. TESTED AND
# REJECTED as the default: over 10 CV seeds it is worse than physics-only on
# every metric (missed +0.30, high-Z +0.90), because halving the training data
# per route costs more than removing NaN columns gains at n = 1400. Kept so
# the comparison is reproducible; revisit at dataset v1 (>= 5 000 events).
GATED = {"periodic": ALL, "flat": CONV + PHYS}
from .dataset import load_obs, iter_events, h5_files
from .events import BENIGN, FAULTS

DECISION = {"benign_step": "HOLD", "benign_train": "HOLD", "benign_idle_drop": "HOLD",
            "bolted_pp": "TRIP", "resistive_pp": "TRIP", "high_z": "TRIP",
            "series_arc": "ALERT",
            "bolted_48": "TRIP", "high_z_48": "TRIP"}                     # v0.4
TRIP_CLASSES = ("bolted_pp", "resistive_pp", "high_z", "bolted_48", "high_z_48")
TRIP_800 = ("bolted_pp", "resistive_pp", "high_z")
TRIP_48 = ("bolted_48", "high_z_48")


# ---------------------------------------------------------------- features

def feature_table(h5path, windows=(0.25e-3, 0.5e-3, 1.0e-3), verbose=True, config=None,
                  node="feeder"):
    """Extract features for every event at each decision window.
    config: None for the default stream or a front-end config (see load_obs).
    node: "feeder" or "rack" (v0.4). Features are normalised to the node's
    own rating. Returns a DataFrame with one row per (event, window)."""
    rows = []
    if True:                                            # one file, a glob of shard files, or a list
        for n, (k, e) in enumerate(iter_events(h5path)):
            obs = load_obs(e, config, node=node)
            pr = e["params"].attrs
            if node == "rack":
                I_n, V_n = pr["I_out_rated"], pr["V_ref48"]
            else:
                I_n, V_n = pr["I_rated"], pr["V_ref"]
            base = dict(event=k, label=e.attrs["label"], background=e.attrs["background"],
                        composite=bool(e.attrs["composite"]),
                        P_rated=pr["P_rated"], V_ref=pr["V_ref"], I_rated=pr["I_rated"],  # v0.2.1 (B5)
                        C_bus=pr["C_bus"], L_line=pr["L_line"],
                        noise_frac=pr["noise_frac"], adc_bits=pr["adc_bits"],
                        R_f=pr.get("ev_R_f", np.nan), arc_place=pr.get("ev_arc_place", np.nan),
                        t_ramp=pr.get("ev_t_ramp", pr.get("ev_t_ramp_bg", np.nan)),
                        smoothed=bool(pr.get("ev_smoothed", False)),          # v1
                        T1=pr.get("ev_T1", np.nan), T2=pr.get("ev_T2", np.nan),
                        sched_tier=int(pr.get("ev_sched_tier", 0)),
                        smooth_on=float(pr.get("smooth_on", np.nan)),        # v0.4
                        C_in=pr.get("C_in", np.nan), C_out=pr.get("C_out", np.nan),
                        S_max=pr.get("S_max", np.nan), R_f48=pr.get("ev_R_f48", np.nan),
                        I_lim_out=pr.get("I_lim_out", np.nan), node=node,
                        bus_storage=float(pr.get("bus_storage", 0.0)),         # v0.4.1
                        C_store=float(pr.get("C_store", 0.0)))
            for W in windows:
                f = extract(obs, I_n, V_n, W=W)
                rows.append({**base, "W_ms": W * 1e3, **f})
            if verbose and (n + 1) % 200 == 0:
                print(f"  features {n + 1}", flush=True)
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
    # OPEN-11: the max-of-benign envelope is set by ONE event and moves with n. Percentile rows put the
    # same Layer-1 OR detector at the q-th percentile of each benign axis (v_min: the (1-q)-th) and
    # report the false-trip rate that setting actually costs, next to what it buys.
    rows = {}
    for q in (1.0, 0.999, 0.99):
        tm, td, tv = ben.di_max.quantile(q), ben.didt_max.quantile(q), ben.v_min.quantile(1.0 - q)
        fire = lambda s_, tm=tm, td=td, tv=tv: (s_.di_max > tm) | (s_.didt_max > td) | (s_.v_min < tv)
        ins = ~fire(trip)
        rows["max" if q == 1.0 else f"p{q*100:g}"] = dict(
            q=q, false_trip=float(fire(ben).mean()), missed_all=float(ins.mean()),
            gray_zone={c: float(ins[trip.label == c].mean()) for c in TRIP_CLASSES if (trip.label == c).any()},
            thresholds=dict(di_max=float(tm), didt_max=float(td), v_min=float(tv)))
    return dict(miss_at_zero_ft=out, gray_zone_fraction=gz,
                envelope=dict(di_max=m_max, didt_max=d_max, v_min=v_env),
                targets_reachable=reach, best_miss_at_ft_target=best, percentile_rows=rows)


# ---------------------------------------------------------------- gate 3

def _metrics(y_true, y_pred, labels):
    ben = np.isin(labels, BENIGN)
    trp = np.isin(labels, TRIP_CLASSES)
    arc = labels == "series_arc"
    ft = float((y_pred[ben] == "TRIP").mean()) if ben.any() else np.nan
    miss = float((y_pred[trp] == "HOLD").mean()) if trp.any() else np.nan
    arc_det = float((y_pred[arc] == "ALERT").mean()) if arc.any() else np.nan
    per = {c: float((y_pred[labels == c] == "HOLD").mean()) for c in TRIP_CLASSES if (labels == c).any()}
    t800 = np.isin(labels, TRIP_800)
    t48 = np.isin(labels, TRIP_48)
    return dict(false_trip=ft, missed=miss, arc_detect=arc_det, missed_per_class=per,
                missed_800=float((y_pred[t800] == "HOLD").mean()) if t800.any() else np.nan,
                missed_48=float((y_pred[t48] == "HOLD").mean()) if t48.any() else np.nan,
                acc=float((y_true == y_pred).mean()))


def _fit(Xtr, ytr):
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                         max_leaf_nodes=15, l2_regularization=0.5,
                                         random_state=0)
    return clf.fit(Xtr, ytr)


def _cv_predict(d, spec, n_splits=5, proba_class=None, seed=0):
    """v0.2.1 (D4) / v0.2.2 (gating). Stratified CV predictions for one
    window's rows.

    spec: a column list (one model) or a dict {"periodic": cols, "flat": cols}
    (two models routed on has_period, trained and applied to their own subset
    inside each fold).

    Rows with onset_found == 0 carry features computed from a default index
    and are meaningless; they are excluded from every training fold and
    scored as the relay would score them -- HOLD (nothing was detected) --
    so an undetected fault is counted as a miss rather than learned from.
    With proba_class set, returns P(class) instead of labels (0 for undetected).
    """
    y, labels = d["decision"].values, d["label"].values
    ok = d["onset_found"].values > 0.5
    if isinstance(spec, dict):
        routes = {"periodic": (d["has_period"].values > 0.5, spec["periodic"]),
                  "flat": (d["has_period"].values <= 0.5, spec["flat"])}
    else:
        routes = {"all": (np.ones(len(d), bool), spec)}
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    if proba_class is None:
        out = np.full(len(d), "HOLD", dtype=object)
    else:
        out = np.zeros(len(d))
    for tr, te in skf.split(np.zeros(len(d)), labels):
        for _, (mask, cols) in routes.items():
            X = d[cols].values.astype(np.float64)
            tr_r = tr[ok[tr] & mask[tr]]
            te_r = te[ok[te] & mask[te]]
            if tr_r.size == 0 or te_r.size == 0:
                continue
            clf = _fit(X[tr_r], y[tr_r])
            if proba_class is None:
                out[te_r] = clf.predict(X[te_r])
            else:
                k = list(clf.classes_).index(proba_class)
                out[te_r] = clf.predict_proba(X[te_r])[:, k]
    return out


def _fit_predict_split(d, spec, tr, te):
    """v0.2.2: single train/test split honouring the same routing and
    onset_found rule as _cv_predict (used for the domain-shift holdout)."""
    y = d["decision"].values
    ok = d["onset_found"].values > 0.5
    if isinstance(spec, dict):
        routes = {"periodic": (d["has_period"].values > 0.5, spec["periodic"]),
                  "flat": (d["has_period"].values <= 0.5, spec["flat"])}
    else:
        routes = {"all": (np.ones(len(d), bool), spec)}
    out = np.full(len(d), "HOLD", dtype=object)
    for _, (mask, cols) in routes.items():
        X = d[cols].values.astype(np.float64)
        tr_r = np.flatnonzero(tr & ok & mask)
        te_r = np.flatnonzero(te & ok & mask)
        if tr_r.size and te_r.size:
            out[te_r] = _fit(X[tr_r], y[tr_r]).predict(X[te_r])
    return out[te]


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
        pred = _cv_predict(d, cols, n_splits)                 # v0.2.1 (D4) / v0.2.2 (gating)
        cv = _metrics(y, pred, labels)
        # composite subset
        comp = d.composite.values & np.isin(labels, TRIP_CLASSES)
        cv["missed_composite"] = float((pred[comp] == "HOLD").mean()) if comp.any() else np.nan
        # domain shift
        tr = d.P_rated.values < holdout_P
        te = ~tr
        p2 = _fit_predict_split(d, cols, tr, te)               # v0.2.2
        ds = _metrics(y[te], p2, labels[te])
        res[name] = dict(cv=cv, domain_shift=ds, cv_pred=pred)
    return res


def repeated_study(df, W_ms=1.0, feature_sets=None, seeds=range(10), n_splits=5):
    """v0.2.2 (D3). Repeat the CV ablation over fold seeds and report
    mean +/- std of false-trip, missed and high-Z-missed rates, overall and on
    the periodic / flat background subsets. Single-seed differences of a few
    events are inside this spread; this is the table to quote."""
    if feature_sets is None:
        feature_sets = {"conventional": CONV, "+physics": CONV + PHYS, "+workload-aware": ALL}
    d = df[df.W_ms == W_ms].reset_index(drop=True)
    labels = d["label"].values
    ben, trp = np.isin(labels, BENIGN), np.isin(labels, TRIP_CLASSES)
    per = (d.background.values == "train")
    hz = labels == "high_z"
    keys = ["false_trip", "missed", "high_z_missed",
            "periodic_false_trip", "periodic_missed", "flat_false_trip", "flat_missed"]
    out = {}
    for name, spec in feature_sets.items():
        rows = []
        for s in seeds:
            p = _cv_predict(d, spec, n_splits, seed=s)
            rows.append([(p[ben] == "TRIP").mean(), (p[trp] == "HOLD").mean(), (p[hz] == "HOLD").mean(),
                         (p[per & ben] == "TRIP").mean(), (p[per & trp] == "HOLD").mean(),
                         (p[~per & ben] == "TRIP").mean(), (p[~per & trp] == "HOLD").mean()])
        r = np.array(rows)
        out[name] = {k: dict(mean=float(r[:, i].mean()), std=float(r[:, i].std())) for i, k in enumerate(keys)}
    return out


def latency_study(df, windows=(0.25, 0.5, 1.0), cols=ALL, n_splits=5):
    out = {}
    for W in windows:
        d = df[df.W_ms == W].reset_index(drop=True)
        y, labels = d["decision"].values, d["label"].values
        pred = _cv_predict(d, cols, n_splits)                 # v0.2.1 (D4)
        out[W] = _metrics(y, pred, labels)
    return out


def arc_placement_study(df, W_ms=1.0, cols=ALL, n_splits=5):
    """Series-arc detectability split by placement (line vs load path)."""
    d = df[df.W_ms == W_ms].reset_index(drop=True)
    y, labels = d["decision"].values, d["label"].values
    pred = _cv_predict(d, cols, n_splits)                     # v0.2.1 (D4)
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
    p_trip = _cv_predict(d, cols, n_splits, proba_class="TRIP")   # v0.2.1 (D4)
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


# ---------------------------------------------------------------- OPEN-12: front-end study

def rate_study(h5path, configs, seeds=range(10), n_splits=5, verbose=True, cache_dir=None):
    """OPEN-12. For every (f_fast, bits) front end stored in the dataset:
    extract features, run the 10-seed repeated CV for +physics and
    +workload-aware, the Gate-2 gray-zone fraction, and the 0.25 ms latency
    point. Returns {config_name: {...}} and caches each feature table."""
    import os
    from .dataset import _cfg_name
    out = {}
    for cfg in configs:
        name = "default" if cfg is None else (cfg if isinstance(cfg, str) else _cfg_name(*cfg))
        csv = None if cache_dir is None else os.path.join(cache_dir, f"features_{name}.csv")
        if csv and os.path.exists(csv):
            df = pd.read_csv(csv)
        else:
            if verbose:
                print(f"  extracting {name} ...", flush=True)
            df = feature_table(h5path, verbose=False, config=cfg)
            if csv:
                df.to_csv(csv, index=False)
        rs = repeated_study(df, feature_sets={"+physics": CONV + PHYS, "+workload-aware": ALL},
                            seeds=seeds, n_splits=n_splits)
        ts = threshold_study(df)
        lat = latency_study(df, windows=(0.25,), cols=ALL, n_splits=n_splits)[0.25]
        d1 = df[df.W_ms == 1.0]
        out[name] = dict(repeated=rs, gray_zone_high_z=ts["gray_zone_fraction"]["high_z"],
                         layer1_high_z_missed=ts["miss_at_zero_ft"]["Layer 1 (mag OR di/dt OR v-collapse)"]["high_z"],
                         latency_025=lat, onset_found=float(d1.onset_found.mean()),
                         fs_fast=float(d1.fs_fast.iloc[0]), adc_bits=float(d1.adc_bits_used.median()))
        if verbose:
            w = rs["+workload-aware"]
            print(f"  {name:14s} FT {w['false_trip']['mean']*100:5.2f}±{w['false_trip']['std']*100:4.2f}"
                  f"  missed {w['missed']['mean']*100:5.2f}±{w['missed']['std']*100:4.2f}"
                  f"  high-Z {w['high_z_missed']['mean']*100:5.2f}±{w['high_z_missed']['std']*100:4.2f}"
                  f"  | gray-zone high-Z {ts['gray_zone_fraction']['high_z']*100:4.1f}%"
                  f"  | 0.25 ms: FT {lat['false_trip']*100:4.1f} missed {lat['missed']*100:4.1f}", flush=True)
    return out


# ---------------------------------------------------------------- v0.4: sensing-node study

def _cache_matches(csv, h5path, verbose=True):
    """The node cache path does not carry the dataset name, so a table left by ANOTHER dataset
    would be reused silently. Accept the cache only if it holds exactly the h5's events."""
    try:
        n = 0
        for f in h5_files(h5path):
            with h5py.File(f, "r") as h:
                n += len(h["events"])
    except OSError:
        return True                                   # no h5 to check against (cache-only use)
    n_csv = pd.read_csv(csv, usecols=["event"]).event.nunique()
    if n_csv != n and verbose:
        print(f"  cache {csv} holds {n_csv} events, {h5path} has {n}: re-extracting", flush=True)
    return n_csv == n


def node_study(h5path, seeds=range(10), n_splits=5, verbose=True, cache_dir=None):
    """v0.4. Repeated CV for three relay configurations on the same events:
    feeder-only (i_L, v_bus), rack-only (i_co, v_out), and both (feature
    concatenation). Reports the usual rates plus missed 800 V faults and
    missed 48 V faults separately -- prediction 1 of the v0.4 spec."""
    import os
    tabs = {}
    for node in ("feeder", "rack"):
        csv = None if cache_dir is None else os.path.join(cache_dir, f"features_{node}.csv")
        if csv and os.path.exists(csv) and _cache_matches(csv, h5path, verbose):
            tabs[node] = pd.read_csv(csv)
        else:
            if verbose:
                print(f"  extracting {node} node ...", flush=True)
            tabs[node] = feature_table(h5path, verbose=False, node=node)
            if csv:
                tabs[node].to_csv(csv, index=False)
    fe, ra = tabs["feeder"], tabs["rack"]
    both, both_cols = two_node_table(fe, ra)
    # v0.4.2: the feeder scored on its own responsibility -- 48 V faults are
    # HOLD from the feeder's point of view (they belong to the rack relay)
    fe_resp = fe.copy()
    fe_resp["decision"] = fe_resp["label"].map(lambda l: "HOLD" if l in TRIP_48 else DECISION[l])
    sets = {"feeder only": (fe, ALL), "feeder, 800 V duty": (fe_resp, ALL),
            "rack only": (ra, ALL), "feeder + rack": (both, both_cols)}
    out = {}
    for name, (df, cols) in sets.items():
        d = df[df.W_ms == 1.0].reset_index(drop=True)
        labels = d["label"].values
        ben, t800, t48 = np.isin(labels, BENIGN), np.isin(labels, TRIP_800), np.isin(labels, TRIP_48)
        hz = labels == "high_z"
        rows = []
        for s in seeds:
            p = _cv_predict(d, cols, n_splits, seed=s)
            rows.append([(p[ben] == "TRIP").mean(), (p[t800] == "HOLD").mean(), (p[hz] == "HOLD").mean(),
                         (p[t48] == "HOLD").mean(), (p[labels == "bolted_48"] == "HOLD").mean(),
                         (p[labels == "high_z_48"] == "HOLD").mean()])
        r = np.array(rows)
        keys = ["false_trip", "missed_800", "high_z_missed", "missed_48", "bolted_48_missed", "high_z_48_missed"]
        out[name] = {k: dict(mean=float(r[:, i].mean()), std=float(r[:, i].std())) for i, k in enumerate(keys)}
        if verbose:
            f = lambda k: f"{out[name][k]['mean']*100:5.2f}±{out[name][k]['std']*100:4.2f}"
            print(f"  {name:14s} FT {f('false_trip')}  missed-800V {f('missed_800')}  high-Z {f('high_z_missed')}"
                  f"  | missed-48V {f('missed_48')}  (bolted {f('bolted_48_missed')}, high-Z {f('high_z_48_missed')})", flush=True)
    return out, tabs


def two_node_table(fe, ra):
    """Feeder + rack feature concatenation with the "detected at either node" onset rule
    (the 'feeder + rack' relay of node_study). Returns (table, column list)."""
    both = fe.copy()
    for c in ALL:
        both[c + "_rack"] = ra[c].values
    both["onset_found"] = np.maximum(fe.onset_found.values, ra.onset_found.values)
    return both, ALL + [c + "_rack" for c in ALL]


def _threshold_at_budget(p_ben, budget):
    """Lowest P(TRIP) threshold whose false-trip rate on p_ben is <= budget (decision: p > t).
    k = floor(budget * n) benign events are allowed above it."""
    k = int(np.floor(budget * p_ben.size + 1e-9))
    srt = np.sort(p_ben)[::-1]
    return float(srt[k]) if k < srt.size else 0.0


def operating_points(df, cols, budgets=(1e-3, 5e-4, 2e-4), seeds=range(10), n_splits=5,
                     W_ms=1.0, nested=False, verbose=True):
    """Operating curve of one relay at fixed false-trip budgets, repeated over fold seeds.

    nested=False  'in-sample': the threshold is the best one on the same out-of-fold P(TRIP)
                  it is scored on. Optimistic; this is what the hand computation did.
    nested=True   'held-out calibration': inside every outer fold the threshold is chosen on
                  inner-CV probabilities of the TRAINING part only, then applied to the held-out
                  fold, which took no part in choosing it. The realised false-trip rate is then
                  a result, not a constraint - it can land above the budget.
    Returns {budget: {metric: {mean, std}}} with metrics false_trip, missed, missed_800,
    high_z_missed, missed_48, threshold."""
    d = df[df.W_ms == W_ms].reset_index(drop=True)
    labels = d["label"].values
    ben, trp = np.isin(labels, BENIGN), np.isin(labels, TRIP_CLASSES)
    t800, t48, hz = np.isin(labels, TRIP_800), np.isin(labels, TRIP_48), labels == "high_z"
    acc = {b: [] for b in budgets}
    for s in seeds:
        if not nested:
            p = _cv_predict(d, cols, n_splits, proba_class="TRIP", seed=s)
            trips = {b: (p > _threshold_at_budget(p[ben], b), _threshold_at_budget(p[ben], b)) for b in budgets}
        else:
            skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=s)
            fired = {b: np.zeros(len(d), bool) for b in budgets}
            ths = {b: [] for b in budgets}
            for tr, te in skf.split(np.zeros(len(d)), labels):
                dtr = d.iloc[tr].reset_index(drop=True)
                p_in = _cv_predict(dtr, cols, n_splits, proba_class="TRIP", seed=1000 + s)   # calibration
                okm = d["onset_found"].values > 0.5
                X, y = d[cols].values.astype(np.float64), d["decision"].values
                clf = _fit(X[tr[okm[tr]]], y[tr[okm[tr]]])
                p_te = np.zeros(te.size)
                m = okm[te]
                p_te[m] = clf.predict_proba(X[te[m]])[:, list(clf.classes_).index("TRIP")]
                for b in budgets:
                    t = _threshold_at_budget(p_in[ben[tr]], b)
                    fired[b][te] = p_te > t
                    ths[b].append(t)
            trips = {b: (fired[b], float(np.mean(ths[b]))) for b in budgets}
        for b, (f, t) in trips.items():
            acc[b].append([f[ben].mean(), (~f[trp]).mean(), (~f[t800]).mean(), (~f[hz]).mean(), (~f[t48]).mean(), t])
        if verbose:
            print(f"    seed {s} done", flush=True)
    keys = ["false_trip", "missed", "missed_800", "high_z_missed", "missed_48", "threshold"]
    out = {}
    for b in budgets:
        r = np.array(acc[b])
        out[b] = {k: dict(mean=float(r[:, i].mean()), std=float(r[:, i].std())) for i, k in enumerate(keys)}
        out[b]["n_benign"] = int(ben.sum())
        out[b]["rows"] = r.tolist()                      # per-seed values, columns = keys (for pooling runs)
    return out


def feature_table_both(h5path, windows=(0.25e-3, 0.5e-3, 1.0e-3), verbose=True):
    """v0.4: feeder and rack features side by side (rack columns suffixed
    _rk), so a classifier can use one node or both. Same row structure."""
    a = feature_table(h5path, windows, verbose, node="feeder")
    b = feature_table(h5path, windows, verbose=False, node="rack")
    feat = ALL + ["onset_found", "t_on_rel"]
    b = b[["event", "W_ms"] + feat].rename(columns={c: c + "_rk" for c in feat})
    return a.merge(b, on=["event", "W_ms"])


ALL_RK = [c + "_rk" for c in ALL]
