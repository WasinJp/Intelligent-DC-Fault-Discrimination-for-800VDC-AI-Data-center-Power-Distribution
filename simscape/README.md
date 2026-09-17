# simscape/ — single-shelf cross-check model (MODEL.md check (i))

Core files: `build_dcsim_shelf.m` builds the model programmatically (Simscape Electrical Foundation library + Simulink control, one-to-one with `dcsim/model_v04.py`); `run_case.m` loads one case from `data/simscape/` (written by `python scripts/simscape_cases.py`), sets parameters and exact initial conditions, simulates on the 1 µs reference grid, and writes `sim_<case>.mat`; `run_all_cases.m` does all eight and scores each with `scripts/compare_simscape.py`.

**These were written without MATLAB.** Verify the following on first open, in this order — each is a one-minute check and each is the kind of thing that fails loudly.

## 0. How to run — one command
```
>> cd <repo>/simscape
>> crosscheck            % all stages, then the 'step' case
>> crosscheck('all')     % all stages, then all eight cases
>> crosscheck('rebuild') % force a fresh port detection and model build
```
Everything it prints also goes to `simscape/crosscheck_log.txt`. It stops at the first failing stage.

| stage | what | file |
|---|---|---|
| 0 | reference data exists; if not, runs `scripts/simscape_cases.py` with the `.venv` Python (`data/simscape/` is not in git) | `ensure_cases.m` |
| 1 | port conventions detected and proven for this MATLAB release | `detect_ports.m`, `test_conventions.m` → `shelf_ports.m` |
| 2 | model built; an `.slx` made by an older builder is rebuilt (tag in the model Description) | `build_dcsim_shelf.m`, `shelf_build_tag.m` |
| 3 | scripts injected, UVLO at 1 µs, compiles with algebraic loops as errors | `verify_build.m` |
| 4 | pre-event window flat at the Python steady state (≤ 1e-4 p.u.) | `smoke_test.m` |
| 5 | cases run and scored by `scripts/compare_simscape.py` | `run_case.m`, `run_all_cases.m` |

`load_case.m` puts one case's parameters and initial conditions in the base workspace; the model's block parameters are those variable **names**, so the model cannot be opened, compiled or run before `load_case` has run (the builder now calls it itself). `probe_blocks.m` is a diagnostic (prints every block's ports and parameter names). `warmup_*.m` belong to the hand-built warm-up circuit, not to check (i).

**Explicit control states (2026-09-18).** `ctrl_d` is a discrete MATLAB Function (Ts = 1 µs) that advances ξ_v, P_cmd and i_co with an explicit RK4, holding the sensed `v_out` over the step; `ctrl` keeps only the algebra (`i_in`, `i_pol`) and the diagnostic outputs. The first version used continuous Integrators under ode23t and failed `step_sm` and `high_z_48_sm`: the anti-windup freeze makes the loop a sliding-mode system, and the implicit solver accepted steps in which ξ_v moved against its own derivative (MODEL.md §4.8 note). The Simscape network itself is still solved by ode23t. `scripts/diagnose_simscape.py` (run automatically on a FAIL) prints which quantity departs from Python first and the control internals around it.

**Sense lags (2026-09-18).** A Simscape network counts as direct feedthrough from its Simulink inputs to its outputs, so capacitor voltage → `ctrl` (algebra) → `i_in` / `i_pol` → network is a Simulink algebraic loop. It is broken on the measurement side: `v_Cin` and `v_out` reach `ctrl` through a first-order lag `tau_sense` = 0.2 µs (an Integrator with the exact initial condition, set in `load_case.m`). Capacitor voltages are smooth states, so the error is τ·dv/dt — under 2 mV on `v_out` in `bolted_48`, below 1e-4 of scale — and the `load_on48` edge on `i_pol` stays sharp. The Python core has no such lag; this is a numerical device of the Simscape implementation and is reported with check (i).

## 1. Port conventions — detected, not assumed (revised 2026-09-18)
The first R2026a run showed the hand-written port table was wrong in layout, not in one index: sources, sensors and the Switch have one left port and two right ports, and `LConn1` on the Controlled Voltage Source is electrical. `detect_ports.m` now finds the conventions by experiment and writes `shelf_ports.m`:

- **roles** (physical-signal vs electrical) by trial connection — `add_line` refuses to join a signal port to an electrical port;
- **polarities** by simulation — the one-resistor circuits of `test_conventions.m` are built with a tentative polarity and every wrong-signed reading flips its entry. The Controlled Voltage Source is the anchor; diode, capacitor, inductor and DC current source each have their own entry (`P.dio`, `P.cap`, `P.ind`, `P.dcs`).

It then re-runs `test_conventions` from the generated file; that run must print ALL PASS. Do not edit `shelf_ports.m` by hand. Initial conditions are variable targets in this release: capacitor `vc` / `vc_specify` / `vc_priority`, inductor `i_L` / `i_L_specify` / `i_L_priority` (the builder's original `v0` / `i0` do not exist).

Two orientations still matter and are fixed by the builder's wiring, given a correct `P.dio`: the ORing diode (`Dor`) conducts bus → input node; the limiter diode (`Dlim`) carries I_lim − i_L from the limiter's output node back to its input node, opposite to `Dsrc`.

## 2. MATLAB Function block scripts
`set_script` injects the code through the Stateflow API (`sfroot`). If it errors, open each block and paste the text from `ctrl_script()` / `uvlo_script()` by hand. The `prm` vector order (17 entries) is defined in `run_case.m` and consumed by both scripts — do not reorder.

## 3. Discrete sample time on `uvlo48`
The UVLO block uses `persistent` variables and must run at a fixed 1 µs sample time (block parameter *Sample time*, or `ch.SampleTime = '1e-6'`). At the inherited/continuous rate the persistent timer would update on minor steps and the trip time would be wrong. 1 µs is inside the 5 µs edge tolerance of check (i).

## Reading a failure (from the build sheet §4)
- `v_out` off in `step` → PI freeze rule or integrator IC (`int_xi`).
- `i_rack` off in `bolted_48` → switch/diode default resistance not zeroed, or the UVLO comparing the capacitor voltage instead of the node.
- `i_L` off in `high_z` → the current limiter (`Ilim`/`Dlim`) or the ORing diode (`Dor`).
- slow drift on every channel from t = 0 → wrong initial conditions (check `run_case.m` assigned all `ic_*`).
- everything wrong from the start → a port convention (§1): re-run `detect_ports`.

## Criterion (pre-registered 2026-09-17)
Excluded-RMS ≤ 1 % on i_L, v_bus, i_rack, v_out with ±5 µs exclusion around reference jumps > 0.1 p.u.; every such edge matched in the Simscape run within 5 µs and 20 % in size; raw RMS reported. All eight runs.
