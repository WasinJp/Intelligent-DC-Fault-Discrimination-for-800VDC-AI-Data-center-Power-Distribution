# TIMING.md — inference budget and latency (FIRMWARE_SPEC.md §7.4)

Generated 2026-10-01 23:54 by `tools/make_timing_md.py` from `docs/timing_study/*.json` (`tools/budget_study.py`) and `docs/timing_study/bench_variants.log` (`fx_cli bench`).

## 1. Decision table: trees vs accuracy vs inference time

Classifier of `studies._fit` (learning rate 0.06, 15 leaves, l2 0.5, random_state 0) on `data/nodes_v1xl6k` (36 000 events: 30 000 benign, 6 000 faults; rows of the 0.25 ms decision window with `onset_found > 0.5`; features unchanged). **auto** = `_fit` as the studies run it: `max_iter 300` with sklearn `early_stopping='auto'`, which is ON above 10 000 rows and stopped at the iteration counts shown (DEVIATIONS.md #9). **100 / 150 / 300** = exactly that many iterations (`early_stopping=False`). Scoring: `studies.operating_points(nested=True)`, 5-fold × 10 seeds, P(TRIP) threshold chosen inside each outer fold on inner-CV probabilities of the training part at the 0.1 % false-trip budget, applied to the held-out fold (held-out calibration, `run_operating_study.py` §3). Rates in %, mean ± std over seeds. Host inference = `fx_model_raw` + softmax per decision on the x86 development machine (3 240 fixture rows × 50, idle machine; p99 includes OS scheduling noise); the Cortex-M7 column is filled by the M3 procedure (`timing` command, DWT).

### feeder + rack (30 features, the two-node relay of the node study)

| setting | trees / iteration | nodes | bytes | host inference mean / p99 (µs) | M7 infer mean / p99 (µs) | false trips | missed 800 V | high-Z missed | missed 48 V | threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| auto | 87 (63–151) | 8874 | 105 kB | 7.4 / 12.5 | _M3_ | 0.098 ± 0.009 | 0.823 ± 0.094 | 2.470 ± 0.283 | 0.500 ± 0.050 | 0.215 |
| 100 | 100 (100–100) | 8700 | 103 kB | 7.0 / 12.3 | _M3_ | 0.099 ± 0.008 | 0.703 ± 0.074 | 2.110 ± 0.221 | 0.400 ± 0.071 | 0.188 |
| 150 | 150 (150–150) | 13050 | 155 kB | 11.8 / 18.7 | _M3_ | 0.096 ± 0.008 | 0.640 ± 0.087 | 1.920 ± 0.260 | 0.340 ± 0.070 | 0.139 |
| 300 | 300 (300–300) | 26100 | 309 kB | 27.1 / 39.7 | _M3_ | 0.095 ± 0.007 | 0.583 ± 0.065 | 1.750 ± 0.196 | 0.305 ± 0.076 | 0.089 |

### feeder only (15 features)

| setting | trees / iteration | nodes | bytes | host inference mean / p99 (µs) | M7 infer mean / p99 (µs) | false trips | missed 800 V | high-Z missed | missed 48 V | threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| auto | 76 (50–195) | 6264 | 74 kB | 4.1 / 7.9 | _M3_ | 0.103 ± 0.007 | 5.810 ± 0.186 | 16.740 ± 0.535 | 69.825 ± 0.675 | 0.883 |
| 100 | 100 (100–100) | 8700 | 103 kB | 5.9 / 10.8 | _M3_ | 0.102 ± 0.010 | 5.753 ± 0.178 | 16.580 ± 0.508 | 69.610 ± 0.648 | 0.885 |
| 150 | 150 (150–150) | 13050 | 155 kB | 9.1 / 15.9 | _M3_ | 0.096 ± 0.013 | 5.800 ± 0.163 | 16.740 ± 0.445 | 70.090 ± 0.740 | 0.895 |
| 300 | 300 (300–300) | 26100 | 309 kB | 19.3 / 29.2 | _M3_ | 0.094 ± 0.008 | 5.793 ± 0.153 | 16.730 ± 0.490 | 70.930 ± 0.600 | 0.919 |

### rack only (15 features)

| setting | trees / iteration | nodes | bytes | host inference mean / p99 (µs) | M7 infer mean / p99 (µs) | false trips | missed 800 V | high-Z missed | missed 48 V | threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| auto | 83 (52–143) | 7134 | 85 kB | 5.2 / 9.5 | _M3_ | 0.098 ± 0.014 | 35.777 ± 0.399 | 73.550 ± 0.731 | 0.305 ± 0.072 | 0.569 |
| 100 | 100 (100–100) | 8700 | 103 kB | 6.5 / 11.0 | _M3_ | 0.098 ± 0.014 | 35.630 ± 0.329 | 73.530 ± 0.583 | 0.345 ± 0.082 | 0.561 |
| 150 | 150 (150–150) | 13050 | 155 kB | 10.5 / 16.1 | _M3_ | 0.100 ± 0.014 | 35.770 ± 0.433 | 73.570 ± 0.610 | 0.370 ± 0.087 | 0.572 |
| 300 | 300 (300–300) | 26100 | 309 kB | 23.2 / 32.8 | _M3_ | 0.096 ± 0.018 | 35.907 ± 0.418 | 73.610 ± 0.644 | 0.420 ± 0.068 | 0.600 |

## 2. Reading the table

- The budget of §7.4 is **≤ 80 µs from window close to trip pin (p99)** on the M7 at 480 MHz, of which inference is the largest unknown. Per decision the walk visits (trees × ~5 levels) nodes of 12 bytes from flash or RAM; the host numbers scale roughly linearly with the tree count (see the four rows).
- The `auto` row is what the committed `fx_model_data.h` contains (trained by `tools/train_model.py` with `_fit`). Fixed 100 trees are a strict improvement in accuracy over `auto` at a similar cost; 150 and 300 improve further at 1.5× and 3× the inference time. Decide after the M3 DWT numbers: if 300 trees fit under 80 µs p99 with the table in AXI SRAM, take 300; otherwise the largest count that fits. Features are not changed in any case.
- The nested threshold (last column) is the P(TRIP) that meets the 0.1 % false-trip budget on held-out data; it is the value for `settings set theta` when the relay is run at the budget instead of the default 0.5.

## 3. Measured latency (to be filled by M3 / M4)

| quantity | host (x86, reference) | NUCLEO-H743 @ 480 MHz (DWT) | spec §7.4 |
|---|---|---|---|
| detector + ring copy per 8-sample block | 17.5 ns/sample (`fx_cli stream`) | _M3_ | < 15 % of a core (< 2 300 cycles / block) |
| feature extraction (record mode, ≤ 2 600 samples incl. two double band-pass runs) | 100 µs mean (`fx_cli extract`, 2 600-sample records) | _M3_ | part of the 80 µs |
| inference | table above | _M3_ | part of the 80 µs |
| window close → trip pin | — | _M3_ | ≤ 80 µs p99 |
| onset → trip pin (scope, replayed faults) | — | _M4_ | 250 + 16 + 80 µs worst case |
| cadence relearn (background), double learner | 5.8 ms mean, 37.6 ms max (host) | — | — |
| cadence relearn, target learner (float32 history, CMSIS-DSP 4096-pt FFT, exact peak refinement) | 7.2 ms mean / 62 ms max; 23.0 M x86 cycles mean / 196 M max; 63.5 FFTs per relearn | _M5 target_ (projection: 70–150 ms mean, 0.4–1.2 s max at 480 MHz if the M7 needs 1.5–3× the x86 cycle count) | < 20 % CPU at one relearn per 200 ms = 40 ms: **not met by the projection**; set the relearn period to 1 s on the target or shorten the lag range (DEVIATIONS.md #14) |
