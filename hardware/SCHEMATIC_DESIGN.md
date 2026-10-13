# SCHEMATIC_DESIGN.md — testbed and sensing nodes, schematic level (rev 2)

**Written:** 2026-10-01. **Rev 2:** 2026-10-08, after the circuit review (CIRCUIT_REVIEW_2026-10-08.md: 13 flagged faults verified, 7 further findings). Companion to SCALING_SHEET.md (values), `bench_block_diagram_rev2.svg` and the three wiring sheets `wiring/sheet{1,2,3}_*_rev2.svg`. This is the level the professor reviews before a schematic-capture drawing is made; every net and every part role is here, part numbers are candidates to be confirmed against what is purchasable in Thailand.
**Scope:** drawn for option B of HIL_TESTBED_PLAN §2.2 (rack-side faults only; the feeder node measures and signals but does not actuate). Option-C-only parts are marked *(C)* and dashed on the sheets.

## 0. Change log rev 1 → rev 2

| # | change | reason (review item) |
|---|---|---|
| 1 | Rack breaker Q_brk driven by an **isolated gate driver** (UCC5350 / ADuM4120 class) with its own isolated DC-DC (12 → 15 V, 1 W) referenced to the FET's source | a ground-referenced 12 V driver cannot enhance a high-side FET whose source sits at 12 V; source-follower mode, 35 W, fails in linear mode at 100 A (item 1) |
| 2 | Feeder breaker Q_fb *(C)* moved to the **high side** (+48 V after F1), 100 V part (IRFB4110 class), same isolated driver | in the return the gate reference flips to −48 V when it opens (oxide failure); 40 V part under-rated; high side lets the supply (−) sit on the star (items 2, 8, finding 15) |
| 3 | **Fail-safe wiring corrected: 10 kΩ pull-UP on the driver input, inverting driver** — an unpowered or resetting node = breaker OPEN; TRIP = 0 = closed; TRIP = 1 = open. Firmware stays TRIP-active-high | rev 1 wrote "pull-down + inverting", which closes the breaker on a dead node (finding 14) |
| 4 | **D_fw** freewheel Schottky (≥ 30 A, few-hundred-A surge) across R_f48 + L_f48, anode at Q_f48's drain, cathode at the 12 V node; **SMCJ18A TVS** across Q_brk; small Schottky across R_f + L_f *(C)* | 30–300 mJ of coil energy per shot had no path when Q_brk or Q_f48 opens → repetitive avalanche (item 4) |
| 5 | One-shots are **74HC221** (non-retriggerable, no CLR-edge trigger); arm key on CLR *and* in the driver enable | 74HC123 is retriggerable and fires on a rising CLR (item 5) |
| 6 | All gate drivers and both isolated DC-DCs powered from a **separate 12 V adapter**, not the bench bus | the 12 V bus sags to ≈ 5 V in a bolted fault and disappears when Q_brk opens (item 6) |
| 7 | **Power-up order** (§8): K1 closed with the supply output off, then output on (or 10 Ω precharge) | 206 A theoretical inrush, C_in overshoot to 58 V on a 63 V part (item 7, check C) |
| 8 | **F2 20 A** moved to the converter output, before the bank | a fuse in the fault loop sees ≈ 84 A²s per shot and adds R and L to R_f48 / L_f48 (item 9) |
| 9 | **Anti-alias filter** values corrected to a true 4th-order Butterworth: 1.5 nF / 1.3 nF and 3.9 nF / 560 pF with R = 1.1 kΩ (Q 0.54 / 1.31, −3 dB 100.6 kHz, −48 dB at 400 kHz), low-Q stage first | rev-1 values gave Q 0.74 / 0.34, −3 dB at 52.5 kHz, −45 dB at 400 kHz (item 10, check D) |
| 10 | **Input network** on both channels, before the jumper: 1 kΩ + BAT54S clamp + unity buffer (U2B for current, U4A for voltage); 47 Ω + 1 nF at each ADC pin | replay / HIL inputs need protection without moving f₀; H7 R_AIN at 16-bit (HIL plan H2, finding 18) |
| 11 | **INA240A2** (×50) for the feeder node | A3 is ×100 (item 12) |
| 12 | Fault resistor = target − measured coil DCR; heavy wire or copper strip for the 30 / 100 µH coils | a 100 µH air coil is 30–50 mΩ of copper (item 11) |
| 13 | Converter buy criteria (d) start-up into 66 mF without hiccup, (e) pre-bias safe / no reverse current when the input collapses | 57 ms at 14 A; a synchronous buck can boost backwards into C_in (item 13) |
| 14 | ESR ballast is a pulse-rated wirewound (or copper strip) | 1.3 J per bolted shot (finding 17) |
| 15 | 100 V parts everywhere on the 48 V side; no logic-level requirement anywhere (all gates driven at 12–15 V) | IRLB8721 is 30 V (item 3, finding 16) |
| 16 | "150 kHz" leftovers in §2 and §6 corrected to 100 kHz | item 12 |

Nothing in the physics the relay sees changed: fault R and L, bank, ESR, shunts, sampling, full scales and the scaling of SCALING_SHEET.md are as before.

## 1. Power path, left to right (Sheet 1)

1. **Lab supply, 48 V**, set to constant-current limit 4.4 A (= 1.75 × rated; the model's source limit). It must stay in CC mode during a feeder-side fault, not trip. Its output must be switchable on/off from the front panel (power-up order, §8). Output floating; **(−) bonded to the bench star ground** at one point. Its output capacitance and CC transition are measured with a step test and entered into the simulator as R_droop / τ_c.
2. **Emergency stop:** a contactor K1 (or 10 A relay with a mushroom button) in the +48 V feed; **fast fuse F1 5 A** after it.
3. **Feeder breaker Q_fb** *(C)*: N-MOSFET 100 V, ≤ 5 mΩ (IRFB4110 class) in the +48 V line after F1 (high side), driven by isolated driver U18 from the feeder node's TRIP; fail-safe per §3. Under option B this is a wire link and the feeder node's TRIP drives an LED and the HIL only.
4. **Feeder emulation:** air-core coil 20 µH (5 A continuous) in series with the wiring; a 20 mΩ, 3 W resistor if the wiring measures below R_line.
5. **Feeder shunt** 10 mΩ, 4-terminal, 3 W, Kelvin-sensed by the feeder node (i_L).
6. **"800 V bus" node:** C_bus 150 µF 63 V electrolytic to ground (ESR measured; a series 22 mΩ if the part is better than 32 mΩ). Feeder node reads v_bus here.
7. **Feeder-side fault injector** *(C)*: from the bus node to ground through 22 Ω 50 W (or 39 Ω 25 W) + an 8 µH air coil + N-MOSFET 100 V (IRFB4110 class) + driver U16, triggered by the bench control through one-shot A (10 ms). A small Schottky across R_f + L_f takes the coil current when the switch opens. Current is capped by the supply's CC limit, so no heavy switch is needed.
8. **ORing diode:** Schottky 100 V 10 A (STPS10H100) in the +48 V line into the rack input filter; the model's ORing assumption. Forward drop ≈ 0.5 V is 1 % of 48 V.
9. **Rack input filter:** L_in 20 µH air coil (5 A), R_in ≈ wiring, C_in 220 µF 63 V to ground.
10. **Converter 48 V → 12 V, 120 W, current limit 14 A:** buy-or-build per SCALING_SHEET §4, now five criteria: (a) holds 14 A ≥ 10 ms without hiccup, (b) clean 50 % load step (fit f_v, τ_i), (c) efficiency fits the two-term loss model, **(d) starts into 66 mF without hiccup (57 ms at 14 A), (e) pre-bias safe — no reverse current / backward boost into C_in when the input collapses while the bank holds the output up.**
11. **F2, 20 A**, at the converter output, before the bank — outside the fault loop.
12. **Storage bank:** 3 × 22 mF 16 V low-ESR snap-in electrolytics in parallel (66 mF, sweep point 58 mF), reverse-protected by a 20 A 40 V Schottky across the bank, plus a **series ESR ballast** (10–15 mΩ, **pulse-rated wirewound** or copper strip, in the bank's positive leg) so that bank ESR + ballast ≈ 19 mΩ (measured). The bank's negative terminal is the **star ground** of the bench: node grounds, load return, fault return, the supply (−) and the scope ground clips all meet here.
13. **Rack shunt** 1 mΩ, 4-terminal, 5 W, rated 10 A continuous and 130 A pulses, on the busbar **downstream of the storage bank**, so it carries i_pol + i_f48 exactly as the model's rack node.
14. **Rack breaker Q_brk:** N-MOSFET 40 V, ≤ 2 mΩ, 195 A (IRFP7430) in the busbar after the shunt, high side, **isolated driver U19 + isolated DC-DC U21 referenced to its source**, fail-safe per §3; **SMCJ18A TVS across drain–source** for the upstream wiring inductance (check A: 23.8 V peak, 1.6 mJ). It carries up to 130 A for < 350 µs before the relay opens it; the hardware one-shot on the fault switch is the independent backstop.
15. **"48 V bus" node (12 V):** rack node reads v_out here.
16. **Load bank:** five branches to ground, each an aluminium-housed resistor on a fan-cooled heatsink and a 40 V ≤ 10 mΩ N-MOSFET with driver (12 V gate drive, standard-level parts are fine): 2.2 Ω (100 W), 4.7 Ω (50 W), 10 Ω (25 W), 22 Ω (25 W), 47 Ω (10 W). All on ≈ 10 A. A 90 °C thermal switch on the heatsink is in the driver enable. The bench control switches branches in sequence to make staircase ramps.
17. **Rack-side fault injector:** from the 12 V node to ground through a selectable resistor (bolted: **(63 mΩ − measured coil DCR)**, e.g. 2 × 0.12 Ω 50 W in parallel trimmed; 0.33 Ω 50 W; 1.2 Ω 50 W), a selectable air coil (10 / 30 / 100 µH, wound to carry 130 A pulses without saturation, heavy wire or copper strip), and the fault MOSFET Q_f48 (IRFP7430) with driver U17, triggered through **one-shot B** (5 ms). **D_fw** (Schottky, ≥ 30 A continuous, few-hundred-A surge, e.g. STPS30 / MBR30 class) across R_f48 + L_f48, anode at Q_f48's drain, cathode at the 12 V node: carries the coil current when Q_f48 turns off *and* when Q_brk opens with Q_f48 still on (Q_f48's drain is then at ground, so D_fw clamps the 12 V node at ≈ −0.5 V). Reverse-biased during the fault, so the relay sees nothing of it.

## 2. Sensing node board (Sheet 2; two identical boards, gain and divider set by jumpers)

Built on a Nucleo-H743ZI2 (or H723ZG) with a small front-end board on its headers.

- **Current channel:** shunt Kelvin pair → INA240 (A1 = ×20 for the rack node, **A2 = ×50** for the feeder node; REF pins to ground, unidirectional) → JP1 (INA240 output *or* SMA i for DAC replay / HIL) → **1 kΩ + BAT54S clamp to 3.3 V / GND → U2B unity buffer** → **fourth-order Butterworth low-pass** (two unity-gain Sallen-Key stages, R = 1.1 kΩ: stage 1 C1 1.5 nF feedback / C2 1.3 nF to ground, Q 0.54, f₀ 103.6 kHz; stage 2 C3 3.9 nF / C4 560 pF, Q 1.31, f₀ 97.9 kHz; low-Q stage first; OPA2350-class, 3.3 V rail-to-rail) → D1/D2 BAT54S clamp → 47 Ω → 1 nF C0G → ADC1 (PA3). Overall −3 dB 100.6 kHz, −48 dB at 400 kHz (LTspice D, ngspice agree). The feature band-pass tops out at 100 kHz anyway (`f_hi = min(100 kHz, 0.4 fs)`), and converter switching ripple must be ≥ 40 dB down before the ADC (§6a). Full scale 3.3 V = 13 × rated (rack, 2.6 V at 130 A) / 2 × rated (feeder, 2.5 V at 5 A).
- **Voltage channel:** divider (12 V: 20 k / 4.7 k; 48 V: 100 k / 4.99 k, 0.1 % metal film; 2.28 V nominal, full scale 1.45 ×) → JP2 (divider *or* SMA v) → 1 kΩ + clamp → U4A unity buffer → the same 100 kHz filter (U5A, U6A) → D3/D4 clamp → 47 Ω → 1 nF → ADC2 (PC0).
- **Sampling:** ADC1 and ADC2 in dual simultaneous mode, 16-bit, 500 kSa/s, triggered by TIM3, DMA into a ring buffer in 8-sample blocks. This is the firmware's contract (FIRMWARE_SPEC.md §9).
- **Outputs:** TRIP (PF13, push-pull, active high, to the breaker's isolated driver, LD3 and a HIL digital input); ONSET (PF14) and ALERT (PF15) test pins / LED; SYNC input (PF12) from the bench control or a HIL digital output.
- **Link:** CAN-FD transceiver (3.3 V, TCAN1042) between the two nodes on a short twisted pair with 120 Ω terminations; carries each node's summary (16 B within 20 µs of the window close) and its features (DEVIATIONS #13). No isolation on the bench (common ground); the product needs isolated CAN and isolated supplies, and the report says so.
- **Record path:** ST-Link VCP for commands, the H7's own USB for the record stream: on a decision, on SYNC or on `capture`, the node sends the 2 600-sample record of both channels to the PC in the dataset's fast-stream layout.
- **Replay / HIL input:** JP1 / JP2 select the SMA inputs instead of the sensors, so the bench control's DACs (0–3.3 V through 100 Ω), a signal generator, or the HIL's analog outputs (0–10 V through a 3:1 pad, 20 kΩ / 10 kΩ, on the HIL adapter panel) drive simulated i and v into the same protection, buffer, filter and ADC chain. First line of protection in HIL mode: saturate the HIL outputs to 0–10 V in the model.
- **Power:** from the Nucleo's 3.3 V; analog rail through a ferrite with 10 µF + 100 nF at every amplifier.

## 3. Bench control and driver board (Sheet 3; third Nucleo-H7)

- Five load gates → five gate drivers U10–U14 (TC4420 / UCC27517, 12 V from the adapter); driver enable = 90 °C thermal switch (NC) AND the arm key.
- Fault triggers: FAULT_B → **U15B 74HC221** one-shot (5 ms: R_t ≈ 71 kΩ, C_t 100 nF, t_w ≈ 0.7·R·C) → U17 → Q_f48. FAULT_A *(C)* → U15A 74HC221 (10 ms) → U16 → Q_f8. The MCU can only *start* a pulse (rising edge); its length is set by R_t·C_t; the '221 cannot be retriggered and does not trigger on a CLR edge. The **arm key** holds CLR low when disarmed and is in series with the U16 / U17 enable; the firmware also reads the key and refuses a fault when it is off. Three independent cuts; no firmware state can hold a short on the bus.
- **Breaker drivers:** node TRIP (3.3 V, active high) → **10 kΩ pull-up to 3.3 V** → isolated driver U19 (rack) / U18 (feeder, *C*) on its inverting input → gate of Q_brk / Q_fb; secondary side powered by isolated DC-DC U21 / U20 (12 → 15 V, 1 W) with its (−) on the FET's source. Truth table: node pin floating (unpowered, reset, cable off) → high → gate low → **breaker OPEN**; TRIP = 0 → gate high (15 V above the source) → closed; TRIP = 1 → open. Firmware stays TRIP-active-high (`board.h` PF13).
- **Driver supply:** a separate 12 V / 2 A adapter through a 1 A fuse feeds U10–U17 and the two isolated DC-DCs. Not the bench bus. Adapter off ⇒ both breakers open.
- POL-UVLO emulation: ADC3 at 1 MSa/s on v_out; if v_out < 9.6 V for 100 µs, all five load gates off; re-enable above 10.1 V. This reproduces the model's load-side UVLO in the bolted case.
- SYNC: one pulse at each scheduled event, manual step and fault trigger, to both nodes and the scope (BNC). In HIL mode SYNC comes from a HIL digital output.
- DEMO_FAULT: one GPIO → HIL digital input (fault-scenario trigger in the model) + SYNC, so the dashboard's fault button works without a PC link to the HIL (HIL plan F8).
- DAC1 / DAC2 (PA4 / PA5) at 1 MSa/s (12-bit) for waveform replay from RAM tables loaded over the console; tables exported from the dataset by `tools/replay_waveforms.py`.
- USB-serial CLI to the PC: `tools/bench_run.py` scripts the SCALING_SHEET §6 plan (200 benign, 60 rack faults; + 20 feeder faults under option C) and never bypasses the hardware arm switch.

## 4. Measurement and calibration before the first fault run

- Each shunt: 4-wire resistance at 1 A and 10 A (temperature coefficient noted).
- Each capacitor bank: capacitance and ESR at 100 Hz and 1 kHz (LCR meter), and a discharge test into a known resistor for the effective value.
- Each coil: inductance at 1 kHz and 100 kHz; **DC resistance (it is part of R_f48)**.
- Wiring: resistance of every power run (4-wire), inductance estimated from geometry and confirmed by the fault front on the scope.
- Converter: efficiency at 20 / 50 / 100 % load; 50 % load-step response (fit f_v, τ_i); overload into 14 A (hold or hiccup, and for how long); start-up into the bank; reverse-current behaviour with the input removed.
- Supply: step response and CC transition; output on/off behaviour.
- Sensing chain: gain and offset of each channel against a calibrated meter at three points; **filter step response on the scope** (goes into the bench / HIL dataset synthesis in place of the designed response); quiet-bus noise floor (`status` σ).
All values go into `PARAMS_BENCH` in the simulator; the bench dataset is regenerated from them; the relay used on the bench is trained on that set.

## 5. Parts list rev 2 (quantities for two nodes, one bench, spares; *(C)* = option C only)

| # | part | qty | note |
|---|---|---|---|
| 1 | Nucleo-H743ZI2 (or H723ZG) | 3 | two nodes + bench control — **first item to secure; everything measurable waits on it** |
| 2 | INA240A1 | 3 | rack node (×20) + spare |
| 3 | **INA240A2** | 3 | feeder node (×50) + spare (rev 1 said A3 = ×100) |
| 4 | OPA2350 (or any 3.3 V RRIO dual, ≥ 20 MHz GBW) | 6 | buffers and filters (U2–U6 per node) |
| 5 | shunt 1 mΩ 4-terminal, 5 W (WSL / CSS class) | 3 | rack |
| 6 | shunt 10 mΩ 4-terminal, 3 W | 3 | feeder |
| 7 | 0.1 % metal-film resistors for dividers; 1 % for filters; C0G capacitors 1.5 nF, 1.3 nF, 3.9 nF, 560 pF, 1 nF | kit | |
| 8 | TCAN1042 (3.3 V CAN-FD transceiver) | 3 | |
| 9 | gate driver, single, non-inverting (UCC27517 / TC4420) | 10 | 5 loads, Q_f48, Q_f8 *(C)*, spares — 12 V supply |
| 9a | **isolated gate driver** UCC5350 / ADuM4120 class | 2 (+1) | Q_brk, Q_fb *(C)* |
| 9b | **isolated DC-DC 12 → 15 V, 1 W** (B1215S / MGJ class) | 2 (+1) | one per isolated driver, (−) on the FET's source |
| 10 | IRFP7430 (40 V, 1.3 mΩ, 195 A, TO-247) | 4 | rack fault switch, rack breaker, spares |
| 11 | **IRFB4110** (100 V, 3.7 mΩ, 180 A) | 3 | feeder breaker *(C)*, feeder fault switch *(C)*, spare (replaces IRLB3034 40 V and IRLB8721 30 V) |
| 12 | 40 V ≤ 10 mΩ N-MOSFET, standard level | 8 | five load branches + spares (12 V gate drive, no logic-level needed) |
| 13 | aluminium-housed resistors: 2.2 Ω 100 W; 4.7 Ω 50 W; 10 Ω, 22 Ω 25 W; 47 Ω 10 W | 1 each + 1 spare | load bank |
| 14 | 0.12 Ω 50 W ×2, 0.33 Ω 50 W, 1.2 Ω 50 W (pulse-rated); 22 Ω 50 W, 39 Ω 25 W *(C)* | 1 set | fault injectors; bolted value trimmed for the measured coil DCR |
| 15 | electrolytic 22 mF 16 V low-ESR snap-in | 4 | storage bank + spare |
| 16 | electrolytic 150 µF 63 V, 220 µF 63 V | 2 each | bus and input filter |
| 17 | 10–15 mΩ **pulse-rated wirewound** (or copper strip), 20 mΩ 3 W, 22 mΩ | 3 | ESR ballast, R_line, bus ESR |
| 18 | enamelled copper wire 1.5 mm², 4 mm², and 6 mm² or copper strip for the 30 / 100 µH coils (8 *(C)*, 20, 20, 10, 30, 100 µH) | 2 spools | wound to a calculator, L and DCR measured |
| 19 | Schottky STPS10H100 (10 A 100 V); 20 A 40 V Schottky | 3 / 2 | ORing; bank reverse protection |
| 19a | **D_fw** Schottky ≥ 30 A, surge ≥ 200 A (STPS30 / MBR30 class, TO-220) | 2 | rack fault coil freewheel |
| 19b | **SMCJ18A** TVS | 3 | across Q_brk (+ spares) |
| 19c | small Schottky (SS34 class) | 2 | feeder coil freewheel *(C)* |
| 19d | BAT54S | 10 | input clamps, ADC clamps |
| 20 | **74HC221** dual one-shot + R/C (71 kΩ / 143 kΩ, 100 nF film) | 2 | 5 ms and 10 ms *(C)* fault limits |
| 21 | heatsink ≥ 0.5 K/W with 120 mm fan; 90 °C thermal switch (NC) | 1 | load bank and fault resistors |
| 22 | contactor or 10 A relay + mushroom E-stop; key switch (arm) | 1 each | |
| 23 | fast fuse 5 A + holder (F1); 20 A fuse + holder (F2, converter output); 1 A (driver adapter) | 1 each | |
| 23a | **12 V / 2 A adapter** | 1 | driver supply |
| 24 | copper bus bar 3 × 15 mm, 4 mm² wire, ring lugs, M5 hardware | — | 12 V side |
| 25 | BNC panel jacks (6), SMA jacks (4), banana jacks (4), screw terminals | — | scope taps, replay / HIL inputs, supply |
| 26 | perfboard / 4-layer PCB for the node front ends (2) and the driver board (1) | — | perfboard first |
| 27 | 48 V → 12 V 150 W buck module, f_sw ≥ 400 kHz | 2 | buy route; characterised against the five criteria before use |
| 28 | (build route only) sync-buck controller IC with external compensation and a non-hiccup cycle-by-cycle limit, 100 V MOSFETs, 33 µH 15 A inductor, 100 µF 100 V input caps | 1 set | order only if the module fails its test |
| 29 | USB isolator (ADuM3160 / ADUM4160 class) | 1–2 | node USB links to the PC if a ground loop shows on the quiet-bus noise |

Not on this list, expected from the lab: 48 V supply (CC mode, output on/off), scope ≥ 100 MHz, differential or current probe ≥ 10 MHz, LCR/ESR meter, multimeter, soldering station, PC.

## 6. Grounding, layout and EMC notes

- Star ground at the storage bank negative; the two nodes reference it with their own ground wire, not through the power return. The lab supply (−) is bonded to the star at one point; no other earth connection on the bench. Scope ground clips only on the star; feeder-side quantities (shunt, L_line) by differential probe.
- Kelvin sense pairs twisted; INA240 placed within 3 cm of the shunt; the front-end board sits on the Nucleo, the shunt cable is short.
- The fault loop (bank → shunt → breaker → fault resistor → coil → MOSFET → ground) is kept physically small; the coil is *the* inductance of that loop by design, so its value dominates the wiring's. D_fw sits directly across the resistor + coil with short leads.
- Scope measurement of the raw fault front: differential probe across the rack shunt, ≥ 10 MHz, plus ch1 SYNC, ch3 ONSET, ch4 TRIP. This is what answers the judges' probe remark: the node's own front end is band-limited to 100 kHz for the 500 kSa/s ADC by design; the scope that checks the front is not.

## 6a. Switching ripple: the one thing the simulator never showed the relay

The core is an averaged converter: the training data contain **no switching ripple**. The bench converter will put ripple on i_rack and v_out at its switching frequency, and the relay's noise-based onset detector (σ of the quiet window), `didt_max` and `spec_i` would all see it. Three rules follow:
1. **Converter switching frequency ≥ 400 kHz** (buy or build): with the corrected 4th-order 100 kHz anti-alias that is 48 dB of attenuation, i.e. ripple below one LSB-equivalent of per-unit noise at the ADC. A 100–200 kHz module is rejected on this criterion.
2. The **residual** ripple and front-end noise are measured on the real node (quiet bus, `status` σ) and added to the bench dataset as the noise model of `synth.synthesize`, together with the measured filter response (HIL_TESTBED_PLAN §2.8, the front-end option). This is a parameter, not a model change.
3. Scope checks of the raw front use the differential probe *before* the filter; the relay's own view is after it.

## 7. What the professor is asked to check

1. The power path and the two breaker placements (both high side, isolated drivers, fail-safe by pull-up + inverting).
2. D_fw, the TVS, the 74HC221 one-shot with the arm key on CLR, the separate driver supply, the power-up order.
3. Fault injector currents, resistor pulse ratings and the one-shot limits (SCALING_SHEET §7).
4. The sensing chain: full scales, the corrected 4th-order 100 kHz anti-alias for 500 kSa/s and the ≥ 400 kHz switching-frequency rule (§6a), the input protection, no isolation on the bench.
5. Whether a 100 Hz voltage loop should be a hard requirement of the converter or a measured value.

## 8. Power-up order and safety procedure

1. Nodes and bench control on USB (their TRIP pins read 0 → the breaker drivers close the breakers).
2. Driver adapter on.
3. K1 closed **with the supply output off**.
4. Supply output on (its own ramp / CC limit precharges C_bus and C_in; no 200 A inrush, C_in stays far below 63 V). If the supply has no output switch: 10 Ω precharge resistor bypassed by K1 after ≥ 5 ms.
5. Arm key only for a fault run; second person present; E-stop within reach.
Every node reset or reflash opens its breaker (fail-safe) — expected. Reflash with the supply output off. Stored energy 4.2 J (bank) + 0.15 J (bus): burn / spatter hazard at the fault switch, not a shock hazard; ≤ 130 A for ≤ 5 ms by hardware.
