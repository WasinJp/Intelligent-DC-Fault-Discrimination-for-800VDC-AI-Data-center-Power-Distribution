# MODEL.md — 800 VDC AI Data Center Distribution Segment: Physics Model Specification

**Version:** 0.4.3
**Date:** 2026-09-17
**Status:** single source of truth for `dcsim`. Every dataset records the MODEL.md version and master seed it was generated from; a dataset is reproducible from those two values alone.
**Project:** Intelligent DC Fault Discrimination for 800 VDC AI Data Center Power Distribution — Delta Cup 2026, Energy Track.

Core selection: `events.CORE_VERSION = "v0.4"` (this document) or `"v0.3"` (the four-state segment of datasets v0.2 and v1; §4.1–§4.5 only, rack as a constant-power load). Workload selection: `events.WORKLOAD_VERSION = "v1"` (§5.1) or `"v0.2"` (single 20–200 ms train, dataset v0.2 reproduction).

---

## 1. Purpose and design rules

The model exists to quantify one question: at what point does a legitimate AI-workload transient become indistinguishable, at the protection relay, from a fault — and what information resolves the ambiguity. It is a Monte Carlo digital twin, not a design tool: wide parameter sweeps, thousands of labelled events, and a discrimination pipeline that sees only what a relay would see.

Design rules that every version must keep:

1. **Pristine physics and synthesised observables are separate layers.** The core (`model_v04.py`) integrates hidden states. The synthesis layer (`synth.py`) turns two node voltages and two node currents into what an acquisition front end delivers. The feature extractor and classifier never touch hidden states, ground-truth labels, or the true event time; onset is detected on the observables.
2. **Every discontinuity lands on a step boundary.** Load steps, fault inception and clearing, arc profiles are step-indexed. Fixed-step RK4 on a segmented time base is therefore an event-aware scheme, not a stiff-solver substitute.
3. **Validation before generation.** The checks in §8 must pass before any dataset is produced. They are analytic or independent-implementation comparisons, not self-consistency.
4. **Pre-registration.** Expected results are written down before a run (§9.4). A prediction that fails is reported as such.
5. **Reproducibility.** `(MODEL.md version, master seed)` determines every event. Per-event seeds derive from the master seed and event index; synthesis noise from a fixed offset.

## 2. Topology

One distribution segment: a source converter feeding an 800 VDC busbar, a rack conversion stage stepping down to a 48 V rack bus, and the GPU load behind point-of-load converters. Two sensing points.

```
 SOURCE            FEEDER                 800 V BUS            RACK STAGE                       48 V BUS            LOAD
 V_ref, R_droop    R_line, L_line         C_bus, R_esr         L_in, R_in  C_in, R_in_esr       C_out, R_out_esr    POL converters
 tau_c  ──► v_c ───────────► i_L ───►  v_bus ─┬─────────► i_Lin ─┬─► v_Cin ─►[ DC-DC ]─► i_co ─► v_out ─┬─► i_pol = P_gpu / v_out
                                              │                  │            η(P), PI, I_lim_out       │
                                              ├─[ R_f, L_f ] i_f │            ramp-rate front end       ├─[ R_f48, L_f48 ] i_f48
                                              │  800 V fault     └ storage                              │  48 V fault
                              ▲ series arc (busbar, arc_place = 1)      ▲ series arc (rack input path, arc_place = 0)

 FEEDER NODE observables: i_L, v_bus            RACK NODE observables: i_co, v_out
```

Under `CORE_VERSION = "v0.3"` the rack stage is absent: the rack is a constant-power load `i = P/v` at the 800 V bus and `C_bus` (1–50 mF) is the rack input capacitance.

## 3. States and notation

| # | state | unit | meaning |
|---|---|---|---|
| 0 | v_c | V | source converter output (droop + first-order lag) |
| 1 | i_L | A | feeder (busbar) current |
| 2 | v_C | V | 800 V bus capacitor voltage (distribution capacitance) |
| 3 | i_f | A | 800 V fault-branch current |
| 4 | i_Lin | A | rack input inductor current (rack draw from the bus) |
| 5 | v_Cin | V | rack input storage capacitor voltage — the "65 J/GPU" element |
| 6 | P_cmd | W | ramp-rate-limited bus-side power command (front-end controller) |
| 7 | ξ_v | A·s | outer 48 V voltage-loop integrator |
| 8 | i_co | A | converter output current (inner current loop, first-order lag) |
| 9 | v_out | V | 48 V bus capacitor voltage |
| 10 | i_f48 | A | 48 V fault-branch current |

Algebraic node quantities: v_bus = v_C + R_esr·i_C; v_Cin,node = v_Cin + R_in_esr·i_Cin; v_out,node = v_out + R_out_esr·i_Cout. Per-unit bases: feeder I_rated = P_rated / V_ref; rack I_out,rated = P_rated / V_ref48.

## 4. Component models

### 4.1 Source converter
`τ_c · dv_c/dt = V_ref − R_droop · i_L − v_c`. Droop 0.2–5 %, lag τ_c 16–320 µs (control bandwidth 0.5–10 kHz). Unidirectional: `i_L ≥ 0` (OPEN-7); output current clamp `i_L ≤ I_lim` implemented as a derivative limit (OPEN-1).

### 4.2 Feeder
`L_line · di_L/dt = v_c − R_line · i_L − V_arc,line − v_bus`.

### 4.3 800 V bus node
`C_bus · dv_C/dt = i_C`, `i_C = i_L − i_Lin − i_f`. Bus voltage cannot go negative (freewheel diodes, OPEN-6). Under v0.3, `i_Lin` is replaced by the constant-power load current `P/v` with a UVLO floor.

### 4.4 800 V fault branch
Shunt R_f–L_f switched in over the fault window: `L_f · di_f/dt = v_bus − R_f · i_f`, with the freewheel clamp preventing reverse fault current once the bus is at zero.

### 4.5 Series arc (§5.4)
A voltage drop V_arc(t) in series with either the busbar (`arc_place = 1`, upstream of the bus capacitance) or the rack input path (`arc_place = 0`, between bus and storage). Static Stokes–Oppenländer level with band-limited 1/f-weighted noise; no ignition/extinction dynamics (OPEN-22).

### 4.6 Rack input filter (v0.4.1)
```
L_in · di_Lin/dt = v_bus − R_in · i_Lin − v_Cin,node
C_in · dv_Cin/dt = i_Lin − i_in,        i_in = P_in / v_Cin
```
C_in is a small bulk/EMI capacitance (0.1–5 mF) behind an ORing stage: `i_Lin ≥ 0`, the shelf cannot back-feed the bus. The large energy storage is **not** here (see §4.9): 65 J per GPU is 3.7 F per 72-GPU rack at 50 V and only 15 mF at 800 V, and only the former fills half a power shelf. v0.4 had it on the input side; corrected in 0.4.1.

**Bus-side storage** (a capacitance shelf, or a BBU without reverse blocking) is a separate sweep element: `bus_storage` with p = 0.5 adds `C_store` (1–50 mF) directly to C_bus, on the bus, where it *can* feed a bus fault. This is the regime in which the dataset-v1 "storage hides high-impedance faults" finding applies; storage behind the ORing stage does not hide them.

### 4.7 Converter-input ramp-rate limiter (v0.4.1; OPEN-13 in its simplest form)
When `smooth_on = 1` the converter's input power draw chases the voltage loop's demand at a bounded rate, and the output storage supplies the deficit:
```
P_req    = v_out · sat(i_ref) + P_loss                      (what the loop asks for)
dP_cmd/dt = sat( (P_req − P_cmd) / τ_r , ±S_max )
P_in     = P_cmd,   P_out,max = P_in − P_loss,   i_co ≤ P_out,max / v_out
```
With `smooth_on = 0`, P_in = P_req and the converter delivers whatever the loop asks up to I_lim,out. This is the GB300-class "power smoothing with embedded energy storage" mechanism placed where it acts; the v0.3 "smoothed workload regime" was the same thing modelled as a property of the load. The front end is a passive filter in both modes, so the 800 V-side stability criterion (§6, gate 1) holds as written.

### 4.8 Averaged DC-DC converter (v0.4)
Power balance with a two-term loss model:
```
P_out = v_out · i_co
P_req = P_out + P_loss,   P_loss = p_fix · P_rated + k2 · P_out² / P_rated      (η = 0.98 at rated, 0.95 at 20 %)
```
Cascaded control: outer PI voltage loop on v_out, inner current loop as a first-order lag with an output current limit.
```
i_ref = K_p (V_ref48 − v_out) + K_i ξ_v,      dξ_v/dt = V_ref48 − v_out   (held when i_ref is clamped: anti-windup)
τ_i · di_co/dt = sat(i_ref, 0, I_lim,out, P_out,max / v_out) − i_co
```
PI tuning for a capacitor plant with an ideal inner loop: `K_i = C_out (2π f_v)²`, `K_p = 2 ζ_v √(K_i C_out)`, ζ_v = 0.7. With the storage on the output (C_out up to 5 F) the voltage loop is slow by design (f_v 20 Hz–2 kHz); the current limit still engages within τ_i. The converter is off after the input UVLO trips (§4.10). Structure follows the aggregated buck-converter equivalent with cascaded voltage–current control of arXiv:2604.06624; the per-stage loss structure follows arXiv:2608.17925.

### 4.9 48 V bus, energy storage, POL load, 48 V fault branch (v0.4.1)
```
C_out · dv_out/dt = i_co − i_pol − i_f48
i_pol = P_gpu(t) / max(v_out, V_uvlo48)      while load_on48
L_f48 · di_f48/dt = v_out,node − R_f48 · i_f48
i_rack = i_pol + i_f48                        (load-side busbar current: the rack-node observable)
```
C_out is the rack energy storage (0.2–5 F at 48 V, scaled with rack power). The POL converters are a constant-power load on the 48 V bus with their own UVLO. The GPU workload P_gpu(t) (§5.1) is applied here, where it physically originates. The rack sensing point is the busbar **downstream of the storage**, so a 48 V fault is seen with the storage bank's discharge current in it (a bolted 48 V fault reads several p.u. at the rack node), not just the converter's limited contribution.

### 4.10 UVLO state machines
Input UVLO (converter): on `v_Cin,node < V_uvlo` for longer than `t_uvlo_delay`, `conv_on = 0`; recovers with hysteresis V_hyst. Recovery restores full commanded power without a re-ramp (OPEN-2). POL UVLO: on `v_out,node < V_uvlo48` for `t_uvlo48`, `load_on48 = 0`; recovers with V_hyst48.

### 4.11 What a 48 V fault looks like from the 800 V bus (v0.4, the design consequence)
A bolted 48 V fault collapses v_out; the converter's delivered power falls to zero; the feeder sees the rack *disappear* — a load drop. A high-impedance 48 V fault clamps i_co at I_lim,out; the feeder sees drawn power rise to ≈ v_out·I_lim,out / η — a load step. Neither carries a fault signature at the feeder: on the early-window features that separate 800 V faults from workload steps, both 48 V fault classes read the same as benign steps (baseline single-event check, 2026-09-11: di_early and dv_early identically zero at the feeder for both). With the ramp-rate front end on, the residual feeder signature of a 48 V fault is smoothed further, and the 800 V high-Z fault signature at the feeder grows (the current-source front end isolates the storage from the fault front). On the v0.4 run (1 800 events, smoothing-off half) the feeder still caught 89 % of 48 V faults on *magnitude* — an unsmoothed 48 V fault pulls the converter to its current limit, a 40–60 % step — at a 6 % false-trip cost; scored on 800 V responsibility only, the same feeder relay ran at 0.03 % false trips. Whether stored energy hides 800 V faults from the feeder depends on which side of the input stage it sits: on the bus (C_store), yes; behind the ORing stage, no.

## 5. Event models

Every event is one record: workload history, then an event at the anchor `t_event = t_pre`, then post-event. Labels and decision classes:

| label | where | decision | note |
|---|---|---|---|
| benign_step | P_gpu, flat background | HOLD | commanded step, ramp 0.5–10 ms |
| benign_train | P_gpu, periodic background | HOLD | the next scheduled rising edge (tier 1 or 2) |
| benign_idle_drop | P_gpu | HOLD | unscheduled drop of 50–85 % of current demand |
| bolted_pp | 800 V bus | TRIP | R_f 1–20 mΩ |
| resistive_pp | 800 V bus | TRIP | R_f 20 mΩ–1 Ω |
| high_z | 800 V bus | TRIP | R_f 1–10 Ω |
| series_arc | busbar or rack input path | ALERT | V_arc 15–40 V + noise |
| bolted_48 | 48 V bus | TRIP | R_f48 0.5–5 mΩ |
| high_z_48 | 48 V bus | TRIP | R_f48 5–100 mΩ (straddles V48 / I_lim,out ≈ 15 mΩ) |

Background rule: benign_train always periodic; benign_step always flat; all other labels 50/50. Composite events (35 % of faults): the fault ignites inside an active workload ramp.

### 5.1 Workload v1 — two-tier cadence (sources: EVIDENCE.md)
AI training is bulk-synchronous: every GPU alternates compute and communication in lockstep, and the rack power traces a square wave at the iteration period. Measured periods run 0.3–10 s; FFT energy concentrates at 0.2–3 Hz. Inside compute phases, shorter power overshoots at ~50 ms scale (electrical-design-power peaks) ride on the iteration wave.

- **Tier 1, iteration:** period T₁ log-uniform 0.3–3 s (the 10 s tail is out of sweep for compute, OPEN-17), duty 0.3–0.7, amplitude ΔP₁ 0.10–0.80 p.u. (single regime under v0.4; the "smoothed" regime of v0.3 is now the front end's ramp-rate controller, §4.7), ramp 0.5–10 ms. Rising edges on a phase-locked grid, each perturbed by U(−j, j)·T₁ with j ≤ 2 % — interval jitter, not drift. The scheduled event edge carries its own jitter.
- **Tier 2, EDP-peak bursts:** present with p = 0.6 on periodic backgrounds; period T₂ log-uniform from 20 ms to min(200 ms, duty·T₁/3); duty 0.3–0.7; amplitude 0.05–0.25 p.u.; ramps 0.5–5 ms; jitter ≤ 2 % of T₂. Bursts exist only inside compute phases and are phase-locked to each phase start (offset 2–10 % of T₁); bursts in different phases are not coherent modulo T₂.
- **Scheduled event:** benign_train lands on the next rising edge of tier 1, or of tier 2 when present (50/50); recorded as `sched_tier`.
- History: `t_pre = 2.5·T₁ + 0.1 s` on periodic backgrounds (up to 7.6 s), 60 ms on flat ones.

### 5.2 Benign events
benign_step: ΔP uniform 0.10–0.80 p.u., sign + with p = 0.8, ramp 0.5–10 ms. benign_idle_drop: 50–85 % of the demand at the anchor, ramp 1–5 ms.

### 5.3 Faults
Fault windows are `FAULT_DURATION = 5 ms` (an SSCB clears within that). 800 V faults per §4.4; 48 V faults per §4.9. Fault L: 0.5–10 µH (800 V), 0.1–2 µH (48 V).

### 5.4 Series arc
V_arc0 15–40 V, noise 5–25 % of V_arc0, band 1 kHz to f_hi (50 kHz–1 MHz), 1/f-weighted; ignition ramp 0.1–2 ms; placement busbar / rack path 50/50.

## 6. Parameter sweep (system draw, per event)

Log-uniform unless stated. Segment rating P_rated 100 kW–1 MW; per-rack quantities scale with it.

| group | parameter | range |
|---|---|---|
| source | V_ref | 760–840 V (uniform) |
| | R_droop | 0.2–5 % of V_ref / I_rated (uniform) |
| | τ_c | 16–320 µs |
| | I_lim | 1.5–2.0 × I_rated (uniform) |
| feeder | L_line, R_line | 1–50 µH, 1–20 mΩ |
| 800 V bus | C_bus | **0.1–2 mF** (v0.4; was 1–50 mF as rack capacitance under v0.3) |
| | R_esr | 2–20 mΩ |
| | V_uvlo, t_uvlo, V_hyst | 600–700 V × V_ref/800, 100 µs, 20 V |
| rack input | L_in, R_in | 1–20 µH, 1–10 mΩ |
| | C_in, R_in_esr | **0.1–5 mF** (v0.4.1), 2–20 mΩ |
| bus storage | bus_storage, C_store | p = 0.5; 1–50 mF added to C_bus (on the bus, can feed a fault) |
| smoothing | smooth_on | p = 0.5 |
| | S_max | 10 kW/ms – 1 MW/ms (converter-input ramp limit) |
| | τ_r | 50–500 µs |
| converter | p_fix, k2 | 0.01012, 0.01028 (η 0.98 rated / 0.95 at 20 %) |
| | V_ref48 | 48–54 V (uniform) |
| | C_out, R_out_esr | **0.2–5 F × (P_rated / 132 kW)** — the rack energy storage (65 J/GPU at 50 V); 0.2–2 mΩ |
| | f_v, ζ_v | 20 Hz–2 kHz, 0.7 |
| | τ_i | 10–50 µs (floor set by the 10 µs history tier) |
| | I_lim,out | 1.2–1.6 × I_out,rated (uniform) |
| | V_uvlo48, t_uvlo48, V_hyst48 | 0.75–0.85 × V_ref48, 50–200 µs, 4 % |
| sensor | noise_frac | 0.05–0.5 % of full scale |
| | adc_bits | {12, 14, 16} |

**Gate 1 (sanity gate).** A drawn system is accepted only if (i) the 800 V loop — source R–L, bus capacitance C_bus + C_in, and the load — has damping ratio ζ ≥ 0.15 under the linearised criterion `s² + (R/L − P/(C V²)) s + (1/LC)(1 − RP/V²) = 0`; (ii) the 48 V voltage loop with the POL constant-power load has ζ ≥ 0.15: `s² C_out + (K_p − P/V₄₈²) s + K_i = 0`; and (iii) **numerically** (v0.4.1): a 10 % load step at rated power rings down on both nodes — residual ripple in the last 2 ms below half that in the first 2 ms, or below 0.1 % of nominal — with no UVLO trip. The two-stage input makes (i) approximate; (iii) is what would have caught the v0.4 instability (a current-source front end decoupled the storage from the bus and left it stabilised by C_bus alone). Rejected draws are counted and reported. The gate censors the sweep non-uniformly against large segments (24 % of 700 kW–1 MW draws rejected vs 2 % of 100–200 kW under v0.3); report the accepted P_rated marginal alongside any per-unit result (OPEN-11).

## 7. Sensor synthesis (observables)

Two nodes, two streams each. Feeder node: i_L, v_bus. Rack node (v0.4): i_co, v_out. Applied to the pristine outputs, in order: anti-alias filter (4th-order Butterworth at 0.4·f_s, causal), decimation, additive white noise, ADC quantisation.

- **Fast stream:** f_s = 2 MSa/s by default over the fine window (−0.2 to +5 ms around the anchor); full scale 2·I_lim (feeder) / 2·I_lim,out (rack) and 1.25·V_ref / 1.25·V_ref48. Noise rms = noise_frac × full scale.
- **Slow stream:** 5 kSa/s over the whole record (2 kHz anti-alias). It is the same sensor averaged down: noise rms = noise_frac × full scale × √(f_slow / f_fast). (Dataset v0.2 applied the full rms at 50 kSa/s; retained only under `WORKLOAD_VERSION = "v0.2"`.)
- **Front-end sweep (OPEN-12):** any (f_s, bits) in {100 k, 250 k, 500 k, 1 M, 2 M} Sa/s × {12, 14, 16} can be stored alongside the default from the same physics pass; the anti-alias corner follows 0.4·f_s and the noise rms scales with √(f_s / 2 MSa/s). The slow stream is identical across configurations.

The feature extractor is rate-aware (all windows are times) and node-agnostic (normalised to the node's rating). Cadence learning runs on the slow stream of the node in use. No feature at decision time t depends on samples after t.

## 8. Time base and validation

### 8.1 Segmented time base
| segment | step | extent |
|---|---|---|
| deep history | `DT_HIST = 10 µs` | from 0 to 200.2 ms before the anchor (only when t_pre exceeds that) |
| near history / post-event | `DT_COARSE = 2 µs` | last 200 ms before the fine window; after it to t_post = 10 ms |
| event window | `DT_FINE = 50 ns` | −0.2 ms to +5 ms around the anchor (fault-branch τ down to 0.2 µs) |
| post-event history (v1-large) | `DT_HIST = 10 µs` | from +10 ms to 1.2 iterations after the anchor (0.5 s on flat backgrounds), so the workload timescale after the event is observable (Layer 3). Faults persist to the end of the record in `FAULT_MODE = "held"` — the relay did not trip, so the fault is still there. |

RK4 at 10 µs is stable for τ_c ≥ 16 µs and τ_i ≥ 10 µs (dt/τ ≤ 1) and resolves the fastest healthy resonance (5 kHz) at 20 steps per period. A 7.6 s history costs ~0.75 M steps. Per event: ~0.7–1.5 s.

### 8.2 Validation checks (all must pass before generation)
| check | what | criterion | typical |
|---|---|---|---|
| (a) | C_bus discharge into R_f–L_f vs the analytic underdamped RLC solution | RMS ≤ 10⁻³ | 6 × 10⁻¹⁵ |
| (b) | droop steady state v_bus = V_ref − (R_droop + R_line) I | ≤ 10⁻⁴ | 10⁻¹⁶ |
| (c) | segmented vs uniform 50 ns schedule through a high-Z fault | ≤ 10⁻³ | 10⁻¹³ |
| (d) | 10 µs history tier vs all-2 µs reference on a two-tier train, after the 2 kHz slow-stream anti-alias, at baseline and at the stiffest sweep corner, on feeder and rack observables | ≤ 10⁻³ | 3 × 10⁻⁴ (20 µs passes the corner with no margin; 40 µs fails) |
| (e) | converter steady state: v_out = V_ref48, P_in = P_gpu + P_loss | ≤ 10⁻³ | 0 |
| (f) | converter output current after a POL power step vs the exact linearised closed loop (PI, capacitor plant, CPL incremental conductance) | ≤ 10⁻² | 8 × 10⁻³ |
| (g) | converter-input ramp limiter: cumulative output-storage energy balance at every sample (KCL × v), input power slew ≤ S_max, input tracks demand after the ramp | ≤ 10⁻² | 3 × 10⁻⁴ |
| (h) | 48 V bolted fault: i_co saturates at I_lim,out; early di_f48/dt = V48 / L_f48 | ≤ 5 × 10⁻² | 4 × 10⁻³ |
| (i) | **Simscape Electrical cross-check** (independent implementation): single shelf, variable-step; step, high_z, high_z_48, bolted_48, each with smoothing off and on (8 runs); feeder and rack waveforms on the 1 µs reference grid | (1) discontinuity-excluded normalised RMS ≤ 1 % on i_L, v_bus, i_rack, v_out, exclusions ±5 µs around adjacent-sample jumps > 0.1 p.u. in the reference (the POL-UVLO edge in bolted_48; 5 µs is 20× the reference-grid jitter and 1/20 of t_uvlo48); (2) every such edge matched in the Simscape run within 5 µs and 20 % in size; (3) raw RMS reported alongside. Registered 2026-09-17 (window narrowed from ±50 µs the same day, before any Simscape result). | *pending* |

`scripts/validate_model.py` runs (a)–(h) and prints ALL PASS. (i) is the independent-implementation credential and is built from this document.

## 9. Gates and studies

### 9.1 Gate 1 — sanity gate (§6)
### 9.2 Gate 2 — conventional thresholds and the gray zone
Layer-1 detectors (magnitude, di/dt, voltage collapse, their OR) with thresholds at the edge of the benign envelope (zero false trips on the benign set). Reports missed faults per class, the gray-zone fraction (faults inside the benign envelope on all axes), and whether any threshold setting reaches false trip < 0.1 % and missed < 1 %. Sensitivity row at the 99th percentile (OPEN-11). Note: the conventional detector is noise-limited — its threshold is set by noise excursions on di/dt — so a lower-bandwidth front end shrinks the gray zone (66.5 % → 50 % from 2 MSa/s to 100 kSa/s on v1) without helping Layer 2.

### 9.3 Gate 3 — discriminator
Gradient-boosted trees (HistGradientBoosting, fixed hyper-parameters) on observable-only features, three decision classes. Feature groups: CONV (Δi, max|Δi|, max di/dt), PHYS (early voltage lead, early current, dynamic resistance, sag, minimum voltage, collapse flag, rise time, causal 1–100 kHz spectral floor), WORK (`has_period`, `period_strength`, `phase_err`). `phase_err` is the distance from onset to the nearest predicted rising edge of either learned cadence tier, folded to [0, 0.5]; it separates *scheduled* from *unscheduled* events, not benign from fault.

Reported as **5-fold stratified CV repeated over 10 fold seeds, mean ± std**; single-seed numbers are not quoted. Undetected onsets are excluded from training and scored HOLD. Studies: ablation (CONV / +PHYS / +WORK), latency (0.25 / 0.5 / 1 ms), domain shift (train < 400 kW, test ≥ 400 kW; single fit, directional), arc placement, operating curve, cadence report (tier-1 period accuracy, tier-2 detection and false detection, scheduled-event phase error by tier, alibi coverage), front-end sweep (OPEN-12), node study (v0.4: feeder-only, rack-only, feeder + rack with "detected at either node" as the onset rule).

Decisions taken from these studies (recorded so they are not re-litigated): `resid_period` dropped from WORK (0.92-collinear with Δi); `has_period` gating rejected (halving training data costs more than NaN columns at n = 1 400); hold-and-confirm second stage rejected (OPEN-14: the confirmation window adds under a paired standard deviation and raises missed faults; the residue is routed to Layer 3 on the workload timescale); `phase_err = min` over tiers retained over split-tier features.

### 9.4 Pre-registered predictions for the first v0.4.1 run (2026-09-16)
The v0.4 run (2026-09-15) was invalid on its smoothing-on half (gate mismatch, storage on the wrong side); its predictions 1 and 3 failed as written on the valid half and are re-registered here.

1. Feeder-only Layer 2, asked to catch everything, misses ≥ 50 % of 48 V faults at a false-trip rate no better than 4 %; scored on 800 V responsibility only, the feeder relay runs at ≤ 0.5 % false trips. The rack node catches > 99 % of 48 V faults at 0.25 ms.
2. The feeder gray zone for 800 V high-Z faults splits on `bus_storage`: ~45 % without, ≥ 60 % with (the v1 regime).
3. Feeder high-Z (800 V) misses: ≤ 2 % without bus storage; with it, rising across C_store terciles to ≥ 10 %.
4. Cadence is learned at both nodes regardless of smoothing (has_period ≥ 0.95); the workload-aware gain persists at both.
5. Feeder + rack: false trips ≤ 3 %, missed 800 V faults ≤ 1 %, missed 48 V faults ≤ 3 %.
6. Smoothing halves the feeder's magnitude cue for 48 V faults (pilot: bolted_48 di_max 0.72 → 0.20), so the feeder's 48 V catch rate is lower with smoothing on than off.

## 10. Dataset schema (HDF5)

```
/session_meta   attrs: model_version, master_seed, git_hash, generated, f_fast, f_slow,
                       workload_version, core_version, rate_configs, n_events, n_rejected_draws
/events/<idx>   attrs: label, seed, background, composite, t_event, n_rejected
  /waveforms    fast_i, fast_v (feeder, 2 MSa/s, fine window), slow_i, slow_v (feeder, 5 kSa/s, whole record)
                rack_fast_i, rack_fast_v, rack_slow_i, rack_slow_v            (v0.4)
                attrs: fast_t0, slow_t0, fs_i, fs_v, fs_i48, fs_v48
    /alt/fs<k>k_b<bits>/  fast_i, fast_v; attrs fast_t0, fs_fast, adc_bits   (OPEN-12 sweep, optional)
  /truth        i_f, i_load, v_c, load_on; v0.4: i_f48, v_Cin, i_pol, load_on48, P_in   (debug/figures only)
  /params       attrs: every system parameter; ev_* event parameters (period, dP_bg, t_ramp_bg, P0, dP, t_ramp,
                R_f, L_f, R_f48, L_f48, arc params, workload, smoothed, T1, T2, dP2, ramp2, sched_tier, jit1, duty1)
```
Per-event seed `master_seed × 1000 + idx`; synthesis noise seed `+ 7919` (feeder), `+ 7919 + 31` (rack), plus a configuration offset for non-default front ends. Feature tables are cached as CSV keyed on a hash of the extractor source; a stale cache is regenerated automatically.

## 11. Open items

| ID | item | status |
|---|---|---|
| OPEN-1 | source current clamp as a derivative limit (no controlled current-limit dynamics) | open |
| OPEN-2 | UVLO recovery restores commanded power without a re-ramp | open |
| OPEN-3 | i/v channel skew and sensor bandwidth mismatch not modelled | open |
| OPEN-4 | bipolar ±400 V topology (OCP Mount Diablo) | open |
| OPEN-5 | *(carried from v0.2 — verify wording against the v0.2 copy)* | open |
| OPEN-6 | bus cannot go negative (freewheel diodes) modelled as a clamp | open |
| OPEN-7 | unidirectional source | open |
| OPEN-8 | statistical resolution: 600 benign events cannot resolve 0.1 % false trip; needs ≥ 5 000 benign | dataset v1-large |
| OPEN-9 | two-tier workload cadence | **closed, v0.3** |
| OPEN-10 | interval-jitter model ≤ 2 % | **closed, v0.3** |
| OPEN-11 | sanity-gate censoring of large segments; Gate-2 99th-percentile row | open |
| OPEN-12 | front-end sensitivity | **closed, v0.3.2**: bits irrelevant (12–16); rate irrelevant for Layer 2 across 100 kSa/s–2 MSa/s at 1 ms; testbed spec 500 kSa/s / 14-bit for margin at 0.25 ms and the arc band; arc-detection column still to be reported per rate |
| OPEN-13 | managed energy storage on C_in | **partially closed, v0.4** (ramp-rate front end); full charge-state controller is OPEN-20 |
| OPEN-14 | hold-and-confirm stage | **closed, rejected, v0.3.3**; residue → Layer 3 on the workload timescale (needs extended post-event record, v1-large) |
| OPEN-15 | flat-background false cadence (1 / 682) | monitor |
| OPEN-16 | short tier-2 periods (20–30 ms, multi-ms ramps) missed ~5 % | stated limit |
| OPEN-17 | iteration periods above 3 s | decide at v1-large |
| OPEN-18 | absolute iteration-edge jitter at rack level unpublished; ≤ 2 % assumed | ask Delta / testbed |
| OPEN-19 | C_out is the rack energy storage: 0.2–5 F at 48 V from 65 J/GPU; the range and the 48 V placement are inferred from public shelf descriptions, not a datasheet | confirm from a shelf datasheet / Delta |
| OPEN-20 | charge-state controller (K_soc, discharge into faults) | v0.5 |
| OPEN-21 | multi-shelf rack with current sharing; v0.4 aggregates six shelves into one | v0.5 |
| OPEN-22 | series-arc ignition/extinction dynamics (Mayr) | open |
| OPEN-23 | rack-node cadence learning and spectral band not tuned for a 48 V bus | v0.4.1 pilot: cadence fine; spectral band unchecked |
| OPEN-24 | the ORing assumption (`i_Lin ≥ 0`): a shelf with a bidirectional input stage could back-feed a bus fault; not in sweep | ask Delta |
| OPEN-25 | Delta BBU placement and behaviour into a bus fault (bus-side `C_store` is the current proxy) | ask Delta |
| OPEN-26 | EDP-tier (tier-2) cadence is soft at the feeder by physics: a slow voltage loop on a farad-class output bank turns a 1 ms burst into a ~10 ms ramp at the bus, so tier-2 edges cannot be phase-located within the decision window at the feeder (scheduled tier-2 p95 ≈ 0.2 there vs ≈ 0.05 at the rack). Tier 1 is unaffected. Report the feeder's tier-2 alibi as weak; the rack node carries the EDP tier. | stated limit |

## 12. Revision log

| version | date | change |
|---|---|---|
| 0.1 | 2026-08-13 | Model specification, four-state core, single-pair figures. |
| 0.2 | 2026-09 | Full taxonomy, sensor synthesis, dataset v0.2 (1 400 events), gates 2–3, series arc, segmented time base. |
| 0.2.2 | 2026-09-08 | No physics change. Feature extractor and studies audited: `phase_err` rebuilt (was bounded at 0.12 by a search-window artifact); two-level edge locator; prominence-based period estimate; `resid_period` demoted; causal spectral filter (load-path arc figure corrected 51 → 38 %); undetected onsets excluded from training; 10-seed repeated CV; gating tested and rejected; V_ref carried into the feature table; C_bus identified as a sensing-floor driver. Dataset v0.2 regenerated from seed on a second machine and Gate 2 reproduced exactly. |
| 0.3 | 2026-09-08 | Workload v1 (§5.1): two-tier cadence sourced in EVIDENCE.md, smoothed/unsmoothed regimes, ≤ 2 % interval jitter; v0.2 workload retained behind a switch. 10 µs history tier with validation (d). Slow stream 5 kSa/s, noise scaled to bandwidth. Dataset v1 (1 400 events). OPEN-9/10 closed. |
| 0.3.1 | 2026-09-09 | Extractor: envelope-based tier-1 search, compute-phase tier-2 search, current-phase tier-2 reference, uncapped harmonic filter. On dataset v1: workload-aware 1.48 / 2.43 / 7.30 % (false trip / missed / high-Z) vs physics-only 2.55 / 4.02 / 12.05; periodic backgrounds 4.22 → 1.24 % missed. Load-path arc figure 66 % (58 % on flat backgrounds; the v0.2 train had buried the arc step). |
| 0.3.2 | 2026-09-09 | OPEN-12 front-end sweep: 16 configurations from one physics pass; rate-aware extractor. Result: bits and rate irrelevant for Layer 2 at 1 ms; gray zone shrinks with bandwidth (conventional detector is noise-limited). |
| 0.3.3 | 2026-09-10 | OPEN-14 hold-and-confirm tested and rejected by pre-registered criterion; damping signal exists (AUC 0.65 at 2.5 ms) but the 50 µs features on the same residue give 0.90; residue routed to Layer 3. |
| **0.4** | **2026-09-15** | **Rack conversion stage (§4.6–§4.11):** input filter and storage C_in (the 1–50 mF sweep transfers from C_bus), ramp-rate charge-management front end (OPEN-13, simplest form), averaged DC-DC with PI voltage loop, inner-loop lag, output current limit and loss model, 48 V bus with POL constant-power load and UVLO, 48 V fault branch. Labels bolted_48, high_z_48. Rack-node observables and node study. The v0.3 "smoothed regime" moved from the workload to the front end, where it acts. Validation (e)–(h) added; (d) extended to the rack node. Baseline single-event result: 48 V faults present at the feeder with zero early-window fault signature (a high-Z 48 V fault is a load step, a bolted one an idle drop); the rack node separates them from benign steps by 10–40× on the same features. v0.3 core retained (`CORE_VERSION = "v0.3"`); dataset v1 reproducible. OPEN-19..23 added. Predictions §9.4 registered before the first run. |

---

| 0.4.1 | 2026-09-16 | **Corrections after the first v0.4 run.** (1) Storage moved to the 48 V output side: C_out 0.2–5 F (65 J/GPU at 50 V), C_in reduced to a small passive input filter behind an ORing stage; bus-side storage (`bus_storage`, C_store 1–50 mF on the bus) added as a separate sweep element for the capacitance-shelf / BBU case. (2) Smoothing re-implemented as a converter-input ramp limiter with the output storage supplying the deficit; the v0.4 current-source front end decoupled the storage from the bus and left it stabilised by C_bus alone (ζ ≈ 0.13 at baseline), which the analytic gate missed — half the v0.4 dataset was generated on a ringing bus and is discarded. (3) Gate 1 gains a numeric decay test on both nodes. (4) Rack-node observable moved to the load-side busbar current i_pol + i_f48, downstream of the storage. (5) Checks (g) and (d) updated. Valid half of the v0.4 run recorded in §4.11. OPEN-24/25 added. Predictions §9.4 re-registered. |

| 0.4.2 | 2026-09-16 | Rack-node slow stream corrected to the load-side current (it was still the converter output; cadence learning at the rack was seeing bursts through the converter's response — 12 of 15 tier-2 scheduled-event failures at the rack fixed on regeneration). Harmonic guard in the tier-2 segment search. Node study gains the "feeder, 800 V duty" row; prediction printout splits the gray zone by bus storage; `run_studies` reports the front-end state and bus-storage terciles. OPEN-26 added. Physics unchanged; datasets generated with 0.4.1 have a wrong rack slow stream and must be regenerated. |

| 0.4.3 | 2026-09-17 | Dataset v1-large support: post-event history tier to 1.2 iterations, `FAULT_MODE = "held"`, per-class counts (`--large`: ≥ 5 000 benign). Simscape cross-check tooling: `simscape_cases.py` exports eight reference runs with `params.json`; `compare_simscape.py` scores check (i); `SIMSCAPE_build_sheet.md` maps every element of the core to a block. Physics unchanged. |

*Sources referenced in this document are collected in EVIDENCE.md. Results for each dataset are in RESULTS.md (v1) and, after the first v0.4 run, RESULTS_v04.md.*
