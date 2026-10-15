# simscape/ — `dcsim_rt`: the fixed-step, explicit, HIL-ready form of MODEL.md v0.4.4

**Added 2026-10-10.** A second independent implementation of the core, next to the Simscape cross-check model, in the
shape a real-time target runs: one discrete MATLAB Function block, explicit RK4 of the 11 states, fixed-step discrete solver,
no Simscape, no continuous states, no algebraic loops. Plus the breaker element (MODEL.md 0.4.5 proposal) and the HIL I/O
(four 0–10 V analog outputs, two TRIP inputs, SYNC). Validated by the unchanged check (i) comparator.
Nothing here modifies `dcsim/`, the generator, or `dcsim_shelf.slx`.

| file | what |
|---|---|
| `dcsim_rt_derivs.m` | right-hand side — line-for-line port of `dcsim.model_v04._derivs` |
| `dcsim_rt_step.m` | one step — the loop body of `model_v04.simulate` in the same operation order (quasi-static rule, UVLO machines, record, RK4, clamps) + the breaker element + the `uvlo_tol` option |
| `dcsim_rt_pv.m`, `dcsim_rt_init.m`, `dcsim_rt_profile.m` | parameter vector (36, PARAM_KEYS order), exact initial state, GPU profile of a check-(i) case |
| `run_rt_case.m` | run one case at a step `dt`, pure-MATLAB loop (`'loop'`) or through the Simulink wrapper (`'slx'`); writes `data/simscape/rt/dt_<x>us/sim_<case>.mat`; scores it with `scripts/compare_simscape.py` |
| `rt_sweep.m` | all eight cases over `dt ∈ {1 2 5 10 20} µs` → one table, `rt_sweep.csv`, `rt_sweep_log.txt` |
| `build_dcsim_rt.m` | builds `dcsim_rt.slx` (the file the HIL company converts) |
| `dcsim_rt_demo.m` | closed-loop desktop demo: scripted TRIP at +0.35 ms opens the model's breaker; figure `rt_demo_<case>.png` |
| `rt_port_check.py` | MATLAB-free validation: the two MATLAB files transliterated to Python vs the real core — **bit-identical** at 1 µs and 10 µs on all eight cases (run 2026-10-10) — and the sweep below |

## How to run (MATLAB R2026a, repo root on the path or `cd simscape`)
```
>> run_rt_case('step')                 % 1 us, pure MATLAB, scored:  expect PASS, worst excluded ~1e-13
>> rt_sweep                            % eight cases x five steps, ~1 min (uvlo_tol 0 = core-identical)
>> rt_sweep([], [], 'loop', 0.5)       % grid-robust UVLO timers — the HIL setting
>> build_dcsim_rt; run_rt_case('bolted_48', 1e-6, 'slx')   % the Simulink wrapper, same numbers as 'loop'
>> dcsim_rt_demo                       % closed loop: bolted_48, rack TRIP at +0.35 ms
```
The reference data (`data/simscape/ref_*.mat`, `params.json`, `cases.json`) is created by `ensure_cases` (via `load_case`) if missing.

## Expected result (pre-registered; `rt_port_check.py` 2026-10-10, confirmed by Wasin's MATLAB run the same day)

Worst discontinuity-excluded RMS over i_L, v_bus, i_rack, v_out (p.u.), P/F by the check-(i) criterion (RMS ≤ 1e-2 on all channels, every reference edge matched within 5 µs and 20 %). `dt` as exact literals (`rt_sweep` default), `uvlo_tol = 0` (timers exactly as the Python core):

| case | 1 µs | 2 µs | 5 µs | 10 µs | 20 µs |
|---|---|---|---|---|---|
| step | 2.6e-14 P | 6.0e-05 P | 2.4e-04 P | 5.4e-04 P | 1.1e-03 P |
| step_sm | 2.3e-14 P | 6.6e-05 P | 2.7e-04 P | 5.8e-04 P | 1.1e-03 P |
| high_z | 7.2e-14 P | 9.5e-04 P | 9.8e-04 P | 2.9e-03 P | 6.4e-03 P |
| high_z_sm | 7.2e-14 P | 9.5e-04 P | 9.8e-04 P | 2.9e-03 P | 6.4e-03 P |
| high_z_48 | 1.0e-13 P | 2.7e-05 P | 1.7e-04 P | 6.8e-04 P | 5.6e-02 **F** |
| high_z_48_sm | 1.0e-13 P | 3.5e-05 P | 1.7e-04 P | 6.8e-04 P | 5.6e-02 **F** |
| bolted_48 | 5.9e-13 P | 1.5e-04 P | 5.9e-04 P | 4.1e-03 P | 1.2e-02 **F** |
| bolted_48_sm | 5.8e-13 P | 5.8e-05 P | 1.3e-04 P | 9.6e-04 **F**† | 6.4e-03 **F**† |

† RMS passes; the POL-UVLO edge lands 6 µs from the reference against the 5 µs tolerance — the grid, not the physics.
At 20 µs the 48 V fault fronts (τ_f ≈ 25 µs) fall under the quasi-static rule and i_rack misses by 5.6 %.

**MATLAB run of 2026-10-10 (Wasin):** 1 µs loop PASS at 2.60e-14; `dcsim_rt.slx` at 1 µs PASS at 5.86e-13 with the UVLO edge at +0.00 µs — the wrapper is the loop. His first sweep showed 8.1e-3 / 2.1e-2 / 3.4e-2 (bolted_48) and 8.0e-3 / 1.2e-2 / 2.9e-2 (bolted_48_sm) at 5 / 10 / 20 µs: that sweep built `dt` as `5*1e-6`, which is one ulp *below* `5e-6`; the Python transliteration with those exact values reproduces his numbers to the digit. Cause: the core's UVLO timer accumulates `dt` and trips at `>= t_uvlo`, so a sum one ulp short trips one step late (105 / 110 / 120 µs instead of 100 µs). The frozen core itself trips at 101 µs at dt = 1 µs and 102 µs at 2 µs for the same reason.

**Consequence and the `uvlo_tol` option.** The UVLO edge in MODEL.md 0.4.4 is grid-dependent by up to one step; invisible inside check (i)'s 5 µs tolerance at 1 µs, visible at ≥ 5 µs, and a real-time box with its own float `dt` will show the same ±1-step wobble. `dcsim_rt_step` therefore takes `uvlo_tol`: `0` = exactly the Python core (use for validation — bit-identical); `0.5` = half-step tolerance, i.e. step counting, independent of the float value of `dt` (use on the HIL). With `uvlo_tol = 0.5` the only cells that change are bolted_48 / bolted_48_sm at 1 µs (1.2e-04 / 1.2e-04, edge at exactly 100 µs) and bolted_48_sm at 2 µs (1.9e-04); every P/F is the same. Proposed for MODEL.md 0.4.5: define `t_uvlo` / `t_uvlo48` as `round(t_uvlo / dt)` steps (`rt_sweep([], [], 'loop', 0.5)` shows the result); it moves the 1 µs references by ≤ 1 µs, inside the check-(i) tolerance, and is a decision for Wasin, not made here.

**Reading for the HIL:** solver step ≤ 5 µs — all eight cases pass with margin; 10 µs — physics within 0.5 %, comparator edges quantised to the step; 20 µs — not acceptable for the 48 V fault classes. The node-side half of check (k) (ZOH + DAC + the real filter into the 500 kSa/s node, scored on the relay's features) is the separate sweep in Python.

## Breaker element (MODEL.md 0.4.5 proposal — text to add to §4 after Wasin's OK)
> **4.12 Breaker element (SSCB).** Two ideal breakers, each commanded by its node's TRIP: `brk_f` in the feeder (open → i_L held at zero; the bus discharges into whatever is on it), `brk_r` in the rack busbar between the storage bank and the load-side busbar (open → i_pol = 0 and i_f48 = 0; the downstream node reads 0). An optional opening delay t_brk after TRIP. Both closed is the published core; no Layer-1/2 observable changes (both are closed throughout the decision window). The model records inception → opening time on its own clock. Implemented in `simscape/dcsim_rt_step.m`; the Python core gains the same two flags when the bench dataset needs the post-trip record.

## HIL I/O of `dcsim_rt.slx`
Inports 1 `TRIP_feeder`, 2 `TRIP_rack` (0/1). Outports 1–4 `AO1..AO4` = i_L, v_bus, i_rack, v_out scaled to 0–10 V (10 V = 2.64 / 1.45 / 16.5 / 1.45 p.u.), 5 `SYNC` (one-step pulse at fault inception), 6 `BRK_F`, 7 `BRK_R`. Base-workspace parameters: `pv` (36), `cfg = [dt qs_dt_min brk_delay uvlo_tol]`, `y0`, `P_gpu_ts`, `t_event`, `f800_on`, `f48_on`, `T_record` — for the HIL build the fault schedule and workload generator replace the From Workspace / Step sources (next step after the meeting).

## Check (k) — node side: does the relay survive the HIL output chain? (2026-10-13 → 15, 36 000 events)

**Question.** The step sweep above says the *physics* transfers at ≤ 5 µs. Check (k) asks whether the *relay* does: the node computes its 15 features from the box's analog outputs — a zero-order-hold staircase at the box's step, a DAC, the panel, the node's own 100 kHz / 500 kSa/s / 16-bit front end — not from the 2 MSa/s stream it was trained on. Scripts: `scripts/run_hil_frontend_study.py` (chains, features, decisions; `--save-tables` writes per-chain feature tables), `scripts/run_hil_operating_points.py` (two-node relay at the 0.1 % false-trip budget per chain, and the transfer matrix), `scripts/plot_hil_onset_cases.py` (per-event diagnostic). Tables: `data/hil_frontend_aa/` (local, gitignored).

**Chains** (applied to the stored 2 MSa/s streams of `v1xl6k`, both nodes, W = 0.25 ms): `ref` = the training domain; `node_ideal` = clip at the node full scale (rack 16.5 × I_rated, feeder 2.64 ×; 1.45 × V) → 4th-order 100 kHz Butterworth → 500 kSa/s → 16-bit; `hil_<dt>` = anti-alias at 0.4/dt → hold at dt → 16-bit DAC over 0–10 V → node front end; `dac_replay` = 1 µs hold, 12-bit (the bench-control fallback). Node and box noise 0 (the box's AO noise floor is an open question to the company; `--box-noise` / `--node-noise` take it when measured).

**Recorded deviation (2026-10-14).** The first chain held the *raw stored stream*. The stored stream is pristine physics plus white sensor noise (0.05–0.5 % of full scale, flat to 1 MHz, `synth.py`); a hold concentrates white noise at low frequency, so the chain pushed ≈ k× more noise power into the node's 100 kHz band for a k-sample hold — something the real box, which outputs smooth model states, never does. It showed as a +4–6 % benign false-trip rate at 2–5 µs, hundreds of "new onsets" on quiet records, and `spec_i`/`spec_v` shifts of 0.2–0.4 σ; the per-event diagnostic (`onset_cases_hil_1us`) found the pre-window σ rising 1.2–1.5× under a 1 µs hold on the same event, which gave it away. The corrected chain anti-aliases at the box's own Nyquist before the hold ("the box computes the physics at step dt"); `--no-hil-aa` reproduces the old numbers. Every number below is from the corrected chain; the 13/14 Oct tables are superseded and kept only in the session log.

**Features and onsets (36 000 events).** `node_ideal`: worst median shift 0.12–0.14 σ (`didt_max`), nothing else above 0.05 σ. Hold at 1–5 µs adds ≤ 0.02 σ on every feature except `spec_i`/`spec_v` at 5 µs (0.10–0.14 σ); 10 µs 0.2–0.3 σ; 20 µs 0.35–0.47 σ. Onset shift on fault events, median: 4 / 5 / 7 / 11 / 19 / 35 µs for node / 1 / 2 / 5 / 10 / 20 µs — the hold's delay plus the filter's. Onset-found rate unchanged in every chain (feeder 99.8 %, rack 96.2 %); one late onset (incomplete window) in 36 000 at 5 µs. Clipping at the node full scale: 0.0 % of events inside the decision window, 0.1 % anywhere in the record (the 13 Oct brief's "about a quarter of bolted_48" was wrong).

**Decisions — two-node relay at the 0.1 % false-trip budget, retrained per front end (held-out threshold calibration, 5 folds × 3 seeds, `run_hil_operating_points.py --nested`):**

| trained and scored on | false trips % | missed % (all TRIP) | missed 800 V % | high-Z missed % | missed 48 V % | θ |
|---|---|---|---|---|---|---|
| clean 2 MSa/s stream (published P5, in-sample) | 0.100 | 0.42 | 0.53 | 1.6 | 0.25 | 0.070 |
| node front end | 0.097 ± 0.005 | 0.48 ± 0.04 | 0.61 ± 0.07 | 1.83 ± 0.21 | 0.28 ± 0.02 | 0.066 |
| HIL 2 µs | 0.113 ± 0.011 | 0.54 ± 0.03 | 0.72 ± 0.06 | 2.17 ± 0.19 | 0.27 ± 0.02 | 0.073 |
| **HIL 5 µs** | **0.100 ± 0.003** | **0.57 ± 0.08** | **0.73 ± 0.10** | **2.20 ± 0.29** | **0.32 ± 0.06** | **0.067** |
| HIL 10 µs | 0.093 ± 0.007 | 0.59 ± 0.10 | 0.76 ± 0.11 | 2.27 ± 0.34 | 0.35 ± 0.08 | 0.092 |

**Transfer** — the 5 µs-trained model scored on the other front ends with its own threshold: node 0.082 % / 0.55 %, 2 µs 0.107 / 0.54, 5 µs 0.100 / 0.56, 10 µs 0.138 / 0.57 (false trips / missed). The model trained on `nodes_v1xl6k` (the clean stream) scored on the node front end: 0.42 % false trips; on 5 µs: 0.15 % — the training front end must be the node's, not the dataset's.

**Pre-registered criteria and verdicts.** (1) node_ideal ≤ 0.1 σ on every feature — PASS except `didt_max` 0.12–0.14 σ (recorded). (2) ≥ 99 % identical decisions at ≤ 5 µs under the *as-trained* model — FAIL (97–98 %), cause: the node front end itself (criterion mis-specified; the relevant number is the retrained row). (3) 1 800-event corrected run: ≤ 10 benign new trips of 600 at 5 µs and spec ≤ 0.15 σ — PASS (9, 0.11). (4) Budgeted rows ref / node / 2 / 5 µs within 0.1 % missed — PASS (0.42–0.57 %); 10 µs ≤ 0.7 % — PASS (0.59). (5) P2-style: held-out false trips in 0.05–0.20 %, missed ≤ 0.7 % — PASS (0.100 ± 0.003, 0.57).

**Reading for the HIL.** The relay transfers. Trained on the node front end at a 5 µs hold, the two-node relay holds its 0.1 % false-trip budget on held-out calibration and misses 0.57 ± 0.08 % of faults (0.42 % on the ideal stream; the difference is ≈ 7 high-Z 800 V events in 5 000 and nothing on the 48 V side), and the same model holds the budget for any box step from 0 to 5 µs (0.08–0.11 %). The step requirement to the HIL company is therefore the plant-side one: **≤ 5 µs required, 2 µs preferred, 10 µs usable with caveats (relay 0.14 % false trips, physics 0.5 %), 20 µs not acceptable.** The 12-bit DAC replay is indistinguishable from a 1 µs box for the relay (latency fallback only, as decided). Consequences: (a) the firmware model `fx_model_data.h` is retrained on `data/hil_frontend_aa/features_*_hil_5us.csv` (`tools/train_model.py --cache`, θ = 0.067 in the HIL settings profile), M2 agreement rerun; the committed model trained on `nodes_v1xl6k` is not to be used on hardware; (b) the same model serves the bench (node front end column) until the measured filter and noise floor are in the bench dataset; (c) `--box-noise` is run when the company gives the AO noise floor.

**Caveats.** Node and box noise 0; the 100 kHz filter is the designed response (measured response → bench dataset, MODEL.md 0.4.5 front-end option); W = 0.25 ms only, phase 0 only (phase and W = 1 ms runs deferred — nothing in the corrected chain depends on them at ≤ 5 µs); single training set (`v1xl6k`); in-sample-calibrated single-seed numbers of the first full run (`hil_operating_points.md`, 15 Oct 01:40) agree with the held-out ones within 0.07 %.

## Breaker element — fix 2026-10-16 (HIL model review #2)

The breaker element (MODEL.md 0.4.5 proposal, `dcsim_rt_step.m`, never exercised by check (i) or `rt_sweep`, where no breaker trips) zeroed `i_L` before and after the RK4 step but not inside it: the four stage states carried a feeder current `(v_c − v_bus)/L_line × dt/2` into `dv_bus/dt`, so an *open* feeder SSCB still charged the bus. Effect: after a feeder trip `v_bus` settled at 0.6 p.u. (R_f 3 Ω) / 0.79 p.u. (8 Ω) at 5 µs instead of decaying through the fault — and the level depended on dt (0.41 / 0.69 at 2 µs; the review's Python transliteration). The plateau is visible in the 15 Oct `highz800` / `highz800_hard` demo plots and was not caught in the 15 Oct review of those plots. Fix: `k1..k4(2) = 0` while `brk_f < 0.5` (same four lines in `rt_port_check.py`). With both breakers closed the lines are inert, so `rt_sweep` and `rt_hil_check` are bit-identical before and after (to be confirmed by the re-run). After the fix v_bus at +3 ms is 0.19 / 0.51 p.u. at both 2 and 5 µs (review table) and keeps falling. The rack breaker was correct (its state reaches the derivatives as flags). The post-trip waveforms have no reference solution yet; they are not used in any dataset or threshold.
