"""dcsim.confirm — OPEN-14 hold-and-confirm study.

Stage 1 decides at W1 (0.25 ms) with the existing Layer-2 features. Events
whose TRIP probability falls in an ambiguous band are re-examined at W2
(2.5 / 4.5 ms) with the same features recomputed on the longer window plus
three that only exist there:

  ring_decay   change in bus-resonance damping after the event. A high-Z
               fault adds a positive resistance across the bus (ringing
               dies faster); a CPL step adds a more negative incremental
               resistance (ringing lasts longer). Needs several ring
               periods (0.2-1.4 ms across the sweep), hence W2.
  settle       continued current movement after the first millisecond,
               relative to the step: a fault has finished on the L/R_f and
               tau_c scales; a benign ramp of 2-10 ms is still rising.
  i2t          integral of (i / I_rated)^2 over the window, p.u.^2*ms --
               the thermal gate; ambiguous events are, by construction,
               well below any busbar limit.

Pre-registered decision (2026-09-10): the confirmation stage is kept only
if, over 10 seeds, it reduces false trips on the ambiguous set by more than
the paired standard deviation of the comparison without raising missed
faults. Otherwise the residue is routed to Layer 3 (hold and monitor on the
workload timescale) and this stage is dropped from the architecture.

Kept separate from features.py so the cached feature tables and the OPEN-12
rate study are untouched.
"""

import os
import hashlib
import numpy as np
import pandas as pd
import h5py
from scipy import signal
from sklearn.model_selection import StratifiedKFold
from .features import extract, detect_onset, _movavg, CONV, PHYS, WORK, ALL, F_FAST
from .dataset import load_obs
from .studies import _fit, DECISION, TRIP_CLASSES
from .events import BENIGN

CONFIRM = ["ring_decay", "settle", "i2t", "di_late"]

W1 = 0.25e-3
W2S = (2.5e-3, 4.5e-3)


# ---------------------------------------------------------------- confirmation features

def extract_confirm(obs, I_rated, W2):
    """Confirmation-window features on the fast stream, W2 after detected onset."""
    fi = obs["fast_i"].astype(np.float64)
    fv = obs["fast_v"].astype(np.float64)
    fs = float(obs.get("fs_fast", F_FAST))
    n_pre = max(int(0.15e-3 * fs), 4)
    n5 = max(int(5e-6 * fs), 1)
    k_on, i_pre, v_pre, sig_i, sig_v, found = detect_onset(fi, fv, n_pre, obs["fs_i"], obs["fs_v"], n_sm=n5)
    nW = max(int(W2 * fs), 8)
    k1 = min(k_on + nW, fi.size)
    wi = fi[k_on:k1] - i_pre
    t = np.arange(wi.size) / fs
    f = {}
    # ---- i2t (p.u.^2 * ms) over the whole window including the pre-event level
    f["i2t"] = float(np.sum((fi[k_on:k1] / I_rated) ** 2) / fs * 1e3)
    # ---- settling: movement in the last 0.5 ms vs the largest excursion
    n1ms = max(int(1e-3 * fs), 4)
    n05 = max(int(0.5e-3 * fs), 4)
    sm = _movavg(wi, max(int(10e-6 * fs), 1))
    di_max = np.abs(sm).max() + 1e-9
    late = sm[-n05:]
    f["settle"] = float(abs(late[-1] - late[0]) / di_max)
    f["di_late"] = float((sm[-1] - sm[min(n1ms, sm.size - 1)]) / I_rated) if sm.size > n1ms else 0.0
    # ---- ring decay: residual after removing the slow trend, envelope slope
    if wi.size >= 4 * n5 + 8:
        # slow trend: 200 us moving average; residual = ringing + noise
        tr = _movavg(wi, max(int(200e-6 * fs), 3))
        res = wi - tr
        # restrict to after the first 0.3 ms (let the front and L/R_f transient pass)
        k_start = min(max(int(0.3e-3 * fs), 2), res.size - 8)
        r = res[k_start:]
        env = np.abs(signal.hilbert(r - r.mean()))
        env = _movavg(env, max(int(50e-6 * fs), 1)) + 1e-9
        tt = np.arange(env.size) / fs
        # log-envelope slope (1/s); positive = decaying. Guard against noise floor:
        # only fit while the envelope is above 3x the pre-event residual noise.
        noise = np.std(fi[:n_pre] - _movavg(fi[:n_pre], max(min(int(50e-6 * fs), n_pre // 3), 1))) + 1e-9
        m = env > 3.0 * noise
        if m.sum() >= 8:
            A = np.vstack([tt[m], np.ones(m.sum())]).T
            slope, _ = np.linalg.lstsq(A, np.log(env[m]), rcond=None)[0]
            f["ring_decay"] = float(-slope * 1e-3)      # per ms, positive = decays
        else:
            f["ring_decay"] = 0.0                         # no ringing above noise
    else:
        f["ring_decay"] = 0.0
    f["onset_found_c"] = 1.0 if found else 0.0
    return f


# ---------------------------------------------------------------- table

def confirm_table(h5path, w2s=W2S, verbose=True, cache=None):
    """One row per event: stage-1 features at W1, and for each W2 the full
    feature set recomputed at W2 plus the confirmation features (suffix
    _W<ms>). Cached to CSV keyed on this module's source."""
    key = hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:12]
    if cache and os.path.exists(cache) and os.path.exists(cache + ".meta") \
            and open(cache + ".meta").read().strip() == key:
        return pd.read_csv(cache)
    rows = []
    with h5py.File(h5path, "r") as h:
        ev = h["events"]
        keys = sorted(ev.keys())
        for n, k in enumerate(keys):
            e = ev[k]
            obs = load_obs(e)
            pr = e["params"].attrs
            base = dict(event=k, label=e.attrs["label"], background=e.attrs["background"],
                        composite=bool(e.attrs["composite"]), P_rated=pr["P_rated"],
                        V_ref=pr["V_ref"], I_rated=pr["I_rated"], C_bus=pr["C_bus"],
                        R_f=pr.get("ev_R_f", np.nan), arc_place=pr.get("ev_arc_place", np.nan),
                        t_ramp=pr.get("ev_t_ramp", pr.get("ev_t_ramp_bg", np.nan)),
                        smoothed=bool(pr.get("ev_smoothed", False)))
            f1 = extract(obs, pr["I_rated"], pr["V_ref"], W=W1)
            row = {**base, **{c: f1[c] for c in ALL + ["onset_found"]}}
            for W2 in w2s:
                tag = f"_W{W2 * 1e3:g}"
                f2 = extract(obs, pr["I_rated"], pr["V_ref"], W=W2)
                fc = extract_confirm(obs, pr["I_rated"], W2)
                row.update({c + tag: f2[c] for c in ALL})
                row.update({c + tag: fc[c] for c in CONFIRM})
            rows.append(row)
            if verbose and (n + 1) % 200 == 0:
                print(f"  confirm features {n + 1}/{len(keys)}", flush=True)
    df = pd.DataFrame(rows)
    df["decision"] = df["label"].map(DECISION)
    if cache:
        df.to_csv(cache, index=False)
        open(cache + ".meta", "w").write(key)
    return df


# ---------------------------------------------------------------- study

def _cv_proba(X, y, labels, ok, seed, n_splits=5):
    """Out-of-fold P(TRIP) (0 for undetected onsets)."""
    p = np.zeros(len(y))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for tr, te in skf.split(X, labels):
        tr = tr[ok[tr]]
        te = te[ok[te]]
        if tr.size == 0 or te.size == 0:
            continue
        clf = _fit(X[tr], y[tr])
        k = list(clf.classes_).index("TRIP")
        p[te] = clf.predict_proba(X[te])[:, k]
    return p


def two_stage_study(df, w2s=W2S, seeds=range(10), n_splits=5, q_hi=0.995, q_lo=0.005,
                    i_ceiling_pu=1.5):
    """Compare, over seeds:
      single@W1            : existing classifier at 0.25 ms, TRIP if P > 0.5
      single@W2            : all features at W2 (+ confirmation features), TRIP if P > 0.5
      two-stage (no conf)  : stage 1 at W1 with an ambiguous band; band re-decided at W2
                             with the W2 feature set WITHOUT the confirmation features
      two-stage (+conf)    : same, WITH the confirmation features
    Ambiguous band from stage-1 out-of-fold probabilities: t_hi = q_hi quantile of
    benign P(TRIP) (nothing trips fast unless clearly a fault), t_lo = q_lo quantile
    of trip-class P(TRIP) (nothing holds fast unless clearly benign). Events above the
    current ceiling trip at stage 1 regardless.
    Reports false trip, missed, high-Z missed, confirm fraction, and decision latency."""
    d = df.reset_index(drop=True)
    y, labels = d["decision"].values, d["label"].values
    ok = d["onset_found"].values > 0.5
    ben = np.isin(labels, BENIGN)
    trp = np.isin(labels, TRIP_CLASSES)
    hz = labels == "high_z"
    X1 = d[ALL].values.astype(np.float64)
    over = (d["di_max"].values > i_ceiling_pu)             # p.u. of I_rated at W1
    out = {}
    rows = {k: [] for k in ["single@W1"] + [f"single@W{w*1e3:g}" for w in w2s]
            + [f"two-stage@W{w*1e3:g} (no conf)" for w in w2s] + [f"two-stage@W{w*1e3:g} (+conf)" for w in w2s]}
    band_frac = {f"W{w*1e3:g}": [] for w in w2s}
    for s in seeds:
        p1 = _cv_proba(X1, y, labels, ok, s, n_splits)
        pred1 = np.where(p1 > 0.5, "TRIP", "HOLD")
        rows["single@W1"].append(_rates(pred1, ben, trp, hz))
        t_hi = np.quantile(p1[ben & ok], q_hi)
        t_lo = np.quantile(p1[trp & ok], q_lo)
        amb = ok & (p1 >= t_lo) & (p1 <= t_hi) & ~over
        for w in w2s:
            tag = f"_W{w*1e3:g}"
            colsA = [c + tag for c in ALL]
            colsB = colsA + [c + tag for c in CONFIRM]
            for name, cols in ((f"single@W{w*1e3:g}", colsB),):
                X2 = d[cols].values.astype(np.float64)
                p2 = _cv_proba(X2, y, labels, ok, s, n_splits)
                rows[name].append(_rates(np.where(p2 > 0.5, "TRIP", "HOLD"), ben, trp, hz))
            for name, cols in ((f"two-stage@W{w*1e3:g} (no conf)", colsA),
                               (f"two-stage@W{w*1e3:g} (+conf)", colsB)):
                pred = np.where(p1 > t_hi, "TRIP", "HOLD").astype(object)
                pred[over & ok] = "TRIP"
                if amb.sum() >= 2 * n_splits:
                    # stage 2: CV inside the ambiguous population only
                    X2 = d[cols].values.astype(np.float64)
                    idx = np.flatnonzero(amb)
                    lab_a = labels[idx]
                    # stratify on decision (labels may have singletons in the band)
                    p2 = np.zeros(idx.size)
                    ya = y[idx]
                    if len(set(ya)) > 1:
                        skf = StratifiedKFold(n_splits=min(n_splits, max(2, min(np.bincount(pd.factorize(ya)[0])))),
                                              shuffle=True, random_state=s)
                        for tr, te in skf.split(X2[idx], ya):
                            clf = _fit(X2[idx][tr], ya[tr])
                            k = list(clf.classes_).index("TRIP") if "TRIP" in clf.classes_ else None
                            p2[te] = clf.predict_proba(X2[idx][te])[:, k] if k is not None else 0.0
                    pred[idx] = np.where(p2 > 0.5, "TRIP", "HOLD")
                r = _rates(pred, ben, trp, hz)
                r["confirm_frac"] = float(amb.mean())
                r["confirm_frac_faults"] = float(amb[trp].mean())
                r["confirm_frac_benign"] = float(amb[ben].mean())
                rows[name].append(r)
            band_frac[f"W{w*1e3:g}"].append(float(amb.mean()))
    for name, rs in rows.items():
        keys = rs[0].keys()
        out[name] = {k: dict(mean=float(np.mean([r[k] for r in rs])), std=float(np.std([r[k] for r in rs])))
                     for k in keys}
    return out


def _rates(pred, ben, trp, hz):
    return dict(false_trip=float((pred[ben] == "TRIP").mean()),
                missed=float((pred[trp] == "HOLD").mean()),
                high_z_missed=float((pred[hz] == "HOLD").mean()))
