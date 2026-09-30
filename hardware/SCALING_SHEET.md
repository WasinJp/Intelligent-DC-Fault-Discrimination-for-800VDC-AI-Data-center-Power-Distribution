# SCALING_SHEET.md — from MODEL.md to a low-voltage testbed

**Written:** 2026-10-01, for Prof. Supachai's pre-build review. Numbers: `python hardware/bench_scaling.py 120 48 12` (edit the three arguments to re-scale; the sheet quotes the 120 W / 48 V / 12 V point).
**Purpose of the bench:** answer the judges' third doubt (simulation vs real system) with a specific, testable claim — *we put the bench's own measured parameters into the simulator, trained the relay on simulated bench events, then ran it on the real bench with real sensors, and the decisions matched.* The first two doubts (algorithm speed, processing hardware) are answered separately by the firmware latency test with waveform replay; that test needs no bench.

## 1. The scaling rule

**Time is not scaled.** Every time constant, delay, workload period, ramp, feature window and the sampling rate stay at their physical values, because the relay's features are defined on time windows and the converter and workload time constants in MODEL.md are physical. Only amplitudes and impedances scale:

| quantity | scale | 120 W bench |
|---|---|---|
| voltage | V_b / V_m | feeder 48/800 = 0.06; rack 12/50 = 0.24 |
| current | I_b / I_m | feeder 2.5/165; rack 10/2640 |
| impedance (R, L, ESR, fault resistance) | Z_b / Z_m = (V_b/I_b)/(V_m/I_m) | feeder × 3.96; rack × 63.4 |
| capacitance (stored energy ÷ rated power preserved) | (P_b/P_m)·(V_m/V_b)² | feeder × 0.253; rack × 0.0158 |

Per-unit ratios that the bench must preserve because the relay's features see them: fault resistance vs V/I_rated; fault time constant L_f/(R_f + ESR) vs the sample period; storage energy vs rated power (35 ms); storage ESR step vs bus voltage (1.6 %); converter current limit vs rated (1.4×); source limit vs rated (1.75×); voltage-loop bandwidth vs the storage time constant.

## 2. The bench point: 120 W, 48 V → 12 V

Why 120 W: 10 A on the rack bus is enough for a shunt to read cleanly and for fault currents to reach the model's 12–13× rated without exotic parts; 108 W of continuous load dissipation is a heatsink and a fan, not a water loop; the 48 V supply needs only 2.5 A rated, 4.4 A limit. 300 W was considered and rejected on load dissipation and fault-pulse energy.

Key values (full table in the script output):

| element | model | bench | remarks |
|---|---|---|---|
| feeder L_line / R_line | 5 µH / 5 mΩ | 20 µH / 20 mΩ | a small air-core coil plus the wiring; sweep 4–200 µH |
| "800 V" bus C_bus / ESR | 0.5 mF / 8 mΩ | 126 µF / 32 mΩ | 63 V electrolytic |
| rack input L_in / C_in | 5 µH / 1 mF | 20 µH / 250 µF | plus an ORing Schottky diode at the converter input |
| converter output current limit | 1.4 × rated | 14 A | must hold, not hiccup, for ≥ 10 ms |
| voltage loop f_v / inner τ_i | 100 Hz / 20 µs | same | measured on the converter, not assumed |
| storage bank C_out / ESR | 3.7 F / 0.3 mΩ | 58 mF / 19 mΩ | e.g. 3 × 22 mF 16 V low-ESR; add series resistance to reach the ESR if the bank is too good |
| 48 V fault, bolted | 1 mΩ | 63 mΩ | peak ≈ 130 A = 13 × rated |
| 48 V fault, high-Z | 20 mΩ | 1.27 Ω | sweep 0.3–6 Ω |
| 48 V fault inductance | 0.5 µH | 32 µH | **must be added as a coil** (see §3.4) |
| 800 V fault, high-Z | 5 Ω | 20 Ω | across the 48 V bus, current capped by the source limit |
| POL UVLO | 40 V, 100 µs, 2 V hyst. | 9.6 V, 100 µs, 0.48 V | implemented by the load-control MCU |
| source current limit | 1.75 × rated | 4.4 A | lab supply in constant-current mode |

Bolted 800 V-side faults are **not** done on the bench: they are Layer-1 territory (analog thresholds), they would abuse the lab supply, and the feeder relay's job in this project is the high-impedance class.

## 3. What does not transfer, and what we do about it

1. **Constant-power load.** The model's GPUs are a constant-power load behind point-of-load converters. The bench load is a bank of switched resistors: cheaper, safer, and its current *falls* when the bus sags instead of rising. Consequence: at the 1.5 % sag of a high-Z fault the difference is 1.5 % of 0.5 p.u., negligible next to the 1–13 p.u. fault current on the rack node; in a bolted fault the load current is 0.5 p.u. against 13 p.u. So the physics of laundering is unchanged, but the simulator must model what is built: **decision requested — add a `load_model = "resistive"` option to the core for the bench dataset** (a few lines in `_derivs`; the data-center datasets keep the constant-power load).
2. **Converter-input smoothing.** The ramp limiter of GB300-class shelves is not implementable in a plain buck. The bench runs with `smooth_on = 0`; that is the case that is *harder* for the feeder (larger step), so it is the conservative one to demonstrate.
3. **The source.** A lab supply replaces the droop-controlled 800 V source. Its output impedance and constant-current transition are measured (step test) and put into the simulator as R_droop and τ_c. It must hold constant current at 4.4 A during a fault, not shut down; that is a supply setting, verified before the first fault run.
4. **Fault inductance.** Scaled L_f48 is 6–130 µH; bench wiring is about 0.5 µH. Without an added coil the bench fault front would be *faster than anything in the training set*, and the relay would be tested outside its distribution. A 30 µH air-core coil in the fault branch, plus one of 10 µH and 100 µH for the sweep, puts it in range. (This is also the judges' di/dt point: the front on the bench will be sub-10 µs, and the scope that checks it needs ≥ 10 MHz.)
5. **Workload ramps.** The model's power ramps (0.5–20 ms) are produced by switching five binary-weighted load branches in sequence from the load-control MCU; a ramp becomes a 5-step staircase. The relay's early-window features see the first step; the bench dataset uses the same staircase profile so simulation and bench agree by construction.
6. **Sensing chain.** Rack node: 1 mΩ shunt, gain 20, full scale 13 × rated at 2.6 V, rated current = 4 000 LSB of the H7's 16-bit ADC. Feeder node: 10 mΩ shunt, gain 50, full scale 2 × rated (the source limit is 1.75 ×). Anti-alias second-order at 150 kHz for 500 kSa/s. Common ground, no isolation on the bench (the product needs it; say so). Voltage: dividers to 2.4 V nominal.
7. **Processor.** STM32H7 internal 16-bit ADC at 500 kSa/s per channel via DMA; the external 14-bit SAR ADC of the product design is not needed for the prototype (OPEN-12: bits and rate are not limiting).

## 4. Converter: buy or build, decided by a pre-registered test

Both routes end in a converter whose control is *measured* and put into the simulator; the difference is risk and schedule.

- **Buy:** a 48 → 12 V, ≥ 150 W synchronous buck module (two ordered now, < US$25 each). Pass criteria on the bench, measured before any relay test: (a) into a 14 A overload it holds a current limit for ≥ 10 ms without hiccup or shutdown; (b) a 50 % load step gives a clean step response from which f_v and τ_i can be fitted (the simulator's check (f) then must reproduce the measured trace within 5 %); (c) efficiency at 20 / 50 / 100 % load fits the two-term loss model.
- **Build (if the module fails (a) or (b)):** a synchronous buck around an analog peak-current-mode controller IC with external compensation and a cycle-by-cycle current limit that does not hiccup. Peak-current-mode *is* the model's cascade (outer voltage error amplifier, inner current loop, clamp), so it maps directly and its compensation sets f_v where we want it. A digitally controlled STM32 buck is the better portfolio project but is a second firmware effort competing with the relay firmware; it is deferred to after November.

## 5. Pre-build verification (what the professor reviews before parts are soldered)

1. This sheet and the schematic (hardware/schematic, to follow).
2. **Bench dataset from paper values:** the scaled parameters go into `PARAMS_BASELINE` as `PARAMS_BENCH`; a small dataset (≈ 300 benign, 6 × 50 faults) is generated with the resistive-load option; the report shows (i) laundering at bench scale: feeder and rack traces for a high-Z 48 V fault, (ii) the fronts at both nodes (90 % times, peak di/dt) against the sensing chain and the ADC, (iii) the relay trained on this set: false trips / missed on cross-validation. Pre-registered expectation: the same picture as Figure 5 at bench scale, rack 90 % time within a factor of 2 of 0.06 ms, feeder 90 % time within a factor of 2 of 1.4 ms.
3. **Safety sheet** (§7) signed off.
4. After assembly, **measure every element** (LCR/ESR meter for C, ESR, L; four-wire for shunts and wiring; converter step response; supply step response) and regenerate the bench dataset from measured values. The relay used on the bench is trained on *that* set.

## 6. Bench test plan and acceptance (pre-registered)

Automated by the load-control MCU; every run recorded by both nodes (raw 500 kSa/s streams to the PC over USB) and by the scope.
- **Benign:** 200 workload events — steps of 10–80 % of rating, staircase ramps 0.5–20 ms, idle drops, two-tier cadence with periods 0.3–3 s.
- **Faults:** 60 rack-side (20 each at 63 mΩ, 0.3 Ω, 1.3 Ω; L 10 / 30 / 100 µH), 20 feeder-side high-Z (20 Ω and 40 Ω), pulse-limited to 5 ms by hardware.
- **Acceptance:** (1) for every feature in `features.py`, the bench value lies inside the 2.5–97.5 % range of the simulated bench dataset for the same event class in ≥ 90 % of events; (2) the relay trained on the simulated bench set gives 0 false trips in 200 benign events and ≤ 3 misses in 80 faults, decisions at 0.25 ms; (3) onset-to-trip latency on the H7, measured on the scope, ≤ 250 µs in every fault run.
- If (1) fails on a feature, the feature and the reason are reported; if (2) fails, the relay is retrained on recorded bench events and both results are reported. Nothing is tuned after the fact without saying so.

## 7. Safety

- Stored energy: 4.2 J in the storage bank, 0.15 J on the bus cap. Not a shock hazard; a burn and spatter hazard at the fault switch.
- Fault pulse: ≤ 130 A for ≤ 5 ms, limited by a **hardware one-shot** (555 or timer IC) between the MCU and the fault-MOSFET gate driver, so no firmware fault can hold the switch closed; the fault resistor is rated for the 5 J pulse with margin (parallel wirewounds on a heatsink).
- Fusing: fast fuse on the 48 V input (5 A); the supply's own current limit at 4.4 A; an emergency-stop contactor in the 48 V feed.
- Continuous dissipation: 108 W in the load bank on a fan-cooled heatsink; thermal switch on the heatsink cuts the load if > 90 °C.
- Electrolytics: 16 V rated on a 12 V bus, reverse-polarity protected; the ORing diode prevents back-feed.
- Fault tests only with a second person present and the professor's sign-off on this sheet.

## 8. Schedule (final on 14 Nov)

| dates | work |
|---|---|
| 1–7 Oct | this sheet, schematic, parts order, converter modules ordered; bench dataset from paper values; FIRMWARE_SPEC.md handed to Claude Code (host-side feature extractor and model export, no hardware needed) |
| 8–17 Oct | professor's review of sheet + schematic + firmware design; Nucleo boards arrive: ADC/DMA sampling and DAC replay; sensing front ends on perfboard |
| 18–31 Oct | bench assembly; converter characterisation and buy/build decision; element measurements; bench dataset from measured values; relay retrained; latency test with replay (doubts 1 and 2 closed) |
| 1–8 Nov | bench recordings (§6); acceptance scored; one table: simulation vs bench |
| 9–14 Nov | video, live demo, rehearsal |

Fallback: if the bench slips, the replay latency test plus the bench-scale simulation still answers doubts 1 and 2 with measurements, and doubt 3 partially.

## 9. Questions for the professor

1. `load_model = "resistive"` in the core for the bench dataset: agreed?
2. Lab equipment: 48 V supply (≥ 5 A, constant-current mode), scope bandwidth, differential or current probe ≥ 10 MHz, LCR/ESR meter, electronic load with dynamic mode (would replace the resistor bank).
3. Supervision and space for fault-injection tests; who signs off §7.
4. Buy-vs-build rule in §4: acceptable, or does he prefer the built converter regardless?
