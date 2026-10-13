# IDCFC Testbed: Hardware So Far, Prof. Supachai's Advice, and What Changes with the HIL

**Date:** 2026-10-08 · **For:** DeltaCup 2026 final (14 Nov) · **Inputs:** SCALING_SHEET.md, SCHEMATIC_DESIGN.md, bench_scaling.py output (120 W point), block diagram + Sheets 1–3, notes from two conversations with Prof. Supachai

---

# Part 1: What we have designed and found so far

## 1.1 Why the bench exists

The judges raised three doubts after the semi-final:

| # | Doubt | How the current plan answers it |
|---|---|---|
| 1 | Is the algorithm fast enough? | Firmware latency test: simulated waveforms are replayed through a DAC into the node, and onset-to-trip is measured on a scope. Needs no power bench. |
| 2 | Can it run on real processing hardware? | Same test, running on an STM32H7. |
| 3 | Is this only a simulation? | A low-voltage **power bench** with real sensors and real faults. The bench's measured parameters go into the simulator, the relay is trained on simulated bench events, then run on the real bench. The claim is that **the decisions match.** |

## 1.2 The scaling rule (SCALING_SHEET §1)

- **Time is not scaled.** Every time constant, workload period, feature window and the sampling rate stay physical, because the relay's features are defined on time windows.
- **Only amplitudes and impedances scale:**
  - voltage by V_b/V_m
  - current by I_b/I_m
  - impedance by Z_b/Z_m
  - capacitance so that stored energy ÷ rated power stays the same (35 ms for the storage bank)

**Bench point: 120 W, "800 V" → 48 V, "48 V" → 12 V.** The model's 132 kW rack becomes a 120 W bench.

| Element | Model | Bench | Remark |
|---|---|---|---|
| Feeder L_line / R_line | 5 µH / 5 mΩ | 20 µH / 20 mΩ | air-core coil + wiring |
| "800 V" bus C_bus / ESR | 0.5 mF / 8 mΩ | 126 µF / 32 mΩ | 150 µF part + ESR ballast |
| Rack input L_in / C_in | 5 µH / 1 mF | 20 µH / 250 µF | + ORing Schottky |
| Converter current limit | 1.4 × rated | 14 A | must hold, not hiccup, ≥ 10 ms |
| Converter loops f_v / τ_i | 100 Hz / 20 µs | same | measured, not assumed |
| Storage bank C_out / ESR | 3.7 F / 0.3 mΩ | 58 mF / 19 mΩ | 3 × 22 mF + ballast |
| 48 V bolted fault | 1 mΩ | 63 mΩ | peak ≈ 130 A = 13 × rated |
| 48 V high-Z fault | 20 mΩ | 1.27 Ω | sweep 0.3–6 Ω |
| 48 V fault inductance | 0.5 µH | 32 µH | **must be an added coil** (wiring ≈ 0.5 µH is far below the range) |
| 800 V high-Z fault | 5 Ω | 20 Ω | current capped by the supply's CC limit |
| POL UVLO | 40 V / 100 µs | 9.6 V / 100 µs | emulated by the bench-control MCU |
| Source current limit | 1.75 × rated | 4.4 A | lab supply in constant-current mode |

## 1.3 Power bench (Sheet 1)

The power path, left to right:

1. 48 V lab supply (CC 4.4 A)
2. E-stop contactor, then a 5 A fast fuse
3. Feeder emulation: L_line + R_line
4. **Feeder shunt** 10 mΩ, read by the feeder node
5. **"800 V bus" node**: C_bus, plus the feeder-side fault injector (22 Ω + 8 µH + MOSFET)
6. ORing Schottky
7. Input filter: L_in, C_in
8. **Converter 48 → 12 V, 120 W**, bought or built per §4 of the scaling sheet, with f_sw ≥ 400 kHz
9. **Storage bank**: 3 × 22 mF with an ESR ballast. Its negative terminal is the **star ground**.
10. **Rack shunt** 1 mΩ
11. **Rack breaker**: IRFP7430, acting as the SSCB emulation
12. **"48 V bus" node (12 V)**
13. Load bank: 5 switched branches, 2.2–47 Ω, about 10 A total
14. **Rack-side fault injector**: 63 mΩ / 0.33 Ω / 1.2 Ω, with 10 / 30 / 100 µH coils and an IRFP7430 switch

The **feeder breaker** is an N-MOSFET in the 48 V return.

**Not built on purpose:** bolted 800 V-side faults. These belong to Layer 1 (analog thresholds), and they would abuse the lab supply.

## 1.4 Sensing nodes (Sheet 2)

The same board design is used for both nodes, with the role chosen by jumper. It sits on a **Nucleo-H743ZI2**.

- **Current channel:** shunt → INA240 (×20 rack / ×50 feeder) → 4th-order Butterworth low-pass at 100 kHz (two Sallen-Key stages, OPA2350) → clamp → ADC1.
- **Voltage channel:** 0.1 % divider (÷5.3 rack / ÷21 feeder) → buffer → same filter → ADC2.
- **Sampling:** ADC1 + ADC2 in dual simultaneous mode, 16-bit, 500 kSa/s, timer-triggered, DMA ring buffer.
- **Full scale:**
  - Rack: 13 × rated at 2.6 V. Rated current ≈ 4 000 LSB.
  - Feeder: 2 × rated.
- **Outputs:**
  - TRIP (PF13) → breaker driver
  - ONSET (PF14) and ALERT pins
  - SYNC input (PF12)
  - CAN-FD between the nodes
  - USB event record: 0.2 ms before and 5 ms after the event, ≈ 21 kB per event
- **Replay inputs:** **JP1/JP2 lift the sensor outputs and feed SMA inputs into the same filter and ADC chain.** This matters a lot for Part 2.

## 1.5 Bench control and safety (Sheet 3)

A third Nucleo-H7 does the following:
- Runs the workload profiles: staircase ramps over 5 load gates, with a two-tier cadence.
- Schedules faults through **hardware one-shots** (74HC123: 10 ms feeder, 5 ms rack). The MCU can only *start* a fault pulse. An ARM key switch is in series.
- Emulates POL-UVLO.
- Sends a SYNC pulse to both nodes and the scope.
- Replays waveforms through DAC1/DAC2 (12-bit, 1 MSa/s) into the node SMA inputs for the latency test.
- Runs the whole test plan unattended from a USB CLI script.

Safety summary:
- Stored energy is 4.2 J in the bank and 0.15 J on the bus capacitor.
- Fault pulses are ≤ 130 A for ≤ 5 ms.
- Protection: fusing, E-stop, a thermal switch at 90 °C, and a second person present for every fault test.

## 1.6 Known gaps between model and bench, and the decisions already made

| Gap | Decision |
|---|---|
| The model uses a constant-power load; the bench uses resistors | Add `load_model = "resistive"` to the core for the bench dataset (question for the professor) |
| The converter-input ramp limiter can't be built in a plain buck | Bench runs with `smooth_on = 0`. This is the harder case for the feeder, so the conservative one to show. |
| A lab supply replaces the droop-controlled source | Measure its impedance and CC transition, then enter them as R_droop and τ_c |
| Fault inductance | Add air-core coils; without them the bench fronts would fall outside the training distribution |
| Workload ramps | Binary-weighted staircase, with the same profile in simulation |
| Switching ripple: the averaged model never showed it to the relay | f_sw ≥ 400 kHz, with the 4th-order 100 kHz filter giving ≥ 48 dB attenuation. Measure the residual noise and add it to `synth.synthesize`. |
| No isolation on the bench | Stated openly; the product would need it |

## 1.7 Verification and acceptance (pre-registered)

**Before building:**
- Generate a bench dataset from paper values, with 16-bit quantisation.
- Expected rack 90 % rise time: within 2× of 0.06 ms. Expected feeder 90 % rise time: within 2× of 1.4 ms.

**After building:**
- Measure every element.
- Regenerate the dataset from the measured values and retrain.

**Test plan:** 200 benign events and 80 faults. Acceptance criteria:
1. Bench feature values fall within the simulated 2.5–97.5 % range in ≥ 90 % of events.
2. 0 false trips and ≤ 3 misses, with decisions at 0.25 ms.
3. Scope-measured onset-to-trip latency ≤ 250 µs in every fault run.

**Original schedule:**

| Dates | Work |
|---|---|
| 1–7 Oct | Paperwork and parts |
| 8–17 Oct | Professor's review; Nucleo boards arrive |
| 18–31 Oct | Bench assembly; buy-or-build decision on the converter; latency test |
| 1–8 Nov | Recordings |
| 9–14 Nov | Demo and rehearsal |

---

# Part 2: Prof. Supachai's advice, and my assessment

## 2.1 What he advised

1. **Make it a real-time Hardware-in-the-Loop (HIL) testbed.** Proving real-time response on physical hardware is the main selling point (จุดขาย) for the judges.
2. **Use MATLAB/Simulink (Simscape Electrical) instead of LTspice** for the high-voltage system model. LTspice is aimed at low-power circuits.
3. **Use the lab's tabletop HIL box.** It runs the Simulink model and outputs real, scaled analog voltages (e.g. 1000 V → 1 V) into your hardware. Ajarn Pichai also has a high-voltage HIL; coordinate with him so the firmware and interface modules are ready.
4. **Have at least two monitoring nodes**, before and after the converter. Their signals behave differently.
5. **Build an interactive dashboard.** It should show the bus status across the network, let you click a point to see its live data, and let you trigger a simulated fault and watch the system respond.
6. **Computation is not the bottleneck.** The math is light, and he doesn't expect the 0.25 ms target to be a problem.
7. **Lab resources are available:** many STM32 boards, the lab equipment, and a room for the build. He will review the schematic, the firmware design and the pre-build verification.

**What we know about the HIL so far:**

| Question | Status |
|---|---|
| Model | Unknown, described as a tabletop box |
| Solver time step | **Not asked yet** |
| Supports Simscape Electrical | Yes |
| Live fault trigger from a PC | Probably; to confirm |
| Can it go to the venue | Probably; to confirm |

## 2.2 Main conclusion: the HIL slots into your design; it doesn't replace it

My earlier advice, before I saw the design, was that "the power stage mostly goes away." I'm taking that back. Your design already has the HIL socket:

- **The node boards' SMA replay inputs (JP1/JP2) are the HIL interface.**
- **The HIL replaces Nucleo #3's DAC replay**, and turns open-loop playback into a closed loop.
- **The power bench remains the only evidence for doubt 3.**

| Judges' doubt | DAC replay (old plan) | HIL (new) | Power bench |
|---|---|---|---|
| 1. Algorithm speed | ✓ open-loop | ✓✓ **closed loop**: the model's breaker opens on your TRIP, and the HIL timestamps fault → trip | ✓ |
| 2. Real processing hardware | ✓ | ✓✓ | ✓ |
| 3. "Only a simulation?" | ✗ | ✗ The waveforms are still computed. No real sensors, ripple, noise or converter. | **✓ only here** |
| Full-scale system (800 V / 132 kW) | ✗ | **✓ the HIL can run the original data-center model**, not the 120 W scaled one | ✗ |
| Interactive "trigger a fault" demo at the venue | weak | **✓ safe, repeatable, portable** | risky (130 A pulses in a hall) |

The HIL also fills exactly the gaps listed in §1.6. In the HIL model you can have:
- the **constant-power load**
- the **ramp limiter** (`smooth_on = 1`)
- the **bolted 800 V-side faults** the bench deliberately skips

So the story for the judges becomes:

> "**HIL** shows the relay protecting the real 800 V / 132 kW design in closed loop, with independently measured trip time. **The bench** shows the same relay, unchanged, working on real sensors and real faults at 120 W."

## 2.3 What actually changes in the design

| Sheet | Change | Size |
|---|---|---|
| **Sheet 2: nodes** | **Protect the SMA inputs** for HIL levels. Analog outputs are typically ±10 V; the OPA2350 runs on a 3.3 V rail. Add a series 1 kΩ and a BAT54S clamp to the rails at each SMA, or a divider if the HIL can't be set to 0–3.3 V. | small |
| Sheet 2 | **TRIP also goes to a HIL digital input.** Add a buffer, so it drives both the breaker driver and the HIL. Check the DI threshold: 3.3 V TTL is fine, 24 V industrial needs an interface. | small |
| Sheet 2 | **SYNC comes from a HIL digital output** marking fault inception. Check that PF12 is 5 V tolerant, or level-shift. | small |
| Sheet 2 | Add a BNC/SMA panel per node: i, v in; TRIP, SYNC out. | small |
| **Sheet 3: bench control** | DAC replay becomes a fallback only. Nucleo #3 also becomes the **"demo controller"**: the dashboard sends it a fault command over USB, and it raises a GPIO into a HIL DI. **This makes the fault button work even if the HIL has no PC API.** | small |
| **Sheet 1: power bench** | Not driven by the HIL at all. But fix the issues in §2.4 before the professor's review. | medium |
| **New: Simulink model** | Port the core from `dcsim` to Simulink and deploy it on the HIL (§2.6). | **large** |
| **New: dashboard** | §2.7 | **large** |
| **Datasets** | Add a `PARAMS_HIL` dataset path that includes HIL zero-order hold at the solver step, DAC quantisation and an added noise floor (§2.5) | medium |

**Model scaling in the HIL:** don't use a fixed 1000:1 ratio. Set each analog output's gain so the node sees **the same per-unit full scale as on the bench**. For example, rack current at 0.2 V per p.u. reproduces exactly what INA240 × 20 delivers. Then the same firmware, the same relay and the same thresholds work in HIL mode and bench mode; only the jumper changes.

**Minimum HIL I/O for two nodes:**
- 4 analog outputs: i and v per node
- 2 digital inputs for the TRIPs, plus 1 for the fault command
- 1 digital output for SYNC

## 2.4 Issues in the current schematic (independent of the HIL)

I found these while reading the sheets. The first three are safety or function problems and should be fixed before the professor reviews the drawing.

1. **The rack breaker is a high-side N-MOSFET with a low-side driver, so it won't turn on.**
   - Q_brk sits in the positive busbar, so its source is at about 12 V. Fully enhancing it needs a gate at about 22 V. The listed TC4420/UCC27517, powered from the 12 V bus, can't do that.
   - Fixes:
     - an **isolated gate driver** with an isolated 12 V DC-DC referenced to the MOSFET source (Si8271 / UCC5350 class), or
     - a **static high-side driver with a charge pump** (LTC7004 class).
   - Verify the parts. Moving it to the return path is possible, but it changes what v_out means.
2. **The gate drivers are powered from the bench 12 V bus, which collapses during exactly the fault they must handle.**
   - In a bolted rack fault, the 12 V bus sags. The breaker gate drive collapses with it.
   - The MOSFET then drops into the linear region while carrying up to 130 A, and will be destroyed.
   - Fix: power all gate drivers, at least the breakers and fault switches, from a **separate supply** that the fault cannot reach: a second bench supply, or an isolated DC-DC from the 48 V side with hold-up capacitance.
3. **Nothing absorbs the inductive energy when a fault current is switched off.**
   - Rack fault coil at 130 A: **0.08 J (10 µH), 0.25 J (30 µH), 0.85 J (100 µH)**. This is dumped into the fault MOSFET at the end of the one-shot, or into the breaker when it trips.
   - Wiring stray inductance of about 0.5 µH at 130 A adds about 4 mJ, as a fast spike.
   - Feeder fault: 8 µH at 2.2 A is tiny energy, but turned off in about 50 ns it gives **≈ 350 V** across a **30 V IRLB8721**.
   - Fixes:
     - a **freewheel diode across each fault branch (coil + resistor)**
     - a **TVS across each breaker and fault MOSFET**
     - a **≥ 100 V logic-level MOSFET for the feeder fault** on the 48 V bus (IRLB8721 is rated 30 V; IRLZ44 at 55 V is marginal)
4. **Feeder breaker in the return: check the body diode orientation.**
   - The return current flows from bench ground to supply(−).
   - If the source faces bench ground, the body diode conducts that current, and the breaker can never interrupt it.
   - The drain must face bench ground and the source supply(−). The driver is then referenced to supply(−).
   - Also confirm the lab supply output is **floating** (not earthed). Use scope ground clips only at the star, or an earthed probe will bypass this breaker.
5. **The fail-safe state is described inconsistently.**
   - Sheet 3 says "10 kΩ pull-down, so an unpowered node = breaker OPEN." With an inverting driver, though, a low input gives gate high, which means **CLOSED**.
   - SCHEMATIC_DESIGN §1 says "default ON."
   - Decide which one you want and make the text match. For a bench, "no node → no power" (fail-open) is arguably the safer choice.
6. **Documentation inconsistencies the professor will notice:**
   - BOM item 3 says **INA240A3 (×50)**, but A3 is ×100. Sheet 2 already corrects this to A2.
   - SCHEMATIC_DESIGN §2 (voltage channel) and §6 still say **150 kHz**, but the filter is now 100 kHz.
7. **Lab STM32s vs the H7.**
   - The whole sensing plan assumes the H7's **16-bit** ADC.
   - If the lab boards are F4/G4 (12-bit), rack rated current drops from about 4 000 to about **250 LSB**. The full scales and the `bits` setting in the dataset must be redone.
   - Use lab boards for Nucleo #3 and prototyping; keep H7s for the nodes if you can get them.

## 2.5 HIL risks to settle first

| Risk | Why it matters for *this* relay | What to do |
|---|---|---|
| **Solver time step** (not yet asked) | Rack 90 % rise ≈ 60 µs; the node samples every 2 µs. At a 1–2 µs step, the HIL output looks like the simulation. At about 10 µs you get 6 samples per front, usable only if the relay is retrained on a zero-order-hold version. At 20–50 µs (typical for CPU-based models), the rack front is 1–3 steps, so **rack-node features won't transfer**. Then the HIL is good only for the feeder node and the latency demo. | Ask first. Also ask whether an FPGA solver is available. |
| **The HIL output is too clean** | The onset detector uses σ of a quiet window. With almost no noise, σ ≈ DAC quantisation, the threshold becomes extremely sensitive, and DAC steps or glitches can trigger false onsets. | Add band-limited noise in the model at the **measured** node noise floor, the same idea as §6a. |
| **DAC update rate and resolution** | A ±10 V 16-bit DAC used over 0–3.3 V gives about 13.4 effective bits, coarser than the H7 ADC. Staircase images at 1/Ts pass the 100 kHz filter if Ts > ~5 µs. | Model zero-order hold and quantisation in `synth` (`PARAMS_HIL`) and train on it. |
| **Stiff branch in the model** | The 800 V fault branch has L_f / R_f = 2 µH / 5 Ω, a time constant of **0.4 µs**, shorter than any realistic HIL step. Forward-Euler discretisation goes unstable. | Use a Tustin/trapezoidal discrete solver, or drop L_f in the HIL model and say so. Its effect is above the 100 kHz anti-alias filter anyway. |
| **Ground loop** | The HIL is mains-earthed. The PC USB is earthed too, as is the scope. | Use a single-point ground between the HIL analog-output ground and the node ground. Consider a USB isolator on the dashboard link. |
| **Latency accounting** | The HIL digital input is sampled once per step. | Report "fault → TRIP received" including up to one step, and cross-check with the scope (SYNC vs TRIP). |
| **Portability** | The demo depends on the box being at the venue. | Confirm with Ajarn Pichai. Record a full closed-loop run on video in any case. |

## 2.6 Simulink port plan

1. **Write the model from the equations, not from Simscape parts.**
   - Translate the core's `_derivs` (the averaged converter, cascade control, source droop, lines and capacitors) into a fixed-step discrete Simulink model.
   - A MATLAB Function block or basic blocks will do.
   - This guarantees it is *the same model* as the Python, and it stays real-time friendly.
   - Use Simscape Electrical only where the HIL toolchain requires it.
2. **Cross-check against Python before going near the HIL.** It must reproduce the `run_demo.py` numbers:
   - benign step: ≈ 0.079 A/µs maximum line di/dt and ≈ 8.5 V sag
   - bolted fault: ≈ 397 A/µs front and bus collapse below UVLO
   - Agreement between the two tools is itself a slide.
3. **Build a fault-scenario block** that selects fault location, R_f and L_f at run time. This becomes the dashboard's "fault menu."
4. **Breaker blocks** opened by the HIL digital inputs. This is what closes the loop.
5. **Output gain blocks** mapping each signal to the node's per-unit full scale (§2.3), plus the noise source (§2.5).

## 2.7 Dashboard architecture

Three data sources:

| Source | What it provides |
|---|---|
| **Nodes (USB)** | Decimated telemetry at about 20–50 Hz: v, i, state, last decision. Event records (0.2 ms before, 5 ms after) on each trip. |
| **HIL host** | Every internal model signal: the other "clickable" network points, and the breaker state. Use Simulink external mode or UDP, whatever the box supports. |
| **Demo controller (Nucleo #3)** | Fault command → HIL digital input, and SYNC. |

The UI:
- **A single-line diagram:** meter → feeder → 800 V bus → converter → 48 V bus → racks. Each segment is coloured by state, and every point is clickable.
- **Clear labels for measured vs simulated values.** Node points show values measured by your hardware; other points show model values. Judges will ask.
- **An event view** with both nodes' waveforms aligned on SYNC, showing the onset marker, the decision, the TRIP, and **the latency in µs** as reported by the HIL.
- **Replay mode** that plays recorded events if the hardware fails at the venue.

## 2.8 Recommended scope and schedule

Fitting the HIL, the Simulink port and the dashboard on top of the full bench before 14 Nov is the main risk. I'd make a **decision on 17 Oct** (after the professor's review and the HIL time-step answer) between:

- **A. HIL + nodes + dashboard only.** Fastest and safest, but doubt 3 is answered only weakly.
- **B. HIL primary + a reduced bench (recommended).**
  - Keep the full power path and both nodes, so the bench still shows the converter-induced difference between nodes.
  - Run only the **rack-side faults** with **one coil value**, and drop the feeder fault injector (the HIL covers it).
  - Defer CAN-FD; use SYNC + PC for v1.
  - Bench results are shown as recordings and the simulation-vs-bench table; the HIL is the live demo.
- **C. Full bench + HIL.** Most convincing, highest schedule risk.

| Dates | Work under option B |
|---|---|
| 8–17 Oct | Professor's review (with the §2.4 fixes); ask the HIL questions (§2.9); Simulink port + Python cross-check; node front end on perfboard; ADC/DMA on the H7 |
| 18–24 Oct | HIL bring-up: model on the box, analog outputs → nodes, TRIP → digital input, **first closed-loop latency number**. Bench: converter acceptance test, rack-side assembly |
| 25–31 Oct | Dashboard v1 (telemetry, events, fault button); bench element measurements; retrain on `PARAMS_HIL` and the measured `PARAMS_BENCH` |
| 1–8 Nov | Scripted HIL runs (benign + faults, latency statistics); bench recordings; one table: simulation vs HIL vs bench |
| 9–14 Nov | Rehearsal at the venue setup; record fallback videos of both |

On 0.25 ms: one earlier summary said the professor sized the math overhead against **2.5 ms**. Your spec is **0.25 ms** onset-to-trip (acceptance 3), so confirm he has the right number in mind. The bolted case is already handled by the Layer-1 analog thresholds, so the 0.25 ms target only has to cover the high-Z class, which is the realistic one.

## 2.9 Questions to close with Prof. Supachai and Ajarn Pichai

1. **Model name of the HIL box.** A photo of its front panel and I/O labels answers most of the questions below.
2. **Solver type and minimum time step**: CPU or FPGA? This decides whether rack-node features transfer (§2.5).
3. **Analog outputs:** how many, what voltage range, what DAC resolution and update rate? **Digital inputs/outputs:** how many, what logic level?
4. MATLAB version and the toolboxes or vendor blockset needed. Simscape Electrical is confirmed; is a discrete fixed-step MATLAB Function model also accepted?
5. **Live control from a PC** (UDP or external mode): fault trigger, and streaming of internal signals for the dashboard.
6. **Can the box go to the venue on 14 Nov?** Who transports it, and is there insurance or a sign-out process?
7. **Scope choice:** option A, B or C (§2.8)? And does the professor still want the full power bench for doubt 3?
8. The schematic items in §2.4, especially the breaker gate-drive approach and its supply.
9. The original scaling-sheet questions: the resistive load model, lab equipment, supervision, and the converter buy-vs-build rule.
