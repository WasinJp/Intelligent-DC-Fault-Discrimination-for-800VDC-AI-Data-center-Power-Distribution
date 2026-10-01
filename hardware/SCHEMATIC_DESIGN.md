# SCHEMATIC_DESIGN.md — testbed and sensing nodes, schematic level

**Written:** 2026-10-01. Companion to SCALING_SHEET.md (values) and the block diagram `bench_block_diagram.svg`. This is the level the professor reviews before a schematic-capture drawing is made; every net and every part role is here, part numbers are candidates to be confirmed against what is purchasable in Thailand.

## 1. Power path, left to right (see the diagram)

1. **Lab supply, 48 V**, set to constant-current limit 4.4 A (= 1.75 × rated; the model's source limit). It must stay in CC mode during a feeder-side fault, not trip. Its output capacitance and CC transition are measured with a step test and entered into the simulator as R_droop / τ_c.
2. **Emergency stop:** a contactor (or 10 A relay with a mushroom button) in the +48 V feed; **fast fuse 5 A** after it.
3. **Feeder breaker (relay actuator, feeder node):** N-MOSFET (40–60 V, ≤ 5 mΩ, e.g. IRLB3034-class) between supply(−) and bench ground, driven by a gate driver from the feeder node's TRIP line, default ON at power-up (pull-up through the driver). Placing it in the return keeps every measurement referenced to bench ground.
4. **Feeder emulation:** air-core coil 20 µH (5 A continuous) in series with the wiring; a 20 mΩ, 3 W resistor if the wiring measures below R_line.
5. **Feeder shunt** 10 mΩ, 4-terminal, 3 W, Kelvin-sensed by the feeder node (i_L).
6. **"800 V bus" node:** C_bus 150 µF 63 V electrolytic to ground (ESR measured; a series 22 mΩ if the part is better than 32 mΩ). Feeder node reads v_bus here.
7. **Feeder-side fault injector:** from the bus node to ground through 22 Ω 50 W (or 39 Ω 25 W) + an 8 µH air coil + N-MOSFET (60 V, e.g. IRLB8721) + gate driver, triggered by the bench control through one-shot A. Current is capped by the supply's CC limit, so no heavy switch is needed.
8. **ORing diode:** Schottky 60 V 10 A (STPS10H100-class) in the +48 V line into the rack input filter; the model's ORing assumption. Forward drop ≈ 0.5 V is 1 % of 48 V.
9. **Rack input filter:** L_in 20 µH air coil (5 A), R_in ≈ wiring, C_in 220 µF 63 V to ground.
10. **Converter 48 V → 12 V, 120 W, current limit 14 A:** buy-or-build per SCALING_SHEET §4. Its output goes to the storage bank node.
11. **Storage bank:** 3 × 22 mF 16 V low-ESR snap-in electrolytics in parallel (66 mF, sweep point 58 mF), reverse-protected by a 20 A Schottky across the bank, plus a **series ESR ballast** (a 10–15 mΩ, 5 W resistor in the bank's positive leg) so that bank ESR + ballast ≈ 19 mΩ (measured). The bank's negative terminal is the **star ground** of the bench: node grounds, load return, fault return and the supply return all meet here.
12. **Rack shunt** 1 mΩ, 4-terminal, 5 W, rated 10 A continuous and 130 A pulses, on the busbar **downstream of the storage bank**, so it carries i_pol + i_f48 exactly as the model's rack node.
13. **Rack breaker (relay actuator, rack node):** N-MOSFET 40 V, ≤ 2 mΩ, 195 A (IRFP7430-class) in the busbar after the shunt, gate driver from the rack node's TRIP, default ON. It carries up to 130 A for < 250 µs before the relay opens it; the hardware one-shot on the fault switch is the independent backstop.
14. **"48 V bus" node (12 V):** rack node reads v_out here.
15. **Load bank:** five branches to ground, each an aluminium-housed resistor on a fan-cooled heatsink and a logic-level N-MOSFET with driver: 2.2 Ω (100 W), 4.7 Ω (50 W), 10 Ω (25 W), 22 Ω (25 W), 47 Ω (10 W). All on ≈ 10 A. A 90 °C thermal switch on the heatsink cuts the load gates. The bench control switches branches in sequence to make staircase ramps.
16. **Rack-side fault injector:** from the 12 V node to ground through a selectable resistor (60 mΩ = 2 × 0.12 Ω 50 W in parallel; 0.33 Ω 50 W; 1.2 Ω 50 W), a selectable air coil (10 / 30 / 100 µH, wound to carry 130 A pulses without saturation, which is why they are air-core), and the fault MOSFET (IRFP7430-class) with its driver, triggered through **one-shot B**.

## 2. Sensing node board (two identical boards; gain and divider set by jumpers)

Built on a Nucleo-H743ZI2 (or H723ZG) with a small front-end board on its headers.

- **Current channel:** shunt Kelvin pair → INA240 (A1 = ×20 for the rack node, A3 = ×50 for the feeder node; REF pins to ground, unidirectional) → **fourth-order** low-pass (two Sallen-Key stages, Butterworth, f_c = 100 kHz; OPA2350-class, 3.3 V rail-to-rail) → ADC1 input. Revised 2026-10-01 from 2nd order / 150 kHz: the feature band-pass tops out at 100 kHz anyway (`f_hi = min(100 kHz, 0.4 fs)`), and converter switching ripple must be ≥ 40 dB down before the ADC (§6, ripple note). Full scale 3.3 V = 13 × rated (rack) / 2 × rated (feeder). A 3.3 V clamp diode pair protects the ADC pin during a fault transient.
- **Voltage channel:** divider (12 V: 20 k / 4.7 k; 48 V: 100 k / 4.99 k, 0.1 % metal film) → unity buffer → same 150 kHz filter → ADC2 input.
- **Sampling:** ADC1 and ADC2 in dual simultaneous mode, 16-bit, 500 kSa/s, triggered by a timer, DMA into a ring buffer. This is the firmware's contract (FIRMWARE_SPEC.md).
- **Outputs:** TRIP (push-pull, active high, to the breaker driver; also an LED); ONSET and TRIP-EDGE test pins for the scope; SYNC input from the bench control (timestamps t_event in the record).
- **Link:** CAN-FD transceiver (3.3 V, e.g. TCAN1042-class) between the two nodes on a short twisted pair with 120 Ω terminations; carries each node's decision and the schedule-check result. No isolation on the bench (common ground); the product needs isolated CAN and isolated supplies, and the report says so.
- **Record path:** USB (Nucleo's ST-Link VCP for commands, the H7's own USB for the record stream): on SYNC or on onset, the node sends the last 0.2 ms and the following 5 ms of both channels (5 200 × 2 × 16 bit ≈ 21 kB) to the PC in the same layout as the dataset's fast streams.
- **Replay input:** a jumper disconnects the INA240 output and the divider from the filters and connects two SMA/BNC inputs instead, so the bench control's DACs (or a signal generator) can drive simulated i and v into the same filter and ADC chain for the latency test.
- **Power:** from the Nucleo's 3.3 V; analog rail through a ferrite and 100 nF/10 µF at every amplifier.

## 3. Bench control board (third Nucleo-H7)

- Five load gates → five gate drivers; a 6th GPIO enables the load bank (through the thermal switch).
- Fault triggers: two GPIOs → **hardware one-shots** (74HC123 or a 555 in monostable mode, 5 ms for the rack fault, 10 ms for the feeder fault) → gate drivers. The MCU can only *start* a pulse; its length is set by the RC of the one-shot, so no firmware fault can hold a short on the bus. A physical "arm" key switch in series with the one-shot outputs.
- POL-UVLO emulation: the board reads v_out with its own ADC at 1 MSa/s (or an analog comparator + timer) and, if v_out < 9.6 V for 100 µs, drops all five load gates; re-enables above 10.1 V. This reproduces the model's load-side UVLO in the bolted case.
- SYNC: one pulse at the scheduled event time to both nodes and the scope (BNC).
- DAC1 / DAC2 at 1 MSa/s (12-bit) for waveform replay from flash; waveforms exported from the dataset by a script.
- USB-serial to the PC: a run is a text command ("benign step 40 % ramp 2 ms", "fault rack 0.33 Ω coil 30 µH"), so the whole §6 test plan of the scaling sheet is a script that runs unattended except for the safety supervision rule.

## 4. Measurement and calibration before the first fault run

- Each shunt: 4-wire resistance at 1 A and 10 A (temperature coefficient noted).
- Each capacitor bank: capacitance and ESR at 100 Hz and 1 kHz (LCR meter), and a discharge test into a known resistor for the effective value.
- Each coil: inductance at 1 kHz and 100 kHz; DC resistance.
- Wiring: resistance of every power run (4-wire), inductance estimated from geometry and confirmed by the fault front on the scope.
- Converter: efficiency at 20 / 50 / 100 % load; 50 % load-step response (fit f_v, τ_i); overload into 14 A (hold or hiccup, and for how long).
- Supply: step response and CC transition.
- Sensing chain: gain and offset of each channel against a calibrated meter at three points; filter step response on the scope.
All values go into `PARAMS_BENCH` in the simulator; the bench dataset is regenerated from them; the relay used on the bench is trained on that set.

## 5. Parts list v0 (quantities for two nodes, one bench, spares)

| # | part | qty | note |
|---|---|---|---|
| 1 | Nucleo-H743ZI2 (or H723ZG) | 3 | two nodes + bench control |
| 2 | INA240A1 | 3 | rack node (×20) + spare |
| 3 | INA240A3 | 3 | feeder node (×50) + spare |
| 4 | OPA2350 (or any 3.3 V RRIO dual, ≥ 20 MHz GBW) | 6 | filters and buffers |
| 5 | shunt 1 mΩ 4-terminal, 5 W (e.g. WSL/CSS-class) | 3 | rack |
| 6 | shunt 10 mΩ 4-terminal, 3 W | 3 | feeder |
| 7 | 0.1 % metal-film resistors for dividers; 1 % for filters; C0G capacitors | kit | |
| 8 | TCAN1042 (3.3 V CAN-FD transceiver) | 3 | |
| 9 | gate driver, single, non-inverting (UCC27517 / TC4420) | 12 | 5 loads, 2 faults, 2 breakers, spares |
| 10 | IRFP7430 (40 V, 1.3 mΩ, 195 A, TO-247) | 4 | rack fault switch, rack breaker, spares |
| 11 | IRLB3034 (40 V, 1.7 mΩ) | 3 | feeder breaker + spares |
| 12 | IRLB8721 (30 V) or IRLZ44 (60 V) logic-level | 10 | load branches, feeder fault switch |
| 13 | aluminium-housed resistors: 2.2 Ω 100 W; 4.7 Ω 50 W; 10 Ω, 22 Ω 25 W; 47 Ω 10 W | 1 each +1 spare | load bank |
| 14 | 0.12 Ω 50 W ×2, 0.33 Ω 50 W, 1.2 Ω 50 W, 22 Ω 50 W, 39 Ω 25 W | 1 set | fault injectors |
| 15 | electrolytic 22 mF 16 V low-ESR snap-in | 4 | storage bank + spare |
| 16 | electrolytic 150 µF 63 V, 220 µF 63 V | 2 each | bus and input filter |
| 17 | 10–15 mΩ 5 W, 20 mΩ 3 W resistors | 3 | ESR ballast, R_line |
| 18 | enamelled copper wire 1.5 mm² and 4 mm² for air coils (8, 20, 20, 10, 30, 100 µH) | 2 spools | wound to a calculator, measured |
| 19 | Schottky STPS10H100 (10 A 100 V); 20 A 40 V Schottky | 3 / 2 | ORing; bank reverse protection |
| 20 | 74HC123 dual one-shot (or 2 × NE555) + RC | 2 | 5 ms and 10 ms fault limits |
| 21 | heatsink ≥ 0.5 K/W with 120 mm fan; 90 °C thermal switch | 1 | load bank and fault resistors |
| 22 | contactor or 10 A relay + mushroom E-stop; key switch (arm) | 1 each | |
| 23 | fast fuse 5 A + holder; 20 A fuse for the 12 V bus | 2 | |
| 24 | copper bus bar 3 × 15 mm, 4 mm² wire, ring lugs, M5 hardware | — | 12 V side |
| 25 | BNC panel jacks (6), banana jacks (4), screw terminals | — | scope taps, supply |
| 26 | perfboard / 4-layer PCB for the node front ends (2) and the driver board (1) | — | perfboard first |
| 27 | 48 V → 12 V 150 W buck module | 2 | buy route; characterised before use |
| 28 | (build route only) sync-buck controller IC with external compensation and a non-hiccup cycle-by-cycle limit, 100 V MOSFETs, 33 µH 15 A inductor, 100 µF 100 V input caps | 1 set | order only if the module fails its test |

Not on this list, expected from the lab: 48 V supply, scope ≥ 100 MHz, differential or current probe ≥ 10 MHz, LCR/ESR meter, multimeter, soldering station, PC.

## 6. Grounding, layout and EMC notes

- Star ground at the storage bank negative; the two nodes reference it with their own ground wire, not through the power return.
- Kelvin sense pairs twisted; INA240 placed within 3 cm of the shunt; the front-end board sits on the Nucleo, the shunt cable is short.
- The fault loop (bank → shunt → breaker → fault resistor → coil → MOSFET → ground) is kept physically small; the coil is *the* inductance of that loop by design, so its value dominates the wiring's.
- Scope measurement of the raw fault front: differential probe across the rack shunt, ≥ 10 MHz, plus ch1 SYNC, ch3 ONSET, ch4 TRIP. This is what answers the judges' probe remark: the node's own front end is band-limited to 150 kHz for the 500 kSa/s ADC by design; the scope that checks the front is not.

## 6a. Switching ripple: the one thing the simulator never showed the relay

The core is an averaged converter: the training data contain **no switching ripple**. The bench converter will put ripple on i_rack and v_out at its switching frequency, and the relay's noise-based onset detector (σ of the quiet window), `didt_max` and `spec_i` would all see it. Three rules follow:
1. **Converter switching frequency ≥ 400 kHz** (buy or build): with the 4th-order 100 kHz anti-alias that is ≥ 48 dB of attenuation, i.e. ripple below one LSB-equivalent of per-unit noise at the ADC. A 100–200 kHz module is rejected on this criterion.
2. The **residual** ripple and front-end noise are measured on the real node (quiet bus, `status` σ) and added to the bench dataset as the noise model of `synth.synthesize`, so the trained relay has seen the noise floor it will meet. This is a parameter, not a model change.
3. Scope checks of the raw front use the differential probe *before* the filter; the relay's own view is after it.

## 7. What the professor is asked to check

1. The power path and the two breaker placements (feeder in the return, rack in the busbar).
2. Fault injector currents, resistor pulse ratings and the one-shot limits (SCALING_SHEET §7).
3. The sensing chain: full scales, the 4th-order 100 kHz anti-alias for 500 kSa/s and the ≥ 400 kHz switching-frequency rule (§6a), no isolation on the bench.
4. Whether a 100 Hz voltage loop should be a hard requirement of the converter or a measured value.
