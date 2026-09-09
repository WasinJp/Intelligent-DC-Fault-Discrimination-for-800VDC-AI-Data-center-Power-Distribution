# v0.3.2 — OPEN-12 acquisition front-end study (sample rate × ADC bits)

Physics unchanged. Default streams byte-identical to v0.3.1 (verified: feature table on the v1 pilot differs by 0.0 across all 15 feature columns). Six files, drop-in.

## What it does

One physics pass per event; the fine window is synthesized at **16 front ends** from the same pristine output:
- rates {100 k, 250 k, 500 k, 1 M, 2 M} Sa/s × bits {12, 14, 16}, stored under `waveforms/alt/fs<rate>k_b<bits>/`
- plus the default stream (2 MSa/s, the event's drawn bits), unchanged
- anti-alias corner 0.4·f_s; sensor noise rms scaled by √(f_s / 2 MSa/s) — same sensor, narrower front end (the §7 rule)
- slow stream identical across configurations (verified)

The feature extractor is now rate-aware: every window is a time (5 µs / 10 µs smoothing, 150 µs pre-window, 50 µs early window, 60 µs filter settle) and the spectral band top follows the anti-alias corner (min(100 kHz, 0.4·f_s)).

## Files

| file | change |
|---|---|
| `dcsim/synth.py` | `synthesize(..., f_fast=2e6, bits=None)`; returns `fs_fast`, `adc_bits`; non-default configs draw independent fast noise and reproduce the default slow-stream draw |
| `dcsim/features.py` | rate-aware `extract` / `detect_onset`; diagnostics `fs_fast`, `adc_bits_used` |
| `dcsim/dataset.py` | `run_event(..., rate_configs)`, `generate(..., rate_configs)`, `load_obs(e, config)`, `_cfg_name` |
| `dcsim/studies.py` | `feature_table(..., config)`; `rate_study(h5, configs, ...)` → per-config 10-seed CV (+physics, +workload-aware), Gate-2 gray-zone fraction, 0.25 ms latency point; caches one feature CSV per config |
| `scripts/generate_dataset.py` | `--rates` flag; default output now `data/events_v1.h5` |
| `scripts/run_rate_study.py` | new; prints the summary table, writes `data/rates/rate_study.json` |

## Run

```
python scripts/generate_dataset.py data/events_v1_rates.h5 200 20260907 --rates
python scripts/run_rate_study.py data/events_v1_rates.h5
```

Cost (from the 42-event pilot, scaled): generation ≈ 1.5–2 s/event → 1 400 events ≈ 40 min, ≈ 0.4 MB/event → ≈ 0.6 GB. Feature extraction 16 × ≈ 4 min ≈ 1 h. Repeated CV ≈ 30 min. Plan ≈ 2.5 h total; it is restartable (feature CSVs are cached per config).

Note the rates dataset uses the same seed and workload as `events_v1.h5`, so its default-stream results must equal the v1 numbers exactly — that is the regression check for the run.

## How to read the table

For each front end: `+workload-aware` false trip / missed / high-Z at 1 ms (10 seeds), the Gate-2 gray-zone fraction (does bandwidth change how many high-Z faults hide inside the benign envelope?), and missed faults at 0.25 ms (does the fast decision survive a slower ADC?). The testbed front end is the cheapest configuration whose column is within one standard deviation of the 2 MSa/s / 16-bit column on all three metrics.
