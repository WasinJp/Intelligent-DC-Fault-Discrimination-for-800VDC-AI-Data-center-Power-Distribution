"""Regenerate every figure in /figures from the core and the v0.2 dataset.
Usage: python scripts/make_figures.py [events.h5]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dcsim.model import PARAMS_BASELINE, run_uniform
from dcsim.events import BENIGN, FAULTS
from dcsim.features import CONV, PHYS, ALL
from dcsim.studies import (threshold_study, classifier_study, operating_curve,
                           latency_study, TRIP_CLASSES)

h5 = sys.argv[1] if len(sys.argv) > 1 else "data/events_v0.2.h5"
csv = h5.replace(".h5", "_features.csv")
FIG = "figures"
os.makedirs(FIG, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
GREEN, BLUE, ORANGE, RED, GREY, PURPLE = "#1b9e77", "#1f77b4", "#e6550d", "#c0392b", "#7f7f7f", "#7570b3"
COL = {"benign_step": "#1b9e77", "benign_train": "#66c2a5", "benign_idle_drop": "#a6d854",
       "bolted_pp": "#c0392b", "resistive_pp": "#e6550d", "high_z": "#f2a63b", "series_arc": "#7570b3"}
NAME = {"benign_step": "benign step", "benign_train": "benign train (scheduled)",
        "benign_idle_drop": "benign idle drop", "bolted_pp": "bolted fault",
        "resistive_pp": "resistive fault", "high_z": "high-Z fault", "series_arc": "series arc"}


# ------------------------------------------------------------------ fig 0a/0b: single-pair waveforms
def fig_waveform_pairs():
    p = PARAMS_BASELINE
    dt, T = 1e-6, 20e-3
    n = int(T / dt)
    t = np.arange(n) * dt
    ramp = np.clip((t - 5e-3) / 2e-3, 0, 1)
    P = p["P_rated"] * (1 + 0.6 * ramp)
    tb, ob = run_uniform(p, dt, T, P_profile=P)
    tf_, of = run_uniform({**p, "R_f": 5e-3}, 5e-8, T, fault_start=5e-3, fault_end=7.5e-3)
    fig, ax = plt.subplots(2, 2, figsize=(12, 6), sharex=True)
    ax[0, 0].plot(tb * 1e3, ob[1], color=GREEN, label="line current $i_L$")
    ax[0, 0].plot(tb * 1e3, ob[4], "--", color=GREY, lw=1, label="load current")
    ax[0, 0].set_title("Benign workload step (+60% $P_{rated}$ in 2 ms)")
    ax[0, 0].legend(frameon=False); ax[0, 0].set_ylabel("current (A)")
    d = np.max(np.abs(np.diff(ob[1]))) / dt * 1e-6
    ax[0, 0].text(0.55, 0.5, f"max di/dt {d:.3f} A/µs\n(≈4 orders below fault)", transform=ax[0, 0].transAxes, color=GREEN)
    ax[0, 1].plot(tf_ * 1e3, of[1], color=GREEN, label="line current $i_L$")
    ax[0, 1].plot(tf_ * 1e3, of[3], color=ORANGE, label="fault current $i_f$")
    ax[0, 1].set_title("Bolted pole-to-pole fault ($R_f$ = 5 mΩ)")
    front = np.max(np.diff(of[3])) / 5e-8 * 1e-6
    ax[0, 1].text(0.3, 0.8, f"front {front:.0f} A/µs", transform=ax[0, 1].transAxes, color=ORANGE)
    ax[0, 1].legend(frameon=False)
    ax[1, 0].plot(tb * 1e3, ob[2], color=BLUE); ax[1, 0].set_ylabel("bus voltage (V)")
    ax[1, 0].axhline(p["V_uvlo"], ls=":", color=GREY); ax[1, 0].set_ylim(0, 850)
    ax[1, 0].text(0.4, 0.85, f"sag {ob[2][:5000].mean() - ob[2].min():.0f} V, converter holds", transform=ax[1, 0].transAxes, color=BLUE)
    ax[1, 0].text(0.05, 0.05, "UVLO threshold", transform=ax[1, 0].transAxes, color=GREY)
    ax[1, 1].plot(tf_ * 1e3, of[2], color=BLUE); ax[1, 1].axhline(p["V_uvlo"], ls=":", color=GREY); ax[1, 1].set_ylim(0, 850)
    ax[1, 1].text(0.35, 0.65, "collapse below UVLO\n(load sheds)", transform=ax[1, 1].transAxes, color=BLUE)
    for a in ax[1]: a.set_xlabel("time (ms)")
    fig.suptitle("Same bus, same sensors — two events a threshold breaker must tell apart")
    fig.tight_layout(); fig.savefig(f"{FIG}/benign_vs_fault.png", dpi=150); plt.close(fig)

    # high-Z pair: benign step vs 5 ohm fault, matched current
    th, oh = run_uniform({**p, "R_f": 5.0, "L_f": 2e-6}, 5e-8, T, fault_start=5e-3, fault_end=T)
    fig, ax = plt.subplots(2, 2, figsize=(12, 6), sharex=True)
    ax[0, 0].plot(tb * 1e3, ob[1], color=GREEN); ax[0, 0].set_title("Benign workload step (+60% $P_{rated}$, +152 A)")
    ax[0, 0].text(0.55, 0.45, "settles — converter\nfollows commanded ramp", transform=ax[0, 0].transAxes, color=GREEN)
    ax[0, 1].plot(th * 1e3, oh[1], color=GREEN); ax[0, 1].set_title("High-impedance fault ($R_f$ = 5 Ω, +~160 A)")
    ax[0, 1].text(0.55, 0.45, "also settles — fault fed\nthrough droop like a load", transform=ax[0, 1].transAxes, color=GREEN)
    ax[0, 0].set_ylabel("line current $i_L$ (A)")
    ax[1, 0].plot(tb * 1e3, ob[2], color=BLUE); ax[1, 1].plot(th * 1e3, oh[2], color=BLUE)
    ax[1, 0].set_ylabel("bus voltage (V)")
    for a in ax[1]: a.set_xlabel("time (ms)"); a.set_ylim(770, 810)
    for a in ax[0]: a.set_ylim(240, 420)
    fig.suptitle("The gray zone: on bus observables alone, a high-impedance fault is nearly indistinguishable from a legitimate load step")
    fig.tight_layout(); fig.savefig(f"{FIG}/grayzone_highz.png", dpi=150); plt.close(fig)


# ------------------------------------------------------------------ fig 1: gray-zone scatter (gate 2)
def fig_grayzone_scatter(df, ts):
    d = df[df.W_ms == 1.0]
    env = ts["envelope"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1.5, 1]})
    a = ax[0]
    for lab in BENIGN + TRIP_CLASSES:
        s = d[d.label == lab]
        a.scatter(s.di_max.clip(1e-3), s.didt_max.clip(1e-4), s=14, alpha=0.65, color=COL[lab],
                  marker="o" if lab in BENIGN else "^", label=NAME[lab], edgecolor="none")
    a.axvline(env["di_max"], color=GREY, ls="--", lw=1)
    a.axhline(env["didt_max"], color=GREY, ls="--", lw=1)
    a.fill_between([1e-3, env["di_max"]], 1e-4, env["didt_max"], color=GREY, alpha=0.08)
    a.set_xscale("log"); a.set_yscale("log")
    a.set_xlabel("current step magnitude  Δi / I_rated")
    a.set_ylabel("max di/dt  (A/µs) / I_rated")
    a.set_title("Every event a threshold breaker sees (600 benign, 600 fault)")
    a.text(2e-3, env["didt_max"] * 0.5, "benign envelope\n(zero false trips)", color=GREY, fontsize=9, va="top")
    gz = ts["gray_zone_fraction"]
    a.text(0.02, 0.97, f"inside envelope: bolted {gz['bolted_pp']*100:.0f}%, resistive {gz['resistive_pp']*100:.0f}%, "
           f"high-Z {gz['high_z']*100:.0f}%", transform=a.transAxes, va="top", fontsize=9)
    a.legend(frameon=False, fontsize=8, loc="lower right", ncol=2)
    b = ax[1]
    dets = ["magnitude", "di/dt", "v-collapse", "Layer 1 (mag OR di/dt OR v-collapse)"]
    short = ["magnitude", "di/dt", "v-collapse", "all three (OR)"]
    x = np.arange(len(dets)); w = 0.26
    for k, c in enumerate(TRIP_CLASSES):
        vals = [ts["miss_at_zero_ft"][dd][c] * 100 for dd in dets]
        b.bar(x + (k - 1) * w, vals, w, color=COL[c], label=NAME[c])
    b.set_xticks(x); b.set_xticklabels(short, fontsize=9)
    b.set_ylabel("faults missed at zero false trips (%)")
    b.set_title("Conventional detectors: what slips through")
    b.legend(frameon=False, fontsize=8); b.set_ylim(0, 100)
    fig.suptitle("Figure 1 — The gray zone is high-impedance faults: no threshold setting reaches <0.1% false trips and <1% missed",
                 fontsize=11)
    fig.tight_layout(); fig.savefig(f"{FIG}/fig1_grayzone_montecarlo.png", dpi=150); plt.close(fig)


# ------------------------------------------------------------------ fig 2: discriminator (gate 3)
def fig_discriminator(df, ts, oc, cs):
    d = df[df.W_ms == 1.0].reset_index(drop=True)
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.8))
    # (a) physics features: rise time vs early voltage lead
    a = ax[0]
    for lab in ("benign_step", "benign_train", "benign_idle_drop", "high_z"):
        s = d[d.label == lab]
        a.scatter(s.di_early.clip(3e-3), s.dv_early.clip(3e-4), s=14, alpha=0.65, color=COL[lab],
                  marker="o" if lab in BENIGN else "^", label=NAME[lab], edgecolor="none")
    a.set_xscale("log"); a.set_yscale("log")
    a.set_xlabel("current moved in first 50 µs  |Δi| / I_rated")
    a.set_ylabel("voltage dip in first 50 µs  Δv / V_ref")
    a.set_title("(a) first 50 µs: a fault has already moved, a ramp has not", fontsize=10)
    a.legend(frameon=False, fontsize=8)
    # (b) workload-aware: residual vs phase error on periodic backgrounds
    b = ax[1]
    s = d[(d.background == "train") & d.resid_period.notna()]
    for lab in BENIGN + TRIP_CLASSES:
        ss = s[s.label == lab]
        if len(ss) == 0:
            continue
        b.scatter(ss.phase_err.clip(1e-3), ss.resid_period.clip(1e-3), s=14, alpha=0.65, color=COL[lab],
                  marker="o" if lab in BENIGN else "^", label=NAME[lab], edgecolor="none")
    b.set_xscale("log"); b.set_yscale("log")
    b.set_xlabel("phase error vs. learned cadence  (fraction of period)")
    b.set_ylabel("residual vs. predicted step  |Δi − Δi_pred| / I_rated")
    b.set_title("(b) periodic backgrounds: scheduled steps land on time and on size", fontsize=10)
    b.legend(frameon=False, fontsize=8, loc="lower right")
    # (c) operating curve
    c = ax[2]
    c.plot(oc["false_trip"] * 100, oc["missed"] * 100, color=PURPLE, lw=2, label="classifier (all features), sweep P(trip)")
    l1 = ts["miss_at_zero_ft"]["Layer 1 (mag OR di/dt OR v-collapse)"]["all_trip"]
    c.scatter([0], [l1 * 100], color=RED, s=70, zorder=5, label="best conventional (Layer 1) at zero false trips")
    c.scatter([oc["false_trip"][np.argmin(np.abs(oc["missed"] - oc["miss_at_ft_target"]))] * 100],
              [oc["miss_at_ft_target"] * 100], color=PURPLE, s=70, zorder=5)
    cv = cs["+workload-aware"]["cv"]
    c.scatter([cv["false_trip"] * 100], [cv["missed"] * 100], color=PURPLE, marker="s", s=60, zorder=5,
              label="classifier default operating point")
    c.set_xlim(-0.3, 12); c.set_ylim(-1, 35)
    c.set_xlabel("false trips on benign transients (%)")
    c.set_ylabel("faults missed (%)")
    c.set_title("(c) operating curve: same sensors, same events", fontsize=10)
    c.annotate(f"{l1*100:.0f}% missed", (0.3, l1 * 100 + 1), color=RED, fontsize=9)
    c.annotate(f"{oc['miss_at_ft_target']*100:.0f}% missed at zero false trips\n"
               f"{cv['missed']*100:.1f}% missed at {cv['false_trip']*100:.0f}% false trips",
               (2.5, 8), color=PURPLE, fontsize=9)
    c.legend(frameon=False, fontsize=8, loc="upper right")
    fig.suptitle("Figure 2 — The discriminator: physics and workload-aware features separate what thresholds cannot (1 ms decision window, 5-fold CV)",
                 fontsize=11)
    fig.tight_layout(); fig.savefig(f"{FIG}/fig2_discriminator.png", dpi=150); plt.close(fig)


# ------------------------------------------------------------------ fig 3: sensing architecture evidence
def fig_sensing(df, cs, arcs):
    d = df[df.W_ms == 1.0].reset_index(drop=True)
    pred = cs["+workload-aware"]["cv_pred"]
    hz = d[d.label == "high_z"].copy()
    hz["if_pu"] = (800.0 / hz.R_f) / (hz.P_rated / 800.0)
    ph = pred[hz.index]
    bins = [0, 0.15, 0.3, 0.6, 1.0, 10]
    labels_ = ["<0.15", "0.15–0.3", "0.3–0.6", "0.6–1.0", ">1.0"]
    miss = []; ns = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = ((hz.if_pu >= lo) & (hz.if_pu < hi)).values
        miss.append((ph[m] == "HOLD").mean() * 100 if m.any() else np.nan); ns.append(int(m.sum()))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    a = ax[0]
    a.bar(labels_, miss, color=COL["high_z"])
    for i, (v, n) in enumerate(zip(miss, ns)):
        a.text(i, v + 1.5, f"n={n}", ha="center", fontsize=8, color=GREY)
    a.set_xlabel("high-Z fault current / segment rated current  (p.u.)")
    a.set_ylabel("high-Z faults missed (%)"); a.set_ylim(0, 60)
    a.set_title("(a) Detectability scales with fault current / segment rating", fontsize=10)
    a.text(0.98, 0.9, "same 10 Ω fault: 6% of a 1 MW segment,\n32% of a 200 kW segment",
           transform=a.transAxes, ha="right", fontsize=9, color=GREY)
    b = ax[1]
    names = list(arcs.keys())
    vals = [arcs[k]["detected"] * 100 for k in names]
    b.bar(["busbar joint arc\n(upstream of C_bus)", "load-path arc\n(downstream of C_bus)"], vals,
          color=[COL["series_arc"], "#bcbddc"])
    for i, v in enumerate(vals):
        b.text(i, v + 1.5, f"{v:.0f}%", ha="center", fontsize=9)
    b.set_ylabel("series arcs flagged ALERT (%)"); b.set_ylim(0, 110)
    b.set_title("(b) The bus capacitor hides load-side arcs from the feeder sensor", fontsize=10)
    fig.suptitle("Figure 3 — What feeder-level sensing can and cannot see: the case for a hybrid feeder + per-rack architecture", fontsize=11)
    fig.tight_layout(); fig.savefig(f"{FIG}/fig3_sensing_architecture.png", dpi=150); plt.close(fig)


# ------------------------------------------------------------------ fig 4: latency + ablation
def fig_latency_ablation(lat, cs):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    a = ax[0]
    Ws = sorted(lat.keys())
    a.plot(Ws, [lat[w]["false_trip"] * 100 for w in Ws], "o-", color=GREEN, label="false trips (benign)")
    a.plot(Ws, [lat[w]["missed"] * 100 for w in Ws], "^-", color=RED, label="faults missed (all)")
    a.plot(Ws, [lat[w]["missed_per_class"]["high_z"] * 100 for w in Ws], "^--", color=COL["high_z"], label="faults missed (high-Z)")
    a.set_xlabel("decision window after onset (ms)"); a.set_ylabel("%"); a.set_ylim(0, 20)
    a.set_title("(a) Decision latency: most of the separation is available by 0.5 ms")
    a.legend(frameon=False, fontsize=9)
    b = ax[1]
    names = list(cs.keys()); x = np.arange(len(names)); w = 0.2
    b.bar(x - 1.5 * w, [cs[n]["cv"]["false_trip"] * 100 for n in names], w, color=GREEN, label="false trips (5-fold CV)")
    b.bar(x - 0.5 * w, [cs[n]["cv"]["missed"] * 100 for n in names], w, color=RED, label="faults missed (5-fold CV)")
    b.bar(x + 0.5 * w, [cs[n]["domain_shift"]["false_trip"] * 100 for n in names], w, color="#a6dcc8", label="false trips, trained <400 kW → tested ≥400 kW")
    b.bar(x + 1.5 * w, [cs[n]["domain_shift"]["missed"] * 100 for n in names], w, color="#f4a582", label="missed, trained <400 kW → tested ≥400 kW")
    b.set_xticks(x); b.set_xticklabels(names); b.set_ylabel("%"); b.set_ylim(0, 22)
    b.set_title("(b) Feature ablation (1 ms window)")
    b.legend(frameon=False, fontsize=8)
    fig.suptitle("Figure 4 — Latency and ablation", fontsize=11)
    fig.tight_layout(); fig.savefig(f"{FIG}/fig4_latency_ablation.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    fig_waveform_pairs()
    print("waveform pairs done")
    df = pd.read_csv(csv)
    ts = threshold_study(df)
    cs = classifier_study(df)
    oc = operating_curve(df)
    lat = latency_study(df)
    from dcsim.studies import arc_placement_study
    arcs = arc_placement_study(df)
    fig_grayzone_scatter(df, ts); print("fig1 done")
    fig_discriminator(df, ts, oc, cs); print("fig2 done")
    fig_sensing(df, cs, arcs); print("fig3 done")
    fig_latency_ablation(lat, cs); print("fig4 done")
