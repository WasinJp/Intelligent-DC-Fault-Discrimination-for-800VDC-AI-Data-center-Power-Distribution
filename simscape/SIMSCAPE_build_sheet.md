# Simscape build sheet — single-shelf cross-check of MODEL.md v0.4.2 (check (i))

Purpose: an **independent implementation** of one rack shelf on an 800 VDC segment, in Simscape Electrical, that reproduces the Python core's waveforms on four events to ≤ 1 % normalised RMS over the fine window. It is the correctness credential and the plant picture for the video. It is not the Monte Carlo and not the classifier.

Scope: averaged converter, same as the Python core. Do **not** build a switching LLC/DAB — it adds weeks, it is not what the Python model is, and the comparison would then be testing two different things. Switching-level is a later, separate model if anyone asks for it.

Everything numeric comes from `scripts/simscape_cases.py`: `params.json` (shared baseline, PI gains), `cases.json` (per-case fault values, smoothing flag, **exact initial state**), and each `ref_<case>.mat` (reference waveforms, `P_gpu`, `load_on48`, `conv_on`). Do not retype values.

**Revision 2026-09-17.** The first version of this sheet had nine errors that would have failed check (i) for non-physics reasons; they were found by reading the reference runs before any Simscape model existed. Corrected below: the POL UVLO *does* trip in `bolted_48`; the source current limit *is* reached in three runs; the ORing diode blocks in `high_z`; the ramp limiter is one saturated integrator; controls read capacitor voltages, UVLO comparators read node voltages; the anti-windup rule is exact and includes the power bound; block defaults must be zeroed; per-case parameters and initial states are now exported.

---

## 1. Element map

Build every storage element as an **ideal Capacitor plus a separate Resistor** (not the capacitor block's ESR field), and put the Voltage Sensor **across the capacitor alone**. The Python controls read the capacitor states; the logged v_bus and v_out are the node voltages including the ESR drop; the UVLO comparators read the node voltages. At `bolted_48` currents, 0.3 mΩ × 30 kA is 9 V — sensing the wrong side is a guaranteed failure.

| Python (model_v04) | Simscape Electrical block(s) | notes |
|---|---|---|
| **source** `τ_c dv_c/dt = V_ref − R_droop i_L − v_c` | Controlled Voltage Source driven by Simulink: `V_ref − R_droop·i_L` → Transfer Fcn `1/(τ_c s + 1)` | i_L from a Current Sensor in the feeder |
| **source current limit** `i_L ≤ I_lim` (derivative clamp) | DC Current Source of I_lim in parallel with an ideal Diode (diode carries I_lim − i_L), the pair in series with the feeder | invisible below the limit; holds exactly I_lim above it. **Reached in `high_z`, `high_z_sm`, `bolted_48`** (i_L peaks at 288.75 A) — required |
| `i_L ≥ 0` | ideal Diode in series with the source | |
| **feeder** R_line, L_line | Resistor + Inductor | |
| **800 V bus** C_bus, R_esr | ideal Capacitor + Resistor to ground; sense across the capacitor for control, at the node for logging | C_store = 0 in all eight cases |
| **800 V fault** R_f, L_f | Switch + Resistor + Inductor, bus to ground; closes at t_event in `high_z` | switch closed resistance → 0 (§ block defaults) |
| **rack input** L_in, R_in, ORing | Inductor + Resistor + ideal Diode from bus to input node | **blocks in `high_z`** (i_Lin → 0 while C_bus discharges) — required |
| **input node** C_in, R_in_esr | ideal Capacitor + Resistor; sense v_Cin across the capacitor | |
| **converter input draw** | Controlled Current Source from the input node to ground, `i_in = P_in / max(v_Cin, V_uvlo)` | v_Cin is the *capacitor* voltage |
| **ramp limiter** (smoothing on) | Sum(P_req − P_cmd) → Gain 1/τ_r → Saturation ±S_max → Integrator → P_cmd, with P_cmd fed back to the Sum. `P_in = P_cmd`. Integrator IC = `P_cmd` from cases.json | this is one state: `dP_cmd/dt = sat((P_req − P_cmd)/τ_r, ±S_max)`. A Rate Limiter followed by a lag is a different system |
| (smoothing off) | `P_in = P_req` | |
| **P_req** | `P_req = v_out·sat(i_ref) + P_loss(v_out·sat(i_ref))`, `P_loss = p_fix·P_rated + k2·P²/P_rated`, gated by `conv_on` | v_out is the *capacitor* voltage; sat = clamp to [0, I_lim_out] |
| **voltage loop** (build by hand, ~5 blocks) | `err = V_ref48 − v_out`; `i_ref = K_p·err + K_i·ξ`; Integrator ξ with IC from cases.json, **integrating `err` only when the final clamped command equals i_ref**, else 0 | the freeze compares against the command *after* the current limit **and** after the power bound (smoothing on). No sign test. The PI Controller block's clamping mode is not equivalent |
| **command clamps** | `sat = min(max(i_ref, 0), I_lim_out)`; smoothing on: `sat = min(sat, (P_in − p_fix·P_rated)/max(v_out, 1))` | |
| **inner loop** | Transfer Fcn `1/(τ_i s + 1)` → Controlled Current Source into the 48 V node; IC = `i_co` from cases.json; multiplied by `conv_on` | `conv_on` stays 1 in all eight cases (input UVLO never trips) — may be a constant |
| **48 V bus** C_out, R_out_esr | ideal Capacitor (IC = 50 V) + Resistor; sense across the capacitor for control, at the node for logging | 3.7 F: the storage |
| **POL load** | Controlled Current Source, `i_pol = load_on48 · P_gpu / max(v_out, V_uvlo48)`; P_gpu from the `P_gpu` vector in ref_<case>.mat via From Workspace | v_out is the *capacitor* voltage |
| **POL UVLO** — **required for `bolted_48` and `bolted_48_sm`** | Simulink: Compare(v_out,node < V_uvlo48) → on-delay t_uvlo48 (timer that resets when the comparison is false) → latch `load_on48 = 0`; re-enable when v_out,capacitor > V_uvlo48 + V_hyst48 | trips at +0.62 ms (off) / +0.58 ms (on); i_rack steps by ~0.5 p.u. at that instant. Compares the **node** voltage |
| **input UVLO** | not needed for these eight cases (never trips); `conv_on = 1` | |
| **48 V fault** R_f48, L_f48 | Switch + Resistor + Inductor, 48 V node to ground; closes at t_event in the `_48` cases | closed resistance → 0: at R_f48 = 1 mΩ a default 10 mΩ switch is a 10× error |
| **rack-node observable** `i_rack = i_pol + i_f48` | one Current Sensor on the common branch feeding the POL source and the 48 V fault | |
| **feeder observable** | Current Sensor in the feeder; Voltage Sensor at the bus node (with ESR) | |

**Block defaults.** Foundation-library Diode: forward voltage 0.6 V and on-resistance 0.3 Ω by default; Switch: closed resistance 10 mΩ by default. Set every diode Vf = 0, Ron = 1 µΩ (or the smallest the solver accepts), Goff as small as possible; every switch Ron = 1 µΩ. Anything in the milliohm range is comparable to R_f48 = 1 mΩ.

**Initial conditions.** Use the exact steady state exported in `cases.json → initial_state` (v_c, i_L, v_C, v_Cin, i_Lin, P_cmd, ξ_v, i_co, v_out; both fault currents 0). The Python reference is perfectly flat before the event; a pre-roll from wrong ICs would still be settling in the 0.2 ms pre-window at a 100 Hz voltage loop. Set the ICs directly on the capacitors, inductors, and the two integrators.

## 2. Solver

- Variable-step, stiff: **ode23t** (or daessc). Relative tolerance 1e-6, absolute 1e-6.
- Max step 1e-6 s. Zero-crossing detection on for the switches.
- Record −0.2 ms to +5 ms around the event at a fixed 1 µs output grid (Configuration → Data Import/Export → output times = `linspace`), so the export aligns with the reference without interpolation artefacts.

## 3. The four cases (× 2 smoothing states = 8 runs)

All at `PARAMS_BASELINE`, P0 = 0.5·P_rated, event at t = 2 ms of a 7 ms record.

| case | what | expect on the feeder | expect at the rack |
|---|---|---|---|
| step | POL power +40 % of P_rated over 2 ms | current ramps ~10 ms (voltage loop + storage) | current steps in 2 ms |
| high_z | 800 V fault R_f = 5 Ω | early current +0.42 p.u. in 50 µs, bus dip | almost nothing |
| high_z_48 | 48 V fault R_f48 = 20 mΩ | a load step, zero early-window signature | converter clamps; busbar current from the storage |
| bolted_48 | 48 V fault R_f48 = 1 mΩ | an idle drop after a brief transient | several p.u. surge, v_out collapses |

The `_sm` variants have `smooth_on = 1` and show the ramp limiter shrinking the feeder's step for `high_z_48` (0.61 → 0.17 p.u. in the Monte Carlo).

## 4. Export and compare

Log `t, i_L, v_bus, i_rack, v_out` with To Workspace (save format: Array) on the 1 µs output grid, shift `t` so the event is at 0, and `save('sim_<case>.mat', 't', 'i_L', 'v_bus', 'i_rack', 'v_out')`. Then:

```
python scripts/simscape_cases.py                 # once: ref_*.mat, params.json, cases.json
python scripts/compare_simscape.py data/simscape/ref_high_z_48.mat data/simscape/sim_high_z_48.mat
```

**Pre-registered criterion (2026-09-17, revised the same day before any Simscape result).** PASS requires (1) *discontinuity-excluded* normalised RMS ≤ 1 % on all four channels, exclusions ±5 µs around any adjacent-sample jump larger than 0.1 p.u. in the reference — the POL-UVLO edge in `bolted_48` / `bolted_48_sm` on `i_rack`; (2) every such edge matched in the Simscape run within 5 µs and 20 % in size; (3) raw RMS reported alongside. The window was narrowed from ±50 µs: 5 µs still absorbs 20× the reference-grid jitter (0.25–0.35 µs) but is 1/20 of t_uvlo48, so a UVLO built with the wrong delay or threshold fails the edge line (verified: a 55 µs delay fails; a 1 µs solver shift passes). Identical for every run, not adjusted after the fact.

Reference-grid check: the 1 µs reference differs from a 50 ns run by ≤ 2 × 10⁻⁴ on every channel except that one sample (7.4 × 10⁻³ raw on `bolted_48` i_rack, 2 × 10⁻⁵ excluded).

What a first failure usually means: `v_out` off in `step` → PI freeze rule or integrator IC; `i_rack` off in `bolted_48` → switch/diode default resistance, or the UVLO comparing the capacitor voltage instead of the node; `i_L` off in `high_z` → the current limiter or the ORing diode missing; a slow drift on every channel → wrong initial state.

## 5. For the video

The schematic **is** the plant slide; colour the two sensing nodes. Run `high_z_48` with a scope on the feeder current and the rack current side by side: the top trace looks like a load step, the bottom trace is the storage bank emptying into a fault. That one clip is the argument. Overlay the Python relay decision (TRIP at 0.25 ms from the rack node; HOLD-then-alibi-check from the feeder) as a title card — Python produces it, Simscape shows why it's needed.

## 6. Time

First working model with the eight runs: two to three days for someone who has used Simscape Electrical before. The element map above is deliberately one-to-one with `model_v04._derivs`, so if a channel disagrees the culprit is a single block.
