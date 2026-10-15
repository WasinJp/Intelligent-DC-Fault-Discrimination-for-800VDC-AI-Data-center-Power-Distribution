"""plot_hil_onset_cases.py -- look at the events where the HIL chain moves the onset the most (check (k) diagnostic).

Reads <out>/hil_frontend_features_W<W>.csv, picks the events with the largest |t_onset(chain) - t_onset(ref)| per node
(and a few with the smallest, for contrast), rebuilds the chains from the h5 exactly as run_hil_frontend_study.py does,
and plots i and v around the onset for ref / node_ideal / <chain>, with each chain's onset marked and the detector's
threshold band drawn. Prints a table: event, label, node, t_onset per chain, pre-window sigma_i / sigma_v and the
resulting thresholds per chain (max(5 sigma, 0.004 fs)) -- the number that says whether the hold moves the onset by
delaying the front or by changing the threshold.

Usage (repo root, .venv):
  python scripts/plot_hil_onset_cases.py "data/events_v1xl6k_s*.h5" --out data/hil_frontend_full --chain hil_1us --n 12
Writes <out>/onset_cases_<chain>.png and onset_cases_<chain>.csv.
"""
import sys, os, argparse
import numpy as np, pandas as pd
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from dcsim import features as F
from dcsim.dataset import iter_events, load_obs
from run_hil_frontend_study import chains_for, onset_of


def thresholds(o):
    fs = float(o["fs_fast"]); n_pre = max(int(0.15e-3 * fs), 4); n5 = max(int(5e-6 * fs), 1)
    fi, fv = o["fast_i"].astype(np.float64), o["fast_v"].astype(np.float64)
    si, sv = F._movavg(fi, n5), F._movavg(fv, n5)
    sig_i, sig_v = si[:n_pre].std() + 1e-9, sv[:n_pre].std() + 1e-9
    return dict(i_pre=fi[:n_pre].mean(), v_pre=fv[:n_pre].mean(), sig_i=sig_i, sig_v=sig_v,
                thr_i=max(5 * sig_i, 0.004 * o["fs_i"]), thr_v=max(5 * sig_v, 0.004 * o["fs_v"]),
                thr_i_is_sigma=5 * sig_i > 0.004 * o["fs_i"], thr_v_is_sigma=5 * sig_v > 0.004 * o["fs_v"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("h5"); ap.add_argument("--out", default="data/hil_frontend_full"); ap.add_argument("--W", type=float, default=0.25)
    ap.add_argument("--chain", default="hil_1us"); ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--node-noise", type=float, default=0.0); ap.add_argument("--phase", type=int, default=0); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    df = pd.read_csv(os.path.join(a.out, f"hil_frontend_features_W{a.W:g}.csv"), dtype={"event": str}, float_precision="round_trip")
    picks = []
    for node in ("feeder", "rack"):
        d = df[df.node == node]
        ref = d[d.chain == "ref"].set_index("event"); v = d[d.chain == a.chain].set_index("event").reindex(ref.index)
        both = (ref.onset_found > 0.5) & (v.onset_found > 0.5)
        dt = (v.t_onset - ref.t_onset).abs()[both] * 1e6
        top = dt.sort_values(ascending=False)
        for k in list(top.index[: a.n // 2]) + list(top.index[-2:]):
            picks.append((k, node, float(top[k]), ref.label[k]))
    want = {k for k, *_ in picks}
    dt_s = float(a.chain[4:-2]) * 1e-6 if a.chain.startswith("hil_") else 1e-6
    rows, panels = [], {}
    rng = np.random.default_rng(a.seed)
    for k, e in iter_events(a.h5):
        if k not in want:
            continue
        pr = e["params"].attrs
        for node in ("feeder", "rack"):
            if not any(p[0] == k and p[1] == node for p in picks):
                continue
            obs = load_obs(e, None, node=node)
            I_n, V_n = (pr["I_out_rated"], pr["V_ref48"]) if node == "rack" else (pr["I_rated"], pr["V_ref"])
            ch = chains_for(obs, I_n, V_n, node, [dt_s], rng, a.node_noise, a.phase)
            sel = {c: ch[c] for c in ("ref", "node_ideal", a.chain)}
            panels[(k, node)] = (sel, I_n, V_n, e.attrs["label"])
            for c, o in sel.items():
                t_on, found = onset_of(o); th = thresholds(o)
                rows.append(dict(event=k, node=node, label=e.attrs["label"], chain=c, t_onset_us=t_on * 1e6 if found else np.nan,
                                 **{kk: (float(vv) if not isinstance(vv, (bool, np.bool_)) else bool(vv)) for kk, vv in th.items()}))
    tab = pd.DataFrame(rows)
    tab.to_csv(os.path.join(a.out, f"onset_cases_{a.chain}.csv"), index=False)
    piv = tab.pivot_table(index=["event", "node", "label"], columns="chain", values=["t_onset_us", "thr_i", "sig_i"])
    print(piv.to_string())
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    n = len(panels); fig, axes = plt.subplots(n, 2, figsize=(14, 2.6 * n), squeeze=False)
    for r, ((k, node), (sel, I_n, V_n, label)) in enumerate(panels.items()):
        t_ref, _ = onset_of(sel["ref"])
        for j, (sig, base) in enumerate((("fast_i", I_n), ("fast_v", V_n))):
            ax = axes[r, j]
            for c, o in sel.items():
                t = (o["fast_t"] - t_ref) * 1e6; y = o[sig] / base
                m = (t > -150) & (t < 250)
                ax.plot(t[m], y[m], lw=0.8, label=c, drawstyle="steps-post" if c != "ref" else "default")
                t_on, found = onset_of(o)
                if found:
                    ax.axvline((t_on - t_ref) * 1e6, ls="--", lw=0.8, color=ax.lines[-1].get_color())
            th = thresholds(sel["ref"]); pre = th["i_pre"] if j == 0 else th["v_pre"]; thr = th["thr_i"] if j == 0 else th["thr_v"]
            ax.axhspan((pre - thr) / base, (pre + thr) / base, color="grey", alpha=0.15)
            ax.set_title(f"{k} {node} {label} -- {sig} (p.u.), onset lines per chain, grey = ref threshold band", fontsize=8)
            ax.set_xlabel("us from ref onset"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(a.out, f"onset_cases_{a.chain}.png"), dpi=110)
    print("wrote", os.path.join(a.out, f"onset_cases_{a.chain}.png"))


if __name__ == "__main__":
    main()
