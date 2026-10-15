"""run_hil_frontend_study.py — check (k), node side: do the relay's features and decisions survive the HIL output chain?

HIL_TESTBED_PLAN §2.8 / §5.1 and MODEL_READINESS §2. The plant half (dcsim_rt step sweep) says the physics transfers
at <= 5-10 us; this script says whether the RELAY does, i.e. whether the 15 features computed by the node from the
HIL's analog outputs are the features the model was trained on.

Chains, applied to the stored 2 MSa/s fast streams of a dataset (both nodes), then features.extract at W:
  ref        the training domain: the stored 2 MSa/s stream as feature_table() uses it (fs = 2 MSa/s)
  node_ideal the node front end with an ideal (continuous) source: clip at the node full scale -> 4th-order 100 kHz
             Butterworth -> 500 kSa/s -> 16-bit at the node full scale        (isolates issue 1 of the 13 Oct brief:
             full scale + clipping + 100 kHz filter + 500 kSa/s, no ZOH)
  hil_<dt>   the HIL chain: anti-alias at 0.4/dt (synth's own rule; the box computes the physics at step dt and its
             output is band-limited to its Nyquist -- it never holds the stored stream's 1 MHz sensor noise; 14 Oct
             diagnostic onset_cases_hil_1us) -> zero-order hold at dt (1, 2, 5, 10, 20 us) -> 16-bit DAC over 0-10 V =
             0..node full scale (saturating) -> + box AO noise (--box-noise, rms fraction of full scale, white at
             2 MSa/s) -> the node front end as above.  --no-hil-aa reproduces the 13/14 Oct runs (hold of the raw
             stored stream), which overstate the staircase cost.
  dac_replay the bench-control fallback: ZOH 1 us, 12-bit over 0-3.3 V = 0..node full scale -> node front end
Node full scales (SCALING_SHEET / HIL plan §4.2): rack 16.5 x I_out,rated and 1.45 x V_ref48; feeder 2.64 x I_rated
and 1.45 x V_ref. The slow stream (cadence / WORK features) is the stored one in every chain, so WORK features are
identical by construction and only CONV + PHYS are compared. Onset thresholds keep the record's fs_i / fs_v, as the
firmware fixtures do.

Scores (per node, per chain, vs ref):
  1. onset: fraction found, |dt_onset| median / p95 (us)
  2. features: |delta| / sigma_ref per feature (sigma_ref = std of the feature over the ref set), median and p95,
     and the fraction of events moved by more than 0.1 sigma
  3. decisions, if --train-table is given (data/nodes_<set> with features_<node>.csv): fit studies._fit on the table
     (W_ms == W, onset_found > 0.5, cols studies.ALL), score EVERY event of ref and of every chain with the relay's
     rule (studies._cv_predict: no onset -> HOLD, P(TRIP) = 0) -> % identical decisions, new trips split by label
     class as studies._metrics does it: BENIGN (= false trips the HIL would show), series_arc (ALERT class, neither),
     TRIP_CLASSES (ref missed, chain caught); lost trips split the same way (TRIP_CLASSES = new misses); onsets
     that appear / disappear; mean |delta P(TRIP)|
     --holdout drops the scored events from the training rows (out-of-sample decisions; without it the ref chain is
     in-sample and a 300-iteration / 15-leaf model memorises it, so every perturbation of a boundary event flips).
     Per-event decisions go to <out>/hil_frontend_decisions_W<W>.csv (event, label, node, chain, onset_found,
     decision, p_trip) and the summary gets a breakdown: lost / new trips by label, P(TRIP)_ref of the flipped
     events (boundary or deep), and the signed mean dP(TRIP) on fault and benign events (bias direction).
     --train-chain <chain> (e.g. hil_5us) retrains on that chain's OWN features of the scored events instead of the
     train table: stratified 5-fold CV over labels, every chain scored out-of-fold with the same folds -> the
     "retrained on the HIL front end" transfer numbers (HIL plan F6). Works with --from-csv (seconds, no h5).
     Late onsets: a chain can fire the detector within the last samples of a record (a tail artefact the ref stream
     never has). Then the decision window is incomplete, extract() cannot run (and would crash on < 10 us of data):
     the row keeps onset_found = 1, gets window_short = 1 and NaN features, and is scored as no decision (HOLD,
     P(TRIP) = 0) -- the relay would not have decided inside the record either. Counted per chain in the summary.
     Checkpointing: rows are appended to <out>/hil_frontend_features_W<W>.csv every 50 events; --resume skips the
     events already in it, so a crash or Ctrl-C costs at most 50 events.
  4. --save-tables writes features_<node>_<chain>.csv in feature_table() layout so run_operating_study.py /
     studies.operating_points can be run on a chain (= "retrained on the HIL front end")

Usage (repo root, .venv):
  python scripts/run_hil_frontend_study.py "data/events_v1large044_s*.h5" --n-per-label 100 --W 0.25
  python scripts/run_hil_frontend_study.py "data/events_v1xl6k_s*.h5" --n-per-label 200 --train-table data/nodes_v1xl6k
Writes <out>/hil_frontend_summary.md and the per-event feature CSVs. Nothing in dcsim/ is modified: the chains are
built here from the stored streams; the generator-side front-end option (MODEL.md 0.4.5) is a separate step.
"""
import sys, os, argparse, functools, time
import numpy as np, pandas as pd
from scipy import signal
sys.path.insert(0, os.getcwd())
from dcsim import features as F
from dcsim.dataset import iter_events, load_obs
from dcsim.features import extract, CONV, PHYS, ALL, F_FAST
from dcsim.studies import DECISION, TRIP_CLASSES, BENIGN

NODE_FS = {"rack": (16.5, 1.45), "feeder": (2.64, 1.45)}   # x rated current, x nominal voltage
F_NODE = 500e3
DECIM = int(F_FAST / F_NODE)                                 # 4
SOS_NODE = signal.butter(4, 100e3, fs=F_FAST, output="sos")  # the node's anti-alias, as an analog filter at 2 MSa/s

# ---- memoise the cadence learner: the slow stream is identical in every chain, so learn once per (event, node)
_cad_cache = {}
_orig_learn = F._learn_cadence
def _memo_learn(st, si, W, t_end):
    key = (st.shape[0], float(st[0]), float(si[:50].sum()), float(si[-50:].sum()), W, round(float(t_end), 9))
    if key not in _cad_cache:
        _cad_cache[key] = _orig_learn(st, si, W, t_end)
    return _cad_cache[key]
F._learn_cadence = _memo_learn


def node_front_end(x, fs_node_scale, bits_node=16, noise_frac=0.0, rng=None):
    """Ideal-source node chain at 2 MSa/s in: clip to [0, FS] -> 100 kHz Butterworth -> every 4th sample -> ADC."""
    x = np.clip(x, 0.0, fs_node_scale)
    zi = signal.sosfilt_zi(SOS_NODE) * x[0]
    y, _ = signal.sosfilt(SOS_NODE, x, zi=zi)
    y = y[::DECIM]
    if noise_frac > 0 and rng is not None:
        y = y + rng.standard_normal(y.shape[0]) * noise_frac * fs_node_scale
    lsb = fs_node_scale / (2 ** bits_node)
    return np.clip(np.round(y / lsb) * lsb, 0.0, fs_node_scale)


def hil_source(x, dt, fs_node_scale, bits_dac=16, phase=0, aa=True, box_noise=0.0, rng=None):
    """[Anti-alias at 0.4/dt ->] zero-order hold of the stored stream at the HIL step dt, DAC-quantised over 0..FS
    (saturating) [-> + box AO noise]."""
    k = int(round(dt * F_FAST))
    if aa and k > 1:
        sos = signal.butter(4, 0.4 / dt, fs=F_FAST, output="sos")
        zi = signal.sosfilt_zi(sos) * x[0]
        x, _ = signal.sosfilt(sos, x, zi=zi)
    if k > 1:
        idx = (np.arange(x.shape[0]) - phase) // k * k + phase
        idx = np.clip(idx, 0, x.shape[0] - 1)
        x = x[idx]
    lsb = fs_node_scale / (2 ** bits_dac - 1)
    y = np.clip(np.round(np.clip(x, 0.0, fs_node_scale) / lsb) * lsb, 0.0, fs_node_scale)
    if box_noise > 0 and rng is not None:
        y = y + rng.standard_normal(y.shape[0]) * box_noise * fs_node_scale
    return y


def chains_for(obs, I_n, V_n, node, steps, rng, node_noise, phase, aa=True, box_noise=0.0, dac_bits=16):
    si_fs, sv_fs = NODE_FS[node][0] * I_n, NODE_FS[node][1] * V_n
    fi, fv = obs["fast_i"].astype(np.float64), obs["fast_v"].astype(np.float64)
    t0 = obs["fast_t"][0]
    base = dict(slow_i=obs["slow_i"], slow_v=obs["slow_v"], slow_t=obs["slow_t"], fs_i=obs["fs_i"], fs_v=obs["fs_v"],
                t_event=obs["t_event"], fs_fast=F_NODE, adc_bits=16)
    def pack(i5, v5):
        return dict(base, fast_i=i5, fast_v=v5, fast_t=t0 + np.arange(i5.shape[0]) / F_NODE)
    out = {"ref": obs}
    out["node_ideal"] = pack(node_front_end(fi, si_fs, 16, node_noise, rng), node_front_end(fv, sv_fs, 16, node_noise, rng))
    for dt in steps:
        out[f"hil_{dt*1e6:g}us"] = pack(node_front_end(hil_source(fi, dt, si_fs, dac_bits, phase, aa, box_noise, rng), si_fs, 16, node_noise, rng),
                                        node_front_end(hil_source(fv, dt, sv_fs, dac_bits, phase, aa, box_noise, rng), sv_fs, 16, node_noise, rng))
    out["dac_replay"] = pack(node_front_end(hil_source(fi, 1e-6, si_fs, 12, phase, aa, box_noise, rng), si_fs, 16, node_noise, rng),
                             node_front_end(hil_source(fv, 1e-6, sv_fs, 12, phase, aa, box_noise, rng), sv_fs, 16, node_noise, rng))
    return out


def onset_of(o):
    fs = float(o["fs_fast"]); n_pre = max(int(0.15e-3 * fs), 4); n5 = max(int(5e-6 * fs), 1)
    k_on, *_ , found = F.detect_onset(o["fast_i"].astype(np.float64), o["fast_v"].astype(np.float64), n_pre, o["fs_i"], o["fs_v"], n_sm=n5)
    return (o["fast_t"][k_on] if found else np.nan), bool(found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("h5"); ap.add_argument("--n-per-label", type=int, default=100)
    ap.add_argument("--steps", default="1,2,5,10,20"); ap.add_argument("--W", type=float, default=0.25)
    ap.add_argument("--node-noise", type=float, default=0.0, help="node noise rms as a fraction of the node full scale (0 until measured)")
    ap.add_argument("--phase", type=int, default=0, help="HIL sample phase in 2 MSa/s samples (0..k-1)")
    ap.add_argument("--no-hil-aa", action="store_true", help="hold the raw stored stream (13/14 Oct behaviour; holds the sensor noise too)")
    ap.add_argument("--dac-bits", type=int, default=16, help="HIL AO resolution over the node full scale for the hil_<dt> chains (16; 12 for a MAB 1511-class output)")
    ap.add_argument("--box-noise", type=float, default=0.0, help="HIL AO noise rms as a fraction of the node full scale, added after the DAC (0 until measured)")
    ap.add_argument("--train-table", default=None, help="data/nodes_<set> dir with features_feeder.csv / features_rack.csv")
    ap.add_argument("--out", default="data/hil_frontend"); ap.add_argument("--save-tables", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--holdout", action="store_true", help="exclude the scored events from the training rows (out-of-sample)")
    ap.add_argument("--train-chain", default=None, help="retrain on this chain's features (5-fold CV, out-of-fold) instead of --train-table")
    ap.add_argument("--resume", action="store_true", help="continue a run: skip the events already in <out>/hil_frontend_features_W<W>.csv")
    ap.add_argument("--from-csv", action="store_true", help="rebuild the summary from <out>/hil_frontend_features_W<W>.csv and "
                    "hil_frontend_decisions_W<W>.csv of a finished run (no h5, no refit)")
    a = ap.parse_args()
    steps = [float(s) * 1e-6 for s in a.steps.split(",")]
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    W = a.W * 1e-3
    feat_csv = os.path.join(a.out, f"hil_frontend_features_W{a.W:g}.csv")
    done_events = set()
    if a.resume and os.path.exists(feat_csv):
        done_events = set(pd.read_csv(feat_csv, usecols=["event"], dtype={"event": str}).event)
        print(f"--resume: {len(done_events)} events already in {feat_csv}", flush=True)
    elif not a.from_csv and os.path.exists(feat_csv):
        os.remove(feat_csv)
    def flush(rows):
        if rows:
            pd.DataFrame(rows).to_csv(feat_csv, mode="a", header=not os.path.exists(feat_csv), index=False)
        rows.clear()
    rows = []; per_label = {}; t_start = time.time(); n_done = 0; n_short = 0
    for k, e in ([] if a.from_csv else iter_events(a.h5)):
        label = e.attrs["label"]
        per_label[label] = per_label.get(label, 0) + 1
        if per_label[label] > a.n_per_label:
            continue
        if k in done_events:
            n_done += 1
            continue
        pr = e["params"].attrs
        for node in ("feeder", "rack"):
            obs = load_obs(e, None, node=node)
            I_n, V_n = (pr["I_out_rated"], pr["V_ref48"]) if node == "rack" else (pr["I_rated"], pr["V_ref"])
            ch = chains_for(obs, I_n, V_n, node, steps, rng, a.node_noise, a.phase, not a.no_hil_aa, a.box_noise, a.dac_bits)
            for name, o in ch.items():
                t_on, found = onset_of(o)
                fs_o = float(o["fs_fast"]); n10 = max(int(10e-6 * fs_o), 1)
                k_on_o = int(np.searchsorted(o["fast_t"], t_on)) if found else 0
                short = found and (o["fast_i"].shape[0] - k_on_o) < n10
                if short:
                    f = {c: np.nan for c in ALL}; n_short += 1
                else:
                    try:
                        f = dict(extract(o, I_n, V_n, W=W))
                    except (IndexError, ValueError) as ex:         # backstop: treat like a short window, but say so
                        print(f"  extract failed on {k}/{node}/{name}: {ex!r} -> window_short", flush=True)
                        f = {c: np.nan for c in ALL}; short = True; n_short += 1
                f.setdefault("onset_found", float(found)); f["window_short"] = float(short)
                win = (o["fast_t"] >= t_on) & (o["fast_t"] < t_on + W) if found else np.zeros(o["fast_t"].shape[0], bool)
                peak_win = float(np.max(o["fast_i"][win]) / I_n) if win.any() else np.nan
                rows.append(dict(event=k, label=label, decision=DECISION[label], node=node, chain=name, W_ms=a.W,
                                 I_rated=I_n, V_ref=V_n, t_onset=t_on,
                                 peak_pu=float(np.max(o["fast_i"]) / I_n), peak_win_pu=peak_win, **f))
        n_done += 1
        if n_done % 50 == 0:
            flush(rows)
            print(f"  {n_done} events, {time.time() - t_start:.0f} s, window_short {n_short}", flush=True)
    flush(rows)
    df = pd.read_csv(feat_csv, dtype={"event": str}, float_precision="round_trip")
    n_done = df.event.nunique()
    if "window_short" not in df:
        df["window_short"] = 0.0
    df["window_short"] = df["window_short"].fillna(0.0)
    chains = [c for c in df.chain.unique() if c != "ref"]
    feats = CONV + PHYS
    md = [f"# check (k), node side - {a.h5}, {n_done} events, W = {a.W} ms, node noise {a.node_noise}, box noise {a.box_noise}, "
          f"phase {a.phase}, HIL DAC {a.dac_bits}-bit, HIL anti-alias at 0.4/dt before the hold: {'OFF (raw hold, overstates the staircase)' if a.no_hil_aa else 'on'}\n"]

    # ---- 1 + 2: onset and feature transfer
    for node in ("feeder", "rack"):
        d = df[df.node == node]
        ref = d[d.chain == "ref"].set_index("event")
        sig = ref.loc[ref.onset_found > 0.5, feats].std().replace(0, np.nan)   # no-onset rows carry default-index features
        fs_pu = NODE_FS[node][0]
        clip_frac = (ref.peak_pu > fs_pu).mean()
        clip_win = (ref.peak_win_pu > fs_pu).mean()
        ws_ref = int((ref.window_short > 0.5).sum())
        md.append(f"\n## {node} node - node full scale {fs_pu} x rated; events exceeding it in the ref stream: "
                  f"{clip_win*100:.1f} % inside the decision window, {clip_frac*100:.1f} % anywhere in the record"
                  + (f"; ref late onsets (window incomplete): {ws_ref}" if ws_ref else "") + "\n")
        md.append("| chain | onset found | |dt_onset| on fault events, median / p95 (us) | features moved > 0.1 sigma (median over features) | worst feature: median / p95 of |d|/sigma |")
        md.append("|---|---|---|---|---|")
        for c in chains:
            v = d[d.chain == c].set_index("event").reindex(ref.index)
            both = ref.onset_found.astype(bool) & v.onset_found.astype(bool)
            flt = both & ref.label.isin(TRIP_CLASSES)          # benign 'onsets' are often noise crossings at a random time
            dt_on = np.abs(v.t_onset[flt] - ref.t_onset[flt]) * 1e6
            rel = (v[feats][both] - ref[feats][both]).abs() / sig
            moved = (rel > 0.1).mean()
            worst = rel.median().idxmax()
            ws = int((v.window_short > 0.5).sum())
            md.append(f"| {c} | {v.onset_found.mean()*100:.1f} % (ref {ref.onset_found.mean()*100:.1f} %){f' [{ws} late, window incomplete]' if ws else ''} | {np.nanmedian(dt_on):.1f} / {np.nanpercentile(dt_on, 95):.1f} | {moved.median()*100:.0f} % | {worst}: {rel[worst].median():.2f} / {rel[worst].quantile(0.95):.2f} |")
        md.append("\nPer-feature median |d|/sigma_ref (rows: chains):\n")
        md.append("| chain | " + " | ".join(feats) + " |"); md.append("|---|" + "---|" * len(feats))
        for c in chains:
            v = d[d.chain == c].set_index("event").reindex(ref.index)
            both = ref.onset_found.astype(bool) & v.onset_found.astype(bool)
            rel = ((v[feats][both] - ref[feats][both]).abs() / sig).median()
            md.append(f"| {c} | " + " | ".join(f"{rel[f]:.2f}" for f in feats) + " |")

    if a.save_tables:
        for node in ("feeder", "rack"):
            for c in df.chain.unique():
                df[(df.node == node) & (df.chain == c)].to_csv(os.path.join(a.out, f"features_{node}_{c}.csv"), index=False)
        md.append(f"\n--save-tables: features_<node>_<chain>.csv written to {a.out} ({len(df.chain.unique())} chains x 2 nodes)")

    # ---- 3: decisions with a model trained on the given table
    if a.train_table or a.train_chain:
        from dcsim.studies import _fit
        from sklearn.model_selection import StratifiedKFold
        trained_on = (f"the {a.train_chain} chain's own features of the scored events (5-fold CV, out-of-fold)" if a.train_chain
                      else a.train_table)
        md.append("\n## Decisions with the model trained on " + trained_on + f" (W = {a.W} ms, cols = studies.ALL)\n")
        md.append("All events are scored, including those whose onset appears or disappears in a chain (no onset = no decision = no trip).\n")
        md.append("| node | chain | identical decisions | new trips: benign (false trips) / arc / fault | lost trips: fault (misses) / arc / benign | onsets new / lost | mean |dP(TRIP)| | agreement with labels | vs labels: false trips (benign->TRIP) / misses (fault->HOLD) |")
        md.append("|---|---|---|---|---|---|---|---|---|")
        dec_rows, brk, notes = [], [], []
        dec_csv = os.path.join(a.out, f"hil_frontend_decisions_W{a.W:g}" + (f"_retrained_{a.train_chain}" if a.train_chain else "") + ".csv")
        if a.from_csv and not a.train_chain:
            saved = pd.read_csv(dec_csv, dtype={"event": str}, float_precision="round_trip")
            notes.append(f"--from-csv: decisions taken from {dec_csv} (the model of that run; --holdout as it was then)")
        for node in ("feeder", "rack"):
            cv_pred = None
            if a.train_chain:
                src = df[(df.node == node) & (df.chain == a.train_chain)].set_index("event")
                ok = ((src.onset_found > 0.5) & (src.window_short < 0.5)).values; labels = src.label.values; y = src.decision.values
                cv_pred = {}
                skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=a.seed)
                for tr_, te_ in skf.split(np.zeros(len(src)), labels):
                    tr_ok = tr_[ok[tr_]]
                    clf = _fit(src[ALL].values[tr_ok], y[tr_ok]); i_trip = list(clf.classes_).index("TRIP")
                    for c in df.chain.unique():
                        sub = df[(df.node == node) & (df.chain == c)].set_index("event").reindex(src.index)
                        if c not in cv_pred:
                            cv_pred[c] = (pd.Series("HOLD", index=src.index, dtype=object), pd.Series(0.0, index=src.index))
                        m = ((sub.onset_found > 0.5) & (sub.window_short < 0.5)).values; rows_ = te_[m[te_]]
                        if rows_.size:
                            X = sub[ALL].values[rows_]
                            cv_pred[c][0].iloc[rows_] = clf.predict(X); cv_pred[c][1].iloc[rows_] = clf.predict_proba(X)[:, i_trip]
                if node == "feeder":
                    notes.append(f"--train-chain {a.train_chain}: model fitted on that chain's features of the scored events "
                                 f"({ok.sum()} with onset of {len(src)}), 5 stratified folds, every chain scored out-of-fold; the train table is not used. "
                                 f"Read it as: the {a.train_chain} row's 'agreement with labels' is the retrained relay's out-of-fold accuracy on its own "
                                 f"front end (compare with the ref row of the --train-table run); 'identical decisions' are now relative to the 2 MSa/s "
                                 f"stream scored by the retrained model, so the rows to read are {a.train_chain} and its neighbours, not ref.")
            elif not a.from_csv:
                tab = pd.read_csv(os.path.join(a.train_table, f"features_{node}.csv"), float_precision="round_trip")
                tr = tab[(tab.W_ms == a.W) & (tab.onset_found > 0.5)] if "onset_found" in tab else tab[tab.W_ms == a.W]
                if a.holdout:
                    scored = set(df.event.astype(str)); n_before = len(tr)
                    tr = tr[~tr.event.astype(str).str.zfill(5).isin(scored) & ~tr.event.astype(str).isin(scored)]
                    notes.append(f"{node}: --holdout, training rows {n_before} -> {len(tr)} (scored events removed)")
                if len(tr) < 100:
                    msg = (f"{node}: only {len(tr)} training rows left after --holdout -- the scored set covers the table. "
                           f"Decisions skipped; use --train-chain ref / --train-chain hil_<dt> (5-fold CV over the scored set) instead.")
                    print(msg, flush=True); notes.append(msg); continue
                clf = _fit(tr[ALL].values, tr["decision"].values)
                i_trip = list(clf.classes_).index("TRIP")
            d = df[df.node == node]

            def decide(sub, _chain=None):
                """Every event gets a decision: no onset -> no window -> no trip (HOLD), P(TRIP) = 0."""
                sub = sub.set_index("event")
                m = (sub.onset_found > 0.5) & (sub.window_short < 0.5)
                if cv_pred is not None:
                    dec_, pt_ = cv_pred[_chain]
                    return dec_.reindex(sub.index), pt_.reindex(sub.index).astype(float), sub.decision, m
                if a.from_csv:
                    sv = saved[(saved.node == node) & (saved.chain == _chain)].set_index("event").reindex(sub.index)
                    return sv.decision, sv.p_trip.astype(float), sub.decision, m
                dec = pd.Series("HOLD", index=sub.index, dtype=object)
                pt = pd.Series(0.0, index=sub.index)
                if m.any():
                    X = sub.loc[m, ALL].values
                    dec[m] = clf.predict(X)
                    pt[m] = clf.predict_proba(X)[:, i_trip]
                return dec, pt, sub.decision, m

            p_ref, pt_ref, lab, on_ref = decide(d[d.chain == "ref"], "ref")
            lbl = d[d.chain == "ref"].set_index("event").label.reindex(p_ref.index)
            dec_rows.append(pd.DataFrame(dict(event=p_ref.index, label=lbl.values, node=node, chain="ref",
                                              onset_found=on_ref.values, decision=p_ref.values, p_trip=pt_ref.values)))
            is_ben, is_fault, is_arc = lbl.isin(BENIGN), lbl.isin(TRIP_CLASSES), (lbl == "series_arc")
            def vs_labels(p_):
                return f"{int(((p_ == 'TRIP') & is_ben).sum())} / {int(((p_ == 'HOLD') & is_fault).sum())} of {int(is_ben.sum())} / {int(is_fault.sum())}"
            md.append(f"| {node} | ref | — | — | — | — | — | {(p_ref == lab).mean()*100:.1f} % | {vs_labels(p_ref)} |")
            for c in chains:
                p, pt, _, on_c = decide(d[d.chain == c], c)
                p, pt = p.reindex(p_ref.index), pt.reindex(p_ref.index)
                on_c = on_c.reindex(p_ref.index).fillna(False).astype(bool)
                same = (p == p_ref).mean()
                new_trip = (p_ref != "TRIP") & (p == "TRIP"); lost_trip = (p_ref == "TRIP") & (p != "TRIP")
                ft_b, ft_a, ft_f = int((new_trip & is_ben).sum()), int((new_trip & is_arc).sum()), int((new_trip & is_fault).sum())
                ms_f, ms_a, ms_b = int((lost_trip & is_fault).sum()), int((lost_trip & is_arc).sum()), int((lost_trip & is_ben).sum())
                new_on = int((~on_ref & on_c).sum()); lost_on = int((on_ref & ~on_c).sum())
                md.append(f"| {node} | {c} | {same*100:.1f} % | {ft_b} / {ft_a} / {ft_f} | {ms_f} / {ms_a} / {ms_b} | {new_on} / {lost_on} | {np.abs(pt - pt_ref).mean():.3f} | {(p == lab).mean()*100:.1f} % | {vs_labels(p)} |")
                dec_rows.append(pd.DataFrame(dict(event=p.index, label=lbl.values, node=node, chain=c,
                                                  onset_found=on_c.values, decision=p.values, p_trip=pt.values)))
                def q(mask):
                    x = pt_ref[mask]; return f"{x.median():.2f} / {x.quantile(0.1):.2f}" if mask.any() else "—"
                brk.append(dict(node=node, chain=c,
                                lost_by_label=", ".join(f"{l} {n}" for l, n in lbl[lost_trip & is_fault].value_counts().items()) or "—",
                                new_by_label=", ".join(f"{l} {n}" for l, n in lbl[new_trip & is_ben].value_counts().items()) or "—",
                                p_lost=q(lost_trip & is_fault), p_new=q(new_trip & is_ben),
                                bias_f=(pt - pt_ref)[is_fault & on_ref & on_c].mean(), bias_b=(pt - pt_ref)[is_ben & on_ref & on_c].mean()))

    if a.train_table:
        if not a.from_csv or a.train_chain:
            pd.concat(dec_rows).to_csv(dec_csv, index=False)
        for n_ in notes: md.append("\n" + n_)
        md.append("\n### Flip breakdown (which events, how close to the boundary, which way the chain pushes)\n")
        md.append("| node | chain | lost fault trips by label | P(TRIP)_ref of lost: median / p10 | new benign trips by label | P(TRIP)_ref of new: median / p10 | signed mean dP(TRIP): fault / benign |")
        md.append("|---|---|---|---|---|---|---|")
        for b in brk:
            md.append(f"| {b['node']} | {b['chain']} | {b['lost_by_label']} | {b['p_lost']} | {b['new_by_label']} | {b['p_new']} | {b['bias_f']:+.3f} / {b['bias_b']:+.3f} |")
        md.append("\nP(TRIP)_ref near the default threshold (0.5) = boundary events a tiny shift flips; well above = the chain moved them. "
                  "Signed dP(TRIP) < 0 on faults = systematic push toward HOLD (a front-end bias, not noise); about 0 with flips both ways = boundary noise / in-sample memorisation (compare with --holdout).")

    md.append("\nReading: |d|/sigma is the feature shift in units of its spread over the event set — 0.1 is invisible to a 15-leaf tree, "
              "1 is a different event. node_ideal isolates the node front end (full scale, clipping, 100 kHz, 500 kSa/s); hil_<dt> adds the ZOH staircase and the DAC; "
              "dac_replay is the 12-bit bench-control fallback. Decisions are the transfer number, split by label class as studies._metrics splits it: new trips on BENIGN events are false trips the HIL would show that the simulation did not "
              "(series_arc is the ALERT class and is counted separately, never as benign); lost trips on TRIP_CLASSES events are misses it would add. Every event is scored with the relay's own rule (no onset = HOLD), so an onset the ZOH staircase creates on a quiet benign record counts.")
    txt = "\n".join(md)
    open(os.path.join(a.out, f"hil_frontend_summary_W{a.W:g}" + (f"_retrained_{a.train_chain}" if a.train_chain else "") + ".md"),
         "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
