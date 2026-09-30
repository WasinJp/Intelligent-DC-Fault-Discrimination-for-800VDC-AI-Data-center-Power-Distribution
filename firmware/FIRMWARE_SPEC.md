# FIRMWARE_SPEC.md — sensing-node and bench-control firmware

**Written:** 2026-10-01. Owner of the spec: Wasin (design sessions). Implementer: Claude Code, working in this repository under `firmware/`. Reviewer: Prof. Supachai (firmware design), then bench tests.
**Read first, in this order:** this file; `dcsim/features.py` (the feature contract, not to be reinterpreted); `dcsim/synth.py` (`_aa_decimate`, the slow-stream definition); `dcsim/studies.py` (`_fit`, `DECISION`, `ALL`); `hardware/SCALING_SHEET.md` and `hardware/SCHEMATIC_DESIGN.md` (what the node is wired to).

## 0. Purpose and the claim under test

The judges of the Delta Cup final doubt one thing: that the relay decides within 0.25 ms of fault onset on a real processor with real sensors. This firmware exists to measure that. The claim it must support, in the words we will use: *"On an STM32H7 at 480 MHz, sampling two channels at 500 kSa/s, the relay's decision window closes 250 µs after onset and the trip pin rises X µs later, measured on a scope in N fault events."* X and N come from this firmware; the target is X ≤ 80 µs (§7).

Two firmware images:
- **node**: runs on each sensing node (feeder and rack, same image, role by a jumper or a stored setting).
- **bench_control**: workload profile, fault triggers, UVLO emulation, SYNC, DAC replay, run scripting (§10). Simpler and separate; may be written second.

## 1. Working rules for the implementer

1. **The feature definitions in `dcsim/features.py` are the contract.** Port them; do not improve them. Any deviation (a different smoothing length, a different filter, a reordered operation) is a spec change and is raised in the PR description, not made silently. The acceptance test for every feature is agreement with the Python value on the same record (§6).
2. **Every milestone has an executable acceptance test** that runs on the host (`firmware/host/`) without hardware wherever the spec says so. A milestone is done when its test passes and the numbers are pasted in `firmware/docs/MILESTONES.md`.
3. **No dynamic allocation, no RTOS, no floating-point formatting on the critical path.** C11, `-Wall -Wextra -Werror`, one shared platform-independent core (`firmware/common/`) compiled both for the host (gcc, tests) and for the target (arm-none-eabi-gcc, `-O2 -mfpu=fpv5-d16 -mfloat-abi=hard`). Float32 on the Cortex-M7 FPU is allowed and expected; "fixed point" is not required.
4. **Determinism.** The same record must give the same features and the same decision on host and target, bit-for-bit for integer paths and within the tolerances of §6 for float paths. Test this.
5. Report timing with the DWT cycle counter, never with estimates.
6. Keep `firmware/docs/DEVIATIONS.md`: every place the target implementation differs from the Python reference (e.g. the stream-mode onset detector of §4.2), why, and what test bounds the difference.

## 2. Repository layout

```
firmware/
  FIRMWARE_SPEC.md              this file
  common/                        platform-independent C (used by host and target)
    fx_config.h                  compile-time constants (§3)
    fx_filters.[ch]              SOS IIR (causal), moving average, decimator
    fx_onset.[ch]                onset detector: record mode and stream mode (§4)
    fx_features.[ch]             CONV + PHYS features (§4)
    fx_cadence.[ch]              slow-stream cadence learner, WORK features (§5)
    fx_model.[ch]                gradient-boosted tree inference; model tables in fx_model_data.h (§6)
    fx_relay.[ch]                Layer-1 thresholds, Layer-2 decision, combined-decision logic (§7)
    fx_record.[ch]               ring buffer, event record layout (§8)
  host/                          gcc build; CLI and tests
    fx_cli.c                     extract features / predict on record files
    tests/                       ctest targets for every milestone
  tools/                         Python (uses the repo's .venv)
    make_fixtures.py             h5 events -> 500 kSa/s record files + Python reference features (§6.1)
    export_filters.py            scipy SOS coefficients -> fx_filters_data.h
    export_model.py              trained HistGradientBoostingClassifier -> fx_model_data.h (§6.3)
    compare.py                   C output vs Python reference, tolerance report
    replay_waveforms.py          records -> bench_control DAC tables
  node/                          STM32H7 target: main, adc_dma, timing, trip, can, usb_record, settings
  bench_control/                 STM32H7 target: profile, fault one-shot triggers, uvlo, sync, dac_replay, cli
  docs/                          MILESTONES.md, DEVIATIONS.md, TIMING.md
```

Target boards: NUCLEO-H743ZI2 (fallback NUCLEO-H723ZG; same code, different clock tree). HAL/LL and CMSIS-DSP are allowed on the target; `common/` must not include them.

## 3. Numeric contract (fx_config.h)

| constant | value | origin |
|---|---|---|
| `FS_FAST` | 500 000 Sa/s | product design; OPEN-12: rate not limiting |
| `FS_SLOW` | 5 000 Sa/s | `features.F_SLOW`; decimation 100:1 |
| `N_PRE` | 75 samples (150 µs) | `max(int(0.15e-3*fs), 4)` |
| `N_SM5` | 2 samples | `max(int(5e-6*fs), 1)` — onset detector and early windows |
| `N_SM10` | 5 samples | `max(int(10e-6*fs), 1)` — decision window smoothing |
| `N_50US` | 25 samples | early window |
| `N_W` (decision window) | 125 samples (0.25 ms) | `max(int(W*fs), 4)`; also support 250 and 500 for tests |
| `N_TAIL` | `max(int(0.1*N_W), min(10, N_W))` = 12 at N_W = 125 | tail mean |
| `N_SKIP` | `min(int(60e-6*fs), N_PRE-3)` = 30 | spectral pre-window start |
| `K_HALF` | `int(0.3*N_W)` = 37 | spectral post-window start |
| band-pass | Butterworth order 4, 1 kHz – 100 kHz at fs = 500 kSa/s, 4 SOS sections, **causal, zero initial state** | `features.extract` |
| slow-stream anti-alias | Butterworth order 4 low-pass at 2 kHz (0.4 × 5 kHz) at fs = 500 kSa/s, then keep every 100th sample; **initial state = first sample** | `synth._aa_decimate` |
| onset thresholds | `thr = max(5·σ_pre, 0.004·fs_scale)` per channel | `features.detect_onset`; `fs_i`, `fs_v` are the per-unit full scales of the record (I_rated, V_ref) |
| record | 0.2 ms before onset to 5 ms after (100 + 2 500 samples), 2 channels, uint16 ADC codes + calibration | dataset fast-stream layout |
| ADC | 16-bit, dual simultaneous, timer-triggered at 500 kSa/s, DMA circular | SCHEMATIC_DESIGN §2 |

Per-unit scaling on the node: `i_pu = (code − offset_i) · gain_i / I_rated`, `v_pu = (code − offset_v) · gain_v / V_ref`, with the four calibration constants stored in settings and applied in float32 before any feature. Features are computed in per-unit exactly as Python does (Python divides by `I_rated`, `V_ref`; the node's I_rated / V_ref are the bench values from SCALING_SHEET, 10 A / 12 V rack, 2.5 A / 48 V feeder).

## 4. Onset detection and CONV/PHYS features

### 4.1 Record mode (host and target, exact port of Python)
Input: a record of `n` samples per channel starting at record start; `N_PRE` samples define the pre-window (`i_pre`, `v_pre` = means; `σ` = std of the 5 µs-smoothed pre-window). Onset = first sample after `N_PRE` where the smoothed |Δi| or |Δv| exceeds its threshold. Then the features of `features.extract` on `[k_on, k_on + N_W)` with 10 µs smoothing, the early window `[k_on − N_50US, k_on + N_50US)` with 5 µs smoothing, and the band-pass run from record start with zero state. Port line by line; keep the Python names as C identifiers.

### 4.2 Stream mode (target only; the deviation to document)
The node does not know when a record starts. It keeps a ring buffer and runs the detector continuously: for candidate sample `k`, the pre-window is the 150 µs ending 50 µs before `k` (`[k − 100, k − 25)`), recomputed incrementally (running sums for mean and variance). When the detector fires at `k_on`, the record is defined as `[k_on − 100, k_on + 2 500)` and **all features are then computed in record mode on that record**, so the feature path is identical to Python; only the onset index can differ. Acceptance (§6.2): on replayed records the stream-mode onset index equals the record-mode index within ±2 samples in ≥ 99 % of events, and the resulting decisions are identical in ≥ 99.5 %.

Hold-off: after a decision, the detector is inhibited for 5 ms (the record length), then re-armed when the 150 µs window is quiet again.

### 4.3 What is computed on the critical path
At `k_on + N_W` (the window close): CONV, PHYS, the band-pass post-window statistic, `phase_err` from the *already learned* cadence (§5), then inference (§6), then the Layer-2 decision, then the trip pin. Everything else (record upload, CAN telemetry, cadence relearning) is off the critical path.

## 5. Cadence learner and WORK features (fx_cadence)

Background task, not on the critical path. Input: the slow stream (5 kSa/s, both channels, produced on the node by the anti-alias decimator of §3 from the fast stream) over a history of up to `H = 7.6 s` (38 000 samples per channel, float32 = 304 kB; the H743 has 1 MB SRAM, place the history in AXI SRAM or SRAM1). Port `features._learn_cadence` and its helpers (`_cadence_candidates`, `_edges_two_level`, `_history_edges`, `_tier2_from_segments`) for the current-channel history. FFT-based autocorrelation (CMSIS-DSP on the target, any FFT on the host) is allowed for `_cadence_candidates` provided the returned lags and strengths match Python's within the §6 tolerance. Relearn every 200 ms; publish `tiers` (T, edges, strength, phase_start, off2, edges_current) atomically for the critical path.

`phase_err` at decision time is computed exactly as in `features.extract` from the published tiers and `t_on`. `has_period`, `period_strength` come from the published tiers. If no tiers are published, `has_period = 0`, `period_strength = 0`, `phase_err = NaN` — the model was trained with these values and handles them (missing-value branches, §6.3).

**Priority note:** M5 (this section) comes after the latency milestone. Until it is done the node runs with `has_period = 0` and `phase_err = NaN`, which is a valid operating mode of the trained model (the "flat background" case). The latency claim does not depend on it.

## 6. Model and acceptance tests

### 6.1 Fixtures (tools/make_fixtures.py)
From a dataset h5 (a glob of shards is fine; use `dcsim.dataset.iter_events`), produce for ≥ 1 000 events (all nine labels, both nodes): a 500 kSa/s record obtained from the stored 2 MSa/s fast stream by `synth._aa_decimate(x, 2e6, 4)` (this is how the OPEN-12 rate study made its 500 kSa/s streams — reuse the same call), the slow streams as stored, the calibration constants, and the Python reference features from `features.extract` at W = 0.25, 0.5, 1.0 ms with `fs_fast = 500e3`. Write one binary record file per event plus a CSV of reference features. Fixture generation is Python; it runs on Wasin's machine (the h5 files are there) and the fixtures are committed under `firmware/host/tests/fixtures/` (keep ≤ 50 MB; sample events if needed).

### 6.2 Feature agreement (M1 acceptance)
`fx_cli extract` on every fixture record; `compare.py` against the CSV. Pass criteria per feature, over all events: onset index identical; `di_end, di_max, didt_max, t_rise, dv_early, di_early, v_sag_end, v_min, r_dyn, collapse` within 1e-6 relative (or 1e-9 absolute where the value is ~0); `spec_i, spec_v` within 1e-4 absolute (float32 IIR vs float64); `has_period, period_strength, phase_err` (M5) within 1e-6 / 1e-4 / 1e-6, NaN matching NaN. Report the worst case per feature.

### 6.3 Model export (M2)
The classifier is `sklearn.ensemble.HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=0.5)` on the feature columns `studies.ALL` (15 features, in that order) with targets `HOLD / TRIP / ALERT` (`studies.DECISION`). The rack node and the feeder node each run their own model; the combined "feeder + rack" relay of the node study is a third model on 30 features exchanged over CAN (§7.3). `export_model.py` walks `clf._predictors[iteration][class].nodes` (fields `feature_idx, num_threshold, missing_go_to_left, left, right, value, is_leaf`) and emits flat arrays; inference sums leaf values per class, adds `clf._baseline_prediction`, applies softmax (or argmax; the decision uses the class scores, and `P(TRIP)` is needed for the operating-point threshold). NaN in a feature follows `missing_go_to_left`. Acceptance: on the whole fixture feature table, class scores within 1e-5 absolute of `clf.decision_function` (or predict_proba within 1e-5) and identical argmax. Also record the model size (nodes, bytes) and the host inference time.

The training script that produces the model file is `tools/train_model.py` (Python): trains on a named feature-table CSV (`data/nodes*/features_<node>.csv` or the bench dataset's), fixes `random_state=0`, and writes `fx_model_data.h` plus a JSON with the training-set hash. The bench relay is trained on the bench dataset (SCALING_SHEET §5); the data-center relay on v1-large. Both are exported with the same tool.

### 6.4 Target parity (M3)
The same fixtures replayed to the target over UART (or preloaded into flash): the node runs record mode and returns features + scores; they must match the host to 1e-6 (integer-identical for the onset index). This proves the target build is the same code, before any analog signal is involved.

## 7. The relay (fx_relay) and the timing claim

### 7.1 Layer 1 (per sample, before any window)
Configurable thresholds on the 5 µs-smoothed stream: `|Δi| > L1_DI`, `v < L1_V`. Defaults **off** (thresholds at ±inf); the bench dataset's Gate-2 max-of-benign envelope at bench scale supplies values when wanted. A Layer-1 trip sets the trip pin immediately and marks the record "L1".

### 7.2 Layer 2
At window close: features → model → `P(TRIP)`; trip if `P(TRIP) > θ`, with θ from settings (default 0.5; the operating-point value from `run_operating_study` for a 0.1 % budget is the alternative). ALERT sets an alert pin/LED, never the trip pin.

### 7.3 Combined decision (M6)
Each node sends its `P(TRIP)`, `has_period`, `phase_err` and onset time over CAN-FD within 20 µs of its window close (one 16-byte frame). The rack node's TRIP is local and immediate (it protects the 48 V bus). The feeder's decision may use the two-node model (30 features) when the rack frame has arrived within 50 µs of its own window close, else its own 15-feature model; log which path was used. The alibi exchange is the `phase_err` field.

### 7.4 Timing instrumentation (the deliverable for the judges)
GPIO `ONSET` rises at `k_on` detection, `TRIP` at the trip decision. DWT cycle counts are logged for: detector cost per DMA block; feature extraction; band-pass; inference; total from window close to trip pin. `docs/TIMING.md` reports mean / p99 / max over ≥ 1 000 replayed events. **Targets:** DMA block = 8 samples (16 µs) so onset granularity ≤ 16 µs; window close to trip ≤ 80 µs (p99); therefore onset-to-trip ≤ 250 + 16 + 80 = 346 µs worst case, stated as "250 µs window + ≤ 80 µs processing". If inference is the bottleneck, reduce `max_iter` in training and report the accuracy cost; do not change the features.

## 8. Records, settings, commands (node)

- Ring buffer: 2 channels × 8 192 samples uint16 (16 ms). On decision (or on SYNC, or on the host command `capture`), the record `[k_on − 100, k_on + 2 500)` per channel plus a header (node id, role, fs, calibration, `k_on`, decision, `P(TRIP)`, all 15 features, DWT timings, SYNC timestamp) is queued and sent over USB CDC (the H7's own USB) as a framed binary blob; `tools/` includes a decoder that writes the same layout `make_fixtures.py` reads, so bench records feed the same compare pipeline.
- Settings (flash, CLI over the ST-Link VCP UART): role, I_rated, V_ref, ADC gain/offset per channel, θ, L1 thresholds, model id, CAN id. `settings show`, `settings set k v`, `settings save`.
- Commands: `capture`, `arm`, `status` (last decision, timings, cadence tiers), `selftest` (runs the fixture parity check on the target), `replay <id>` (host-pushed record through the record-mode path).

## 9. ADC and sampling (node)

TIM-triggered ADC1+ADC2 dual simultaneous, 16-bit, 500 kSa/s, DMA circular into the ring buffer, half/complete callbacks every 8 samples per channel (a small block is deliberate: it bounds onset granularity; verify the interrupt load stays < 15 % of one core). The 3.3 V clamp and the 150 kHz anti-alias are hardware (SCHEMATIC_DESIGN §2). Calibration procedure (`tools/calibrate.md`): two-point gain/offset per channel against a meter; stored in settings.

## 10. Bench control firmware (second image, keep it simple)

- `profile`: a table-driven workload generator: two-tier cadence (T1 0.3–3 s, duty, T2 bursts), steps of 10–80 % of rating as staircase ramps over 0.5–20 ms across the five load gates; idle drops. Deterministic from a seed so runs are reproducible.
- `fault`: `fault rack <r_sel> <l_sel>` / `fault feeder <r_sel>` set the selector relays/jumpers (or just tell the operator), then pulse the one-shot trigger at a scheduled time relative to the profile (scheduled or unscheduled, chosen by the script).
- `uvlo`: ADC at 1 MSa/s on v_out; if below 9.6 V for 100 µs, all load gates off; re-enable above 10.1 V.
- `sync`: a pulse on the SYNC output at each scheduled event time; both nodes and the scope receive it.
- `replay <table>`: DAC1/DAC2 at 1 MSa/s from flash tables generated by `replay_waveforms.py` (records → 12-bit DAC codes matching the node's front-end full scale), triggered by `sync`.
- CLI over USB-serial; a Python runner in `tools/bench_run.py` scripts the §6 test plan of SCALING_SHEET (200 benign, 80 faults), records everything, and never bypasses the hardware arm switch.

## 11. Milestones and order

| M | deliverable | needs hardware | acceptance |
|---|---|---|---|
| M1 | `common/` feature extractor (record mode) + host CLI + fixtures | no | §6.2 feature agreement on ≥ 1 000 events |
| M2 | model export + inference | no | §6.3 score agreement; size and host time reported |
| M3 | node target: ADC/DMA, stream-mode detector, record-mode features, inference, trip pin, DWT timing, UART parity | Nucleo + a signal generator or a resistor divider for ADC sanity | §6.4 parity; §4.2 stream/record agreement on replayed records; first TIMING.md |
| M4 | bench_control DAC replay + latency measurement | 2 Nucleo, scope | scope traces: onset-to-trip over ≥ 100 replayed faults; TIMING.md final |
| M5 | cadence learner + WORK features | no (host), then target | §6.2 on WORK features; background CPU load < 20 % |
| M6 | CAN link, combined decision, record upload, settings/CLI complete | 2 Nucleo | two-node decision on replayed pairs matches the host two-node model |
| M7 | bench_control profile / fault / uvlo / sync + `bench_run.py` | bench | the SCALING_SHEET §6 plan runs end to end |

M1–M2 start now (parts in transit). M3–M4 are what the judges asked for and come before M5. M7 lands with the bench assembly.

## 12. Out of scope for November

Isolation, the external 14-bit SAR ADC, EtherCAT, Layer 3 (hold-and-monitor), OTA, and anything that is product rather than prototype. They are listed in the product-design slide, not in this firmware.
