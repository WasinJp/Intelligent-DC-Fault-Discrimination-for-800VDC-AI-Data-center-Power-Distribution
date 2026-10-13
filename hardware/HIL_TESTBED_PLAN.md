# HIL_TESTBED_PLAN.md — Prof. Supachai's advice, what we have settled, and the firmware and hardware work that follows

**Written:** 2026-10-08. **For:** the DeltaCup 2026 final on 2026-11-14. **Scope decision:** 2026-10-17 (§2.2).
**Inputs:** two conversations with Prof. Supachai; TESTBED_HIL_REVIEW.md (2026-10-08); the LTspice checks in `hardware/ltspice/`; the revised SCHEMATIC_DESIGN.md and SCALING_SHEET.md (2026-10-08); the repo at commit a48e3b9 (firmware M1–M7, `firmware/docs/TIMING.md`, `DEVIATIONS.md`, the reference fixtures).
**Rules that still apply:** MODEL.md is the single source of truth; changes to the generator or physics core need Wasin's agreement; validation before generation; predictions are written down before a run.

Every item carries a tag:

| tag | meaning |
|---|---|
| **DECIDED** | agreed; build on it |
| **PROPOSED** | recommended here; needs Wasin's OK before it is built |
| **OPEN** | needs an answer from the professor, Ajarn Pichai, or a measurement |
| **WITHDRAWN** | an earlier suggestion that turned out wrong; listed so nobody revives it |

---

## 1. What Prof. Supachai advised

1. **Make the testbed a real-time Hardware-in-the-Loop (HIL) setup.** Showing real-time response on real hardware is the main selling point for the judges.
2. **Use MATLAB/Simulink with Simscape Electrical for the high-voltage system model**, not LTspice; LTspice is for low-power circuits.
3. **Use the lab's tabletop HIL box.** It runs the Simulink model and outputs scaled analog voltages into our hardware. Ajarn Pichai also has a high-voltage HIL; coordinate with him so the firmware and interface modules are ready.
4. **At least two monitoring nodes**, before and after the converter, because their signals behave differently.
5. **An interactive dashboard**: bus status across the network, click a point to see its live data, trigger a simulated fault and watch the system respond.
6. **Computation is not the bottleneck.** The math is light; he does not expect the timing target to be a problem.
7. **Resources:** many STM32 boards, lab equipment, and a room for the build. He agreed a real hardware testbed is needed to convince the judges, and he will review the schematic, the firmware design and the pre-build verification.

What is known about the HIL box so far: model unknown ("tabletop"); supports Simscape Electrical; solver type and time step **not yet asked**; live fault trigger from a PC probably; can go to the venue probably.

---

## 2. What we have settled from it

### 2.1 What each part of the testbed proves — DECIDED

The judges raised three doubts after the semi-final (algorithm speed, real processing hardware, "is it only a simulation?") and advised a high-bandwidth current probe for the fault current.

| | HIL + nodes | Power bench (120 W) |
|---|---|---|
| Algorithm speed | **closed loop**: the model's breaker opens on our TRIP; the HIL timestamps fault inception → trip | yes, scope-measured |
| Real processing hardware | yes, the STM32H7 nodes | yes |
| "Only a simulation?" | **no**: the waveforms are still computed | **only here**: real sensors, real converter, real faults |
| High-bandwidth probe remark | no | yes: differential probe across the rack shunt |
| Full-scale system (800 V / 132 kW, constant-power load, ramp limiter on, bolted 800 V faults) | **yes** | no |
| Live "trigger a fault" demo at the venue | **yes**: safe and repeatable | no (≈ 100 A pulses in a hall) |

The HIL is added to the design; it does not replace the bench. Its plug-in point already exists: the node's replay inputs (Sheet 2 JP1/JP2).

The story for the judges: *the HIL shows the relay protecting the full 800 V design in closed loop, with trip time measured by lab equipment; the bench shows the same relay, unchanged, working on real sensors and real faults at 120 W.*

How we answer the plant-model question: the model is validated by an independent Simscape implementation (check (i), 8 of 8 PASS on 2026-09-18). The hardware, firmware and timing are real.

### 2.2 Scope — OPEN, decide on 2026-10-17

After the professor's review and the HIL time-step answer, choose one:

- **A. HIL + nodes + dashboard only.** Fastest; doubt 3 answered only by the Simscape cross-check.
- **B. HIL primary + reduced bench (recommended).** Keep the power path, the converter, both nodes and the rack breaker. Run **rack-side faults only, one coil value**.
  - Drop the feeder fault injector and the feeder breaker Q_fb. The feeder node's TRIP drives an LED and the HIL only.
  - This removes 3 of the 12 vulnerable parts (Q_fb drive, Q_fb rating, Q_f8).
  - It still shows the core result: at the feeder, a 48 V fault looks like a load step (MODEL.md §4.11).
- **C. Full bench + HIL.** Most convincing, highest schedule risk.

### 2.3 The timing claim — DECIDED wording, PROPOSED predictions

**Wording (from FIRMWARE_SPEC §7.4; use it everywhere):** *"The decision uses 0.25 ms of data after onset; the trip pin follows within ≤ 80 µs."* Onset to trip is therefore ≤ 250 + 16 + 80 = 346 µs worst case.

SCALING_SHEET acceptance (3), "onset-to-trip ≤ 250 µs", and the same phrase in TESTBED_HIL_REVIEW §2.8 contradict this. The relay cannot trip before its 250 µs of data is in. **Correct both.**

**Pre-registered prediction for the HIL** (fault inception → trip, the HIL's own measurement). Computed from the firmware reference fixtures (`firmware/host/tests/fixtures/reference_features.csv`, W = 0.25 ms, 120 events per class), with the 16 µs block and 80 µs processing added at their worst case:

| fault class (node in charge) | inception → onset, median / p95 | inception → trip, median / p95 |
|---|---|---|
| bolted / resistive 800 V (feeder) | 6 / 11–13 µs | ≈ 0.35 / 0.36 ms |
| high-Z 800 V (feeder) | 14 / 127 µs | ≈ 0.36 / 0.47 ms |
| bolted / high-Z 48 V (rack) | 4–5 / 10–11 µs | ≈ 0.35 / 0.36 ms |

Add the HIL digital input's sampling period, up to one HIL step. Cross-check on the scope: SYNC (inception), ONSET pin, TRIP pin.

**Bolted faults are Layer 1.** The firmware already has Layer-1 thresholds (FIRMWARE_SPEC §7.1, off by default). On the HIL, set them from the v1-large Gate-2 benign envelope; that trips bolted faults in microseconds. The 0.25 ms ML decision is for the gray-zone faults (high-Z 800 V and 48 V), which do not collapse the bus.

Confirm with the professor that he sized the computation against 0.25 ms, not 2.5 ms.

### 2.4 Two nodes — DECIDED (backed by our own numbers)

From `firmware/docs/TIMING.md`, decisions at 0.25 ms on 36 000 events, held-out calibration at a 0.1 % false-trip budget:

| relay | missed 48 V faults | missed high-Z 800 V |
|---|---|---|
| feeder only | ≈ 70 % | ≈ 17 % |
| rack only | ≈ 0.3 % | ≈ 74 % |
| feeder + rack | ≈ 0.5 % | ≈ 2.5 % |

Each node is blind to the other side's faults; together they cover both. This is the quantitative form of the professor's point 4.

### 2.5 The model on the HIL — DECIDED approach, details PROPOSED

- **What runs:** the full-scale data-center model, MODEL.md v0.4.4 (800 V, 132 kW), not the 120 W scaled one. Start from the existing `simscape/dcsim_shelf.slx`. It already advances the converter controller as an explicit discrete update (`ctrl_d`), which a fixed-step real-time target needs (MODEL.md §4.8: implicit solvers break the anti-windup rule).
- **Reference to check against:** check (i)'s eight cases, scored by `scripts/compare_simscape.py`. **Not** the old `run_demo.py` numbers (0.079 A/µs, 8.5 V, 397 A/µs). That script is not in the repo, and 397 A/µs is the hidden fault-branch current (800 V across 2 µH), which no node observes.
- **Stiff fault branch:** at a coarse fixed step, use the MODEL.md 0.4.4 quasi-static rule, already validated by check (j). Do not use Tustin; it rings on a stiff mode.
- **Added to the model for the HIL:**
  - the **two-tier workload generator** (§5.1), running continuously. `phase_err` needs ≈ 2.5 iterations of cadence history (up to 7.6 s) before a benign edge has its alibi.
  - a **breaker element** (SSCB) per node, opened by a HIL digital input. **PROPOSED:** a MODEL.md entry for it (opening time, what happens after), since the core has no breaker today.
  - a **fault-scenario block**: location, R_f, L_f, inception time, selectable at run time. This is the dashboard's fault menu.
  - **output scaling and saturation** per §4.2, plus a noise source if the measured HIL noise is below the training range (§3.5).
- **New validation check — PROPOSED, check (k):** the relay features at the HIL step, through the HIL front end, against the 50 ns reference on the same events (`scripts/compare_feature_tables.py`). It must pass before any HIL dataset or result is quoted.

### 2.6 One firmware, two modes — DECIDED

The HIL outputs are scaled so the node sees the **same per-unit full scale as on the bench** (table in §4.2). The firmware converts codes with `gain_i/v` and `offset_i/v` from settings, so HIL mode and bench mode differ only in settings and a jumper.

All four observables are non-negative in MODEL.md (i_L ≥ 0 by OPEN-7, i_rack ≥ 0, both voltages ≥ 0). Unipolar 0–3.3 V scaling into the existing chain is therefore correct.

### 2.7 Fail-safe trip — DECIDED (revised 2026-10-08)

Keep the built firmware as it is: **TRIP active high** (`firmware/node/board.h`, PF13). On the bench, put a **pull-up** on each breaker driver input, powered from the driver board, and use an **inverting** isolated driver. When a node is unpowered or in reset, its pin floats, the pull-up wins, and the breaker opens. No firmware change is needed. On the HIL, the model's breaker opens while its digital input is high.

### 2.8 The dataset for HIL mode — PROPOSED (needs Wasin's OK; MODEL.md 0.4.5)

The physics is unchanged; only the front end differs. Add a **HIL front-end option** to the synthesis layer, alongside the OPEN-12 alternate front ends, generated from the same physics pass with no regeneration of v1-large. It contains:
- zero-order hold at the HIL step;
- DAC quantisation at the HIL's resolution and output range;
- the node's real 4th-order 100 kHz filter (designed values now, values fitted to the scope step response once built);
- the measured noise floor.

Store it in `session_meta` so a HIL dataset stays reproducible from (MODEL.md version, seed). The same mechanism carries the bench front end. Retrain the relay on it for HIL mode.

This is not a `PARAMS_HIL` parameter set (the name in TESTBED_HIL_REVIEW). The parameters are the data-center model's.

### 2.9 Withdrawn — WITHDRAWN

| suggestion | why withdrawn |
|---|---|
| port `model.py` / check against `run_demo.py` numbers | outdated model; check (i) is the reference (§2.5) |
| ±10 V → 0–3.3 V level shifter on every channel | all observables are unipolar; per-unit scaling into the existing chain is better (§2.6) |
| change the firmware to "BRK high = closed" | the pull-up + inverting driver gets fail-safe with the built firmware (§2.7) |
| "the power stage goes away with HIL" | the bench is the only answer to doubt 3 (§2.1) |
| "onset-to-trip ≤ 250 µs" | impossible by construction (§2.3) |

LTspice was never used for the high-voltage system; it stays the right tool for the bench circuits and the node front end.

---

## 3. Firmware — status and work for analysis

### 3.1 Where it stands (`firmware/docs/MILESTONES.md`)

| milestone | status | key result |
|---|---|---|
| M1 feature extractor | done | 6 480 rows: onset identical, features within 1.5 × 10⁻¹⁰ relative of Python |
| M2 model inference | done | scores bit-identical to sklearn on 9 720 rows |
| M3 node streaming | built, untested on target | host preview: identical decisions 100 %; DWT timing not yet measured |
| M4 DAC replay latency | tools exist | needs boards and scope |
| M5 cadence learner | host done, target built, untested | matches Python to 10⁻¹³ |
| M6 CAN-FD + record upload | built, untested | round trips pass in unit tests |
| M7 bench control | built, untested | profile, faults, UVLO, SYNC, replay, console |

The firmware is not the critical path. The HIL model and the node front end are.

### 3.2 Items to analyze

| # | item | why it matters | tag |
|---|---|---|---|
| F1 | **M3 on the board: DWT timing**, window close → trip pin, target ≤ 80 µs p99 | the number behind the timing claim; it also decides the tree count (TIMING.md §2: 100 trees is a free improvement over `auto`; 300 only if it fits) | OPEN, first job when the boards arrive |
| F2 | **Two-node decision over CAN adds 150–250 µs** (DEVIATIONS #13: the rack's 15 features need three 64-byte CAN-FD frames) | the two-node relay is the accurate one (§2.4), but this delay would push its trip to ≈ 0.5–0.6 ms | OPEN; options below |
| F3 | **Cadence relearn cost** (DEVIATIONS #14): projected 70–150 ms per relearn on the M7 against a 40 ms budget | if confirmed, relearn every 1 s; check that `phase_err` holds up | OPEN, measure on M3/M5 |
| F4 | **Onset detector** (DEVIATIONS #1, frozen baseline) verified only on the host | repeat with replayed and HIL waveforms; the HIL is the first source of continuous, long quiet stretches | OPEN |
| F5 | **HIL-mode settings**: gain/offset per §4.2, Layer-1 thresholds (§2.3), SYNC from a HIL digital output | settings only, no code change expected | PROPOSED |
| F6 | **Retrain** on the HIL front end (§2.8) and, later, the measured bench front end | the relay must have seen the filter and noise it will meet | PROPOSED, after §2.8 is approved |
| F7 | **Telemetry stream for the dashboard**: v, i, state and last decision at 20–50 Hz | not in the firmware today (only `status` on the console and event records over USB); needs a small spec | PROPOSED |
| F8 | **Bench control as demo controller**: a dashboard fault command → GPIO into a HIL digital input, plus SYNC | makes the fault button work even if the HIL has no PC interface | PROPOSED |

**F2 options, to compare on the existing tables before choosing:**
- **(a) Node-separable model:** train the two-node model so each tree uses features from one node only (`interaction_cst` in sklearn's HistGradientBoosting). The rack then sends three partial class scores in the existing 16-byte summary frame, within 20 µs. This changes training, not the generator or the features. Measure the accuracy cost against the 30-feature model in TIMING.md.
- **(b) Fewer rack features over CAN:** the most important few, as float64. Fewer frames, some accuracy cost.
- **(c) Accept the delay** for the two-node path, and let each node trip its own zone immediately with its single-node model. Report both latencies.

---

## 4. Hardware — status and work for analysis

### 4.1 Node board (used in both modes)

| # | item | detail | tag |
|---|---|---|---|
| H1 | **Anti-alias filter values** | C1 1.5 nF, C2 1.3 nF, C3 3.9 nF, C4 560 pF, R 1.1 kΩ, low-Q stage first. The drawn values gave −3 dB at 52.7 kHz; these give 100.6 kHz and −48 dB at 400 kHz (LTspice D) | DECIDED |
| H2 | **Replay/HIL input protection** | A series 1 kΩ in front of the filter adds to its 1.1 kΩ input resistor and moves −3 dB to **76 kHz**. Put 1 kΩ + clamp in front of *both* sources (INA240 and SMA, before the jumper) and cut the filter's first resistor to 100 Ω, or add a buffer. First line of protection: saturate each HIL output to 0–3.3 V in the model; ±10 V through the clamp pushes ≈ 6 mA into the Nucleo's 3.3 V rail | PROPOSED |
| H3 | **TRIP out** to the breaker driver and a HIL digital input | buffer per the HIL input's voltage threshold (3.3 V logic direct; 24 V industrial needs an interface) | OPEN (needs the HIL input threshold) |
| H4 | **SYNC in** from a HIL digital output | check the level against PF12, level-shift if needed | OPEN |
| H5 | **Connector panel** per node | BNC/SMA: i in, v in, TRIP out, SYNC in, ONSET test point | PROPOSED |
| H6 | **Grounding** | one point between the HIL analog ground and the node ground; USB isolator on the dashboard link if a ground loop shows on the quiet-bus noise | PROPOSED |
| H7 | **INA240A2** for the feeder (×50) | A3 is ×100 | DECIDED |
| H8 | **Keep the H743 for the nodes** | the firmware is built for it; lab boards (F4/G4) for prototyping. If a node must be 12-bit, test that first as a front-end option: OPEN-12 found bits irrelevant at the synthesis full scale, but the rack node's 13 × rated full scale costs ≈ 2 bits | DECIDED / OPEN for 12-bit |

### 4.2 HIL interface — PROPOSED scaling

Minimum I/O for two nodes: **4 analog outputs** (i and v per node), **3 digital inputs** (two TRIPs + the fault command), **1 digital output** (SYNC).

Per-unit full scales equal to the bench node's:

| signal | per-unit base (model) | volts per p.u. at the node | 3.3 V = | HIL output gain |
|---|---|---|---|---|
| feeder current i_L | 165 A (132 kW / 800 V) | 1.25 V | 2.64 p.u. | 7.58 mV/A |
| feeder voltage v_bus | 800 V | 2.28 V | 1.45 p.u. | 2.85 mV/V |
| rack current i_rack | 2 640 A (132 kW / 50 V) | 0.20 V | 16.5 p.u. | 75.8 µV/A |
| rack voltage v_out | 50 V | 2.28 V | 1.45 p.u. | 45.6 mV/V |

**Resolution — OPEN:** a ±10 V, 16-bit output has a 0.31 mV step. That is ≈ 650 steps per p.u. on the rack current, against ≈ 4 000 at the node's ADC, so the HIL's output step, not the ADC, limits the rack current channel. It is near the low end of the training noise range. Ask whether the output range can be set to 0–5 V, and model the step in the HIL front end (§2.8).

### 4.3 Power bench — reduced scope under option B

Keep (with the 2026-10-08 fixes): power path, converter (six acceptance criteria), storage bank, rack shunt, **rack breaker Q_brk**, load bank, rack fault injector with one coil.

The vulnerable parts that remain, from the Bench Risk Register:

| part | fix in the design | tag |
|---|---|---|
| Q_brk high-side gate drive | isolated driver referenced to its source + isolated DC-DC; **inverting, pull-up input** (§2.7) | DECIDED |
| Fault coil energy | freewheel diode across R_f48 + coil, at Q_f48's drain | DECIDED |
| Q_brk turn-off spike | SMCJ18A TVS | DECIDED |
| Fault one-shot | 74HC221 non-retriggerable, arm key on CLR | DECIDED |
| Gate-driver supply | separate 12 V adapter, not the bench bus | DECIDED |
| K1 hot plug | power-up order (K1 before the supply output) or 10 Ω precharge | DECIDED |
| F2 placement | converter output, outside the fault loop | DECIDED |
| Coil DCR in R_f48 | resistor = target − measured DCR; heavy wire for 30 / 100 µH | DECIDED |
| Vendor-model rerun of LTspice A | IRFP7430 model; peak Vds and avalanche energy against the datasheet | OPEN, before ordering |

Dropped under option B: Q_fb, its TVS and isolated driver; the feeder fault injector (Q_f8, 22 Ω, 8 µH, SS310); one-shot A. Keep the supply output floating anyway; it avoids earth loops through the scope and PC.

### 4.4 Dashboard — PROPOSED architecture

| source | provides |
|---|---|
| Nodes (USB) | telemetry at 20–50 Hz (F7); event records (0.2 ms before, 5 ms after) on each trip |
| HIL host | every internal model signal, for the clickable points; breaker states (external mode or UDP, whatever the box supports) |
| Demo controller (bench-control Nucleo) | fault command → HIL digital input; SYNC |

Views:
- **Single-line diagram:** source → feeder → 800 V bus → converter → 48 V bus → racks. Coloured by state; every point clickable.
- **Measured vs simulated:** values at the two node points are measured by our hardware; all other points are model values. Label which is which; the judges will ask.
- **Event view:** both nodes' waveforms aligned on SYNC, with onset, decision, TRIP and the HIL-measured latency in µs.
- **Replay mode:** plays recorded events if the hardware fails at the venue.

---

## 5. Open questions

**For Ajarn Pichai (a photo of the HIL's front panel and I/O labels answers most of them):**
1. Model name; solver type (CPU or FPGA) and minimum time step. The requirement from our own rate study (OPEN-12):
   - ≤ 2 µs step and output update keeps the 0.25 ms claim;
   - ≤ 10 µs is enough only for a 1 ms decision;
   - 20–50 µs (typical CPU targets) means the rack-node features will not transfer.
2. Analog outputs: how many, range (can it be 0–5 V?), resolution, update rate, **noise floor**.
3. Digital inputs/outputs: how many, **voltage threshold**, how often the inputs are sampled.
4. MATLAB version and toolboxes; whether the FPGA path runs Simscape Electrical models directly or needs conversion.
5. Live control from a PC (UDP or external mode): fault trigger, streaming internal signals.
6. Can the box go to the venue on 2026-11-14; who transports it; sign-out process.

**For Prof. Supachai:**
1. Scope A, B or C (§2.2).
2. The timing claim in §2.3: did he size it against 0.25 ms?
3. The schematic fixes (Q_brk drive and its supply, freewheel diode, one-shot, power-up order).
4. The earlier scaling-sheet questions: resistive load model for the bench dataset, lab equipment, supervision for fault tests, converter buy-vs-build rule.

**For Wasin (approvals that unblock work):**
1. MODEL.md 0.4.5: the HIL/bench front-end option (§2.8) and the breaker element (§2.5).
2. New check (k) (§2.5).
3. Which F2 option to analyze first (§3.2).

---

## 6. Order of work to the scope decision (2026-10-17)

1. Send the §5 questions; get the HIL facts. Everything about the HIL front end depends on the time step and output specs.
2. Rerun LTspice A with the vendor IRFP7430 model; order parts for the option-B bench and the node front ends.
3. Put `dcsim_shelf.slx` on a fixed-step solver; rescore against check (i); add check (k).
4. Nucleo boards arrive: M3 on target (F1), then M5 timing (F3).
5. 2026-10-17: scope decision with the professor; then HIL bring-up (first closed-loop latency number), dashboard v1, retraining.

---

## 7. Addendum 2026-10-08 (evening) — circuit review rev 2, status of the tags above

Wasin agreed to the order of work of §6 and to the circuit fixes of CIRCUIT_REVIEW_2026-10-08.md. Changes to the tags above:

- **§2.7 fail-safe — DECIDED, wording corrected:** 10 kΩ **pull-up** on the isolated driver's inverting input (rev-1 Sheet 3 said pull-down, which closes the breaker on a dead node). Firmware stays TRIP-active-high.
- **§4.3 Bench Risk Register — all rows DECIDED and drawn** (Sheets 1–3 rev 2, SCHEMATIC_DESIGN rev 2 §0). Additions: the feeder breaker (option C) moves to the **high side** with the same isolated driver, so the supply (−) is bonded to the star; **74HC221** (not '123) with the arm key on CLR; 100 V parts everywhere on the 48 V side, no logic-level requirement; ESR ballast pulse-rated; 47 Ω + 1 nF at the ADC pins; converter buy criteria (d) start-up into 66 mF, (e) pre-bias safe.
- **H2 — DECIDED:** 1 kΩ + BAT54S clamp + unity buffer (U2B / U4A) before the filter on both channels, ahead of JP1 / JP2; the filter's R stays 1.1 kΩ (f₀ unchanged). HIL 0–10 V outputs through a 3:1 pad on the HIL adapter panel (resolution 3× better than asking the box for 0–3.3 V).
- **H1 — DECIDED and verified:** rev-2 values give Q 0.537 / 1.319, −3 dB 100.6 kHz, −48.0 dB at 400 kHz (hand calculation, LTspice D, ngspice agree).
- **§4.3 "Vendor-model rerun of LTspice A" — still OPEN:** rerun with the IRFP7430 vendor model, with and without D_fw; also C with the supply ramping after K1.
- **§5.1 step-size tiers — WITHDRAWN as a requirement to state to Ajarn Pichai.** They were transplanted from OPEN-12 (sensor sample rate with a matched anti-alias), not from a ZOH-into-500 kSa/s study. Replaced by the front-end sweep (check (k) generalised: ZOH at {1, 2, 5, 10, 20, 50} µs + DAC quantisation + the real filter + noise + full scale, scored on the relay's features and operating point), run before the box's step is known; the plant-side question (fixed-step local solver at 10 / 20 / 50 µs rescored against check (i)) is separate and run on the desktop first.
- **Fallback — DECIDED:** bench_control DAC replay + a post-trip waveform switch on TRIP = the closed-loop demo without the HIL box; the HIL is built on top of it.
- **Critical path — DECIDED:** a NUCLEO-H743ZI2 / H723ZG in hand (M3 §1–§3 the same day). F4 / G4 lab boards cannot run the node image.
- **Professor package:** `IDCFC_hardware_review_2026-10-08.docx` (EN + Thai summaries) with the block diagram rev 2 and Sheets 1–3 rev 2; the ask list is its §5.
