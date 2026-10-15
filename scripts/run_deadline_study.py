"""run_deadline_study.py -- how long after inception until something goes wrong, per fault class (Prof. Supachai, 15 Oct).

The relay's time is a design choice (0.25 ms of data after onset + <= 96 us) unless it is compared with the deadline the
physics sets. From the stored streams of a dataset, per fault event, measured from inception t_event:

  deadlines (first time each condition holds):
    D1  i_L   > k_f x I_rated        feeder current beyond what an SSCB is assumed to interrupt  (k_f tunable, default 2 and 3)
    D2  i_rack > k_r x I_out_rated   rack busbar current beyond the rack breaker's assumed limit (k_r tunable, default 2 and 3)
    D3  v_bus < V_uvlo               800 V bus below the rack converter's input UVLO (a fault starts taking healthy racks down)
    D4  v_out < V_uvlo48 for t_uvlo48  48 V bus below the POL UVLO for its delay (the GPUs drop; the training run is lost)
  our time:
    T_on   inception -> onset (features.detect_onset on the ref stream, per node; the earlier of the two)
    T_trip = T_on + W + 96 us (window + onset granularity + processing budget; FIRMWARE_SPEC 7.4) -- replace 96 us by the
           measured M3 number when it exists (--proc-us)
    T_brk  = T_trip + t_brk (SSCB opening, --t-brk, default 20 us; ask Delta)

Streams: fast (2 MSa/s, -0.2 to +5 ms around the anchor) for the first 5 ms, then the slow stream (5 kSa/s) to the end of
the record, so deadlines up to the record length (seconds) are found. A deadline that never occurs in the record is
reported as "> record" and counted separately.

Output: per class, median / p5 / p95 of every deadline and of T_on, T_trip, T_brk; the fraction of events where
T_brk < each deadline (margin met); one ECDF figure per class. Writes <out>/deadline_table.md, deadline_events.csv,
deadline_<class>.png.

Usage (repo root, .venv):
  python scripts/run_deadline_study.py "data/events_v1xl6k_s*.h5" --n-per-label 300 --out data/deadline
  python scripts/run_deadline_study.py "data/events_v1xl6k_s*.h5" --labels high_z,high_z_48 --n-per-label 1000 --out data/deadline_hz
"""
import sys, os, argparse, time
import numpy as np, pandas as pd
sys.path.insert(0, os.getcwd())
from dcsim import features as F
from dcsim.dataset import iter_events, load_obs
from dcsim.studies import TRIP_CLASSES

INF = np.inf


def first_time(t, cond, t0):
    """First t >= t0 where cond holds; inf if never."""
    m = cond & (t >= t0)
    i = np.flatnonzero(m)
    return float(t[i[0]] - t0) if i.size else INF


def first_time_held(t, cond, t0, hold):
    """First t >= t0 from which cond holds continuously for `hold` seconds; inf if never."""
    m = (cond & (t >= t0)).astype(np.int8)
    if not m.any():
        return INF
    dt = float(np.median(np.diff(t))) if t.size > 1 else INF
    n = max(int(round(hold / dt)), 1)
    c = np.convolve(m, np.ones(n, dtype=np.int8), mode="valid")
    i = np.flatnonzero(c >= n)
    return float(t[i[0]] - t0) if i.size else INF


def join(fast_t, fast_x, slow_t, slow_x):
    """Fast stream where it exists, slow stream after it (the slow stream covers the whole record)."""
    after = slow_t > fast_t[-1]
    return np.concatenate([fast_t, slow_t[after]]), np.concatenate([fast_x, slow_x[after]])


def onset_time(o):
    fs = float(o["fs_fast"]); n_pre = max(int(0.15e-3 * fs), 4); n5 = max(int(5e-6 * fs), 1)
    k_on, *_, found = F.detect_onset(o["fast_i"].astype(np.float64), o["fast_v"].astype(np.float64), n_pre, o["fs_i"], o["fs_v"], n_sm=n5)
    return float(o["fast_t"][k_on] - o["t_event"]) if found else INF


def q(x):
    x = np.asarray(x, float); fin = np.isfinite(x)
    if not fin.any():
        return "> record", "", "", 0
    v = x[fin]
    return f"{np.median(v)*1e3:.3f}", f"{np.percentile(v, 5)*1e3:.3f}", f"{np.percentile(v, 95)*1e3:.3f}", int(fin.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("h5"); ap.add_argument("--n-per-label", type=int, default=300)
    ap.add_argument("--labels", default=",".join(TRIP_CLASSES))
    ap.add_argument("--k", default="2,3", help="breaker current limits in x rated, comma list")
    ap.add_argument("--W", type=float, default=0.25, help="decision window, ms")
    ap.add_argument("--proc-us", type=float, default=96.0, help="onset granularity + processing budget after the window close (us); M3 measured value when known")
    ap.add_argument("--t-brk", type=float, default=20e-6, help="SSCB opening time after TRIP (s)")
    ap.add_argument("--out", default="data/deadline")
    a = ap.parse_args()
    labels = [l for l in a.labels.split(",") if l]; ks = [float(k) for k in a.k.split(",")]
    os.makedirs(a.out, exist_ok=True)
    rows = []; per = {}; t0_ = time.time()
    for key, e in iter_events(a.h5):
        label = e.attrs["label"]
        if label not in labels:
            continue
        per[label] = per.get(label, 0) + 1
        if per[label] > a.n_per_label:
            continue
        pr = e["params"].attrs; te = float(e.attrs["t_event"])
        fe = load_obs(e, None, node="feeder"); ra = load_obs(e, None, node="rack")
        t_i, i_L = join(fe["fast_t"], fe["fast_i"].astype(float), fe["slow_t"], fe["slow_i"].astype(float))
        t_v, v_bus = join(fe["fast_t"], fe["fast_v"].astype(float), fe["slow_t"], fe["slow_v"].astype(float))
        t_ri, i_rk = join(ra["fast_t"], ra["fast_i"].astype(float), ra["slow_t"], ra["slow_i"].astype(float))
        t_rv, v_out = join(ra["fast_t"], ra["fast_v"].astype(float), ra["slow_t"], ra["slow_v"].astype(float))
        V_uvlo = float(pr.get("V_uvlo", 0.8 * pr["V_ref"])); V_uvlo48 = float(pr.get("V_uvlo48", 0.8 * pr["V_ref48"])); t_uvlo48 = float(pr.get("t_uvlo48", 100e-6))
        r = dict(event=key, label=label, I_rated=float(pr["I_rated"]), I_out_rated=float(pr["I_out_rated"]),
                 R_f=float(pr.get("R_f", np.nan)), R_f48=float(pr.get("R_f48", np.nan)),
                 record_end=float(t_i[-1] - te))
        for k in ks:
            r[f"D1_iL_gt_{k:g}x"] = first_time(t_i, i_L > k * pr["I_rated"], te)
            r[f"D2_irack_gt_{k:g}x"] = first_time(t_ri, i_rk > k * pr["I_out_rated"], te)
        r["D3_vbus_lt_uvlo"] = first_time(t_v, v_bus < V_uvlo, te)
        r["D4_vout_lt_uvlo48_held"] = first_time_held(t_rv, v_out < V_uvlo48, te, t_uvlo48)
        t_on_f, t_on_r = onset_time(fe), onset_time(ra)
        r["T_on_feeder"], r["T_on_rack"] = t_on_f, t_on_r
        r["T_on"] = min(t_on_f, t_on_r)
        r["T_trip"] = r["T_on"] + a.W * 1e-3 + a.proc_us * 1e-6
        r["T_brk"] = r["T_trip"] + a.t_brk
        rows.append(r)
        if len(rows) % 100 == 0:
            print(f"  {len(rows)} events, {time.time()-t0_:.0f} s", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(a.out, "deadline_events.csv"), index=False)
    dl_cols = [c for c in df.columns if c.startswith("D")]
    md = [f"# Deadline study - {a.h5}, {len(df)} fault events, W = {a.W} ms, processing {a.proc_us:g} us, t_brk {a.t_brk*1e6:g} us\n",
          "Times in ms after inception. median / p5 / p95 over the events where the condition occurs within the record; n = how many of the class it occurs in. "
          "'margin met' = fraction of events (condition occurring) where T_brk < deadline.\n"]
    for label in labels:
        d = df[df.label == label]
        if d.empty:
            continue
        md.append(f"\n## {label} ({len(d)} events)\n")
        md.append("| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |"); md.append("|---|---|---|---|---|---|")
        for c in ["T_on", "T_trip", "T_brk"]:
            m, lo, hi, n = q(d[c]); md.append(f"| {c} | {m} | {lo} | {hi} | {n} | - |")
        for c in dl_cols:
            m, lo, hi, n = q(d[c])
            fin = np.isfinite(d[c]) & np.isfinite(d.T_brk)
            met = f"{(d.T_brk[fin] < d[c][fin]).mean()*100:.1f} %" if fin.any() else "-"
            md.append(f"| {c} | {m} | {lo} | {hi} | {n} | {met} |")
    md.append("\nReading: a deadline much longer than T_brk means 0.25 ms is a choice (earliest discriminating point at the budget, with margin), "
              "not a necessity; a deadline shorter than T_brk in a class means that class needs Layer 1 (per-sample threshold) - say which. "
              "'> record' = the condition never occurs within the stored record (seconds): no deadline from that mechanism for that class.")
    txt = "\n".join(md); open(os.path.join(a.out, "deadline_table.md"), "w", encoding="utf-8").write(txt); print(txt)
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        for label in labels:
            d = df[df.label == label]
            if d.empty:
                continue
            fig, ax = plt.subplots(figsize=(8, 4.5))
            for c in dl_cols + ["T_brk"]:
                x = np.sort(d[c][np.isfinite(d[c])].values) * 1e3
                if x.size:
                    ax.step(x, np.arange(1, x.size + 1) / len(d), where="post", label=f"{c} (n={x.size})", lw=1.8 if c == "T_brk" else 1.0)
            ax.set_xscale("log"); ax.set_xlabel("ms after inception"); ax.set_ylabel("fraction of events"); ax.set_title(f"{label}: deadlines vs our time (ECDF)")
            ax.grid(True, which="both", alpha=0.3); ax.legend(fontsize=7)
            fig.tight_layout(); fig.savefig(os.path.join(a.out, f"deadline_{label}.png"), dpi=110); plt.close(fig)
    except Exception as ex:
        print("figure skipped:", ex)


if __name__ == "__main__":
    main()
