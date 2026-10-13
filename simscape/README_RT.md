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
