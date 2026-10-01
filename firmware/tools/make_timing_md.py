"""make_timing_md.py — assemble docs/TIMING.md (the §7.4 decision table) from the budget-study JSONs
(tools/budget_study.py) and the host bench log (fx_cli bench per model variant).

  python firmware/tools/make_timing_md.py [--study firmware/docs/timing_study] [--out firmware/docs/TIMING.md]
         [--bench firmware/docs/timing_study/bench_variants.log]

The on-target columns (DWT) are left as placeholders until M3 runs; the host columns are x86 numbers."""
import argparse
import glob
import json
import os
import re
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SETTINGS = ["auto", "100", "150", "300"]
RELAYS = ["both", "feeder", "rack"]


def pct(d):
    return f"{d['mean'] * 100:.3f} ± {d['std'] * 100:.3f}"


def parse_bench(path):
    """-> {(setting, model): dict(trees, nodes, bytes, mean_us, p99_us)}"""
    out, setting = {}, None
    if not os.path.exists(path):
        return out
    for line in open(path):
        m = re.match(r"== it(\d+)", line)
        if m:
            setting = m.group(1); continue
        if line.startswith("== auto"):
            setting = "auto"; continue
        m = re.match(r"model\s+(\w+)\s+trees\s+(\d+)\s+nodes\s+(\d+)\s+bytes\s+(\d+).*mean\s+([\d.]+) us.*p99\s+([\d.]+) us.*max\s+([\d.]+) us", line)
        if m and setting:
            out[(setting, m.group(1))] = dict(trees=int(m.group(2)), nodes=int(m.group(3)), bytes=int(m.group(4)),
                                              mean_us=float(m.group(5)), p99_us=float(m.group(6)), max_us=float(m.group(7)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", default=os.path.join(ROOT, "firmware", "docs", "timing_study"))
    ap.add_argument("--bench", default=os.path.join(ROOT, "firmware", "docs", "timing_study", "bench_variants.log"))
    ap.add_argument("--out", default=os.path.join(ROOT, "firmware", "docs", "TIMING.md"))
    a = ap.parse_args()
    bench = parse_bench(a.bench)
    res = {}
    for p in glob.glob(os.path.join(a.study, "*_it*.json")):
        d = json.load(open(p))
        res[(d["relay"], str(d.get("setting", d["max_iter"])))] = d
    lines = []
    w = lines.append
    w("# TIMING.md — inference budget and latency (FIRMWARE_SPEC.md §7.4)\n")
    w(f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `tools/make_timing_md.py` from `docs/timing_study/*.json` "
      "(`tools/budget_study.py`) and `docs/timing_study/bench_variants.log` (`fx_cli bench`).\n")
    w("## 1. Decision table: trees vs accuracy vs inference time\n")
    w("Classifier of `studies._fit` (learning rate 0.06, 15 leaves, l2 0.5, random_state 0) on `data/nodes_v1xl6k` "
      "(36 000 events: 30 000 benign, 6 000 faults; rows of the 0.25 ms decision window with `onset_found > 0.5`; "
      "features unchanged). **auto** = `_fit` as the studies run it: `max_iter 300` with sklearn `early_stopping='auto'`, "
      "which is ON above 10 000 rows and stopped at the iteration counts shown (DEVIATIONS.md #9). **100 / 150 / 300** = "
      "exactly that many iterations (`early_stopping=False`). Scoring: `studies.operating_points(nested=True)`, 5-fold × "
      "10 seeds, P(TRIP) threshold chosen inside each outer fold on inner-CV probabilities of the training part at the "
      "0.1 % false-trip budget, applied to the held-out fold (held-out calibration, `run_operating_study.py` §3). "
      "Rates in %, mean ± std over seeds. Host inference = `fx_model_raw` + softmax per decision on the x86 development "
      "machine (3 240 fixture rows × 50, idle machine; p99 includes OS scheduling noise); "
      "the Cortex-M7 column is filled by the M3 procedure (`timing` command, DWT).\n")
    for relay in RELAYS:
        title = {"both": "feeder + rack (30 features, the two-node relay of the node study)",
                 "feeder": "feeder only (15 features)", "rack": "rack only (15 features)"}[relay]
        w(f"### {title}\n")
        w("| setting | trees / iteration | nodes | bytes | host inference mean / p99 (µs) | M7 infer mean / p99 (µs) | false trips | missed 800 V | high-Z missed | missed 48 V | threshold |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for s in SETTINGS:
            d = res.get((relay, s))
            b = bench.get((s, relay))
            if not d and not b:
                continue
            it = f"{d['n_iter_mean']:.0f} ({d['n_iter_min']}–{d['n_iter_max']})" if d else "—"
            nodes = f"{b['nodes']}" if b else "—"
            byt = f"{b['bytes'] / 1024:.0f} kB" if b else "—"
            host = f"{b['mean_us']:.1f} / {b['p99_us']:.1f}" if b else "—"
            if d:
                w(f"| {s} | {it} | {nodes} | {byt} | {host} | _M3_ | {pct(d['false_trip'])} | {pct(d['missed_800'])} | "
                  f"{pct(d['high_z_missed'])} | {pct(d['missed_48'])} | {d['threshold']['mean']:.3f} |")
            else:
                w(f"| {s} | {b['trees'] // 3} | {nodes} | {byt} | {host} | _M3_ | _pending_ | _pending_ | _pending_ | _pending_ | — |")
        w("")
    done = sorted(k for k in res)
    missing = [(r, s) for r in RELAYS for s in SETTINGS if (r, s) not in res]
    if missing:
        w(f"_Study runs still pending: {missing}_\n")
    w("## 2. Reading the table\n")
    w("- The budget of §7.4 is **≤ 80 µs from window close to trip pin (p99)** on the M7 at 480 MHz, of which inference is "
      "the largest unknown. Per decision the walk visits (trees × ~5 levels) nodes of 12 bytes from flash or RAM; the host "
      "numbers scale roughly linearly with the tree count (see the four rows).")
    w("- The `auto` row is what the committed `fx_model_data.h` contains (trained by `tools/train_model.py` with `_fit`). "
      "Fixed 100 trees are a strict improvement in accuracy over `auto` at a similar cost; 150 and 300 improve further at "
      "1.5× and 3× the inference time. Decide after the M3 DWT numbers: if 300 trees fit under 80 µs p99 with the table "
      "in AXI SRAM, take 300; otherwise the largest count that fits. Features are not changed in any case.")
    w("- The nested threshold (last column) is the P(TRIP) that meets the 0.1 % false-trip budget on held-out data; it is "
      "the value for `settings set theta` when the relay is run at the budget instead of the default 0.5.\n")
    w("## 3. Measured latency (to be filled by M3 / M4)\n")
    w("| quantity | host (x86, reference) | NUCLEO-H743 @ 480 MHz (DWT) | spec §7.4 |")
    w("|---|---|---|---|")
    w("| detector + ring copy per 8-sample block | 17.5 ns/sample (`fx_cli stream`) | _M3_ | < 15 % of a core (< 2 300 cycles / block) |")
    w("| feature extraction (record mode, ≤ 2 600 samples incl. two double band-pass runs) | 100 µs mean (`fx_cli extract`, 2 600-sample records) | _M3_ | part of the 80 µs |")
    w("| inference | table above | _M3_ | part of the 80 µs |")
    w("| window close → trip pin | — | _M3_ | ≤ 80 µs p99 |")
    w("| onset → trip pin (scope, replayed faults) | — | _M4_ | 250 + 16 + 80 µs worst case |")
    w("| cadence relearn (background), double learner | 5.8 ms mean, 37.6 ms max (host) | — | — |")
    w("| cadence relearn, target learner (float32 history, CMSIS-DSP 4096-pt FFT, exact peak refinement) | "
      "7.2 ms mean / 62 ms max; 23.0 M x86 cycles mean / 196 M max; 63.5 FFTs per relearn | _M5 target_ (projection: 70–150 ms mean, "
      "0.4–1.2 s max at 480 MHz if the M7 needs 1.5–3× the x86 cycle count) | < 20 % CPU at one relearn per 200 ms = 40 ms: "
      "**not met by the projection**; set the relearn period to 1 s on the target or shorten the lag range (DEVIATIONS.md #14) |")
    with open(a.out, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", a.out, f"({len(done)} study results, {len(bench)} bench rows)")


if __name__ == "__main__":
    main()
