# simscape/ — single-shelf cross-check model (MODEL.md check (i))

Three files: `build_dcsim_shelf.m` builds the model programmatically (Simscape Electrical Foundation library + Simulink control, one-to-one with `dcsim/model_v04.py`); `run_case.m` loads one case from `data/simscape/` (written by `python scripts/simscape_cases.py`), sets parameters and exact initial conditions, simulates on the 1 µs reference grid, and writes `sim_<case>.mat`; `run_all_cases.m` does all eight and scores each with `scripts/compare_simscape.py`.

**These were written without MATLAB.** Verify the following on first open, in this order — each is a one-minute check and each is the kind of thing that fails loudly.

## 1. Port conventions (the `P` struct at the top of `build_dcsim_shelf.m`)
Open the built model and hover the ports of one block of each type. The assumed conventions:

| block | assumed |
|---|---|
| Resistor / Inductor / Capacitor / Diode / DC Current Source | `LConn1` = +, `RConn1` = − |
| Switch | `LConn1` = +, `RConn1` = −, `LConn2` = PS control |
| Controlled Current / Voltage Source | `LConn1` = PS control, `RConn1` = +, `RConn2` = − |
| Current Sensor | `LConn1` = +, `RConn1` = −, `RConn2` = I (PS out) |
| Voltage Sensor | `LConn1` = +, `RConn1` = −, `RConn2` = V (PS out) |

If any differ, edit `P` only; every connection uses it. The Diode's anode/cathode assignment matters in two places: the ORing diode (`Dor`, must conduct bus → input node) and the limiter diode (`Dlim`, must carry I_lim − i_L from the limiter's output node back to its input node; see the NOTE in the file).

## 2. MATLAB Function block scripts
`set_script` injects the code through the Stateflow API (`sfroot`). If it errors, open each block and paste the text from `ctrl_script()` / `uvlo_script()` by hand. The `prm` vector order (17 entries) is defined in `run_case.m` and consumed by both scripts — do not reorder.

## 3. Discrete sample time on `uvlo48`
The UVLO block uses `persistent` variables and must run at a fixed 1 µs sample time (block parameter *Sample time*, or `ch.SampleTime = '1e-6'`). At the inherited/continuous rate the persistent timer would update on minor steps and the trip time would be wrong. 1 µs is inside the 5 µs edge tolerance of check (i).

## Reading a failure (from the build sheet §4)
- `v_out` off in `step` → PI freeze rule or integrator IC (`int_xi`).
- `i_rack` off in `bolted_48` → switch/diode default resistance not zeroed, or the UVLO comparing the capacitor voltage instead of the node.
- `i_L` off in `high_z` → the current limiter (`Ilim`/`Dlim`) or the ORing diode (`Dor`).
- slow drift on every channel from t = 0 → wrong initial conditions (check `run_case.m` assigned all `ic_*`).
- everything wrong from the start → a port convention (§1).

## Criterion (pre-registered 2026-09-17)
Excluded-RMS ≤ 1 % on i_L, v_bus, i_rack, v_out with ±5 µs exclusion around reference jumps > 0.1 p.u.; every such edge matched in the Simscape run within 5 µs and 20 % in size; raw RMS reported. All eight runs.
