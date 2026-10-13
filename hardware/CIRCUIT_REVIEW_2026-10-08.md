# CIRCUIT_REVIEW_2026-10-08.md — verification of the 13 flagged faults, the extra findings, and what changes on each sheet

**Scope:** the three wiring sheets (rev 1, 2026-10-02), SCHEMATIC_DESIGN.md and SCALING_SHEET.md (2026-10-01), `bench_scaling.py`, the 13-item fault list, and the four LTspice / ngspice checks A–D.
**Verdict in one line:** all 13 items are real; 9 of them would have damaged parts on the first fault run. None of them changes the physics the relay sees (fault R, L, bank, shunts, sampling); they change drive, protection, ratings and the anti-alias filter. The bench concept and the scaling stand.
**Status of every fix below:** PROPOSED — for Wasin's OK, then Prof. Supachai's review. Nothing is ordered yet.

## 1. The 13 flagged items — verified

Checks recomputed independently (Sallen-Key formulas, series RLC discharge of the 66 mF bank, long-solenoid coil estimate). "B/C" says what happens to the item under scope option B (rack-side faults only) or C (full bench).

| # | item | verdict | my check | fix (rev 2) | B/C |
|---|---|---|---|---|---|
| 1 | Q_brk cannot be driven by a ground-referenced 12 V driver | **correct, would fail** | source sits at 12 V; a driver that reaches 12 V gives Vgs ≈ 0. Source-follower mode: node ≈ 8.5 V, ≈ 35 W in the FET at 10 A; linear at ~100 A in a fault | isolated gate driver (UCC5350 / ADuM4120 class) + 1 W isolated DC-DC 12 → 15 V referenced to Q_brk's source. Alternative considered and rejected: P-channel high side (≥ 9 mΩ at 40 V class adds 10 % to the bolted fault loop and runs hot) | both |
| 2 | Q_fb in the return: 40 V part, and the gate reference flips when it opens | **correct, would fail** | normal current must flow drain → source so the body diode blocks: drain at bench ground, source at supply (−). When it opens, supply (−) falls to ≈ −48 V (C_bus drains into the fault; supply (+) follows the bus); a ground-referenced driver then puts +48 V on the gate → oxide failure and the FET turns back on. Check B: 65.7 V peak | **move the feeder breaker to the high side** (+48 V line after F1), 100 V FET (IRFB4110 class), same isolated-driver circuit as Q_brk. Then the supply (−) can be bonded to the star and the return is never opened (this also removes item 8's main hazard) | **C only** (B: wire link) |
| 3 | Q_f8 IRLB8721 is a 30 V part on the 48 V bus | **correct** | IRLB8721 Vds = 30 V; the doc's "60 V" is wrong | 100 V part. Note: the drivers deliver 12 V gate drive, so *no* FET on the bench needs to be logic-level; choose on Vds and Rds only | **C only** |
| 4 | Fault coil has no path when Q_brk or Q_f48 opens | **correct, would fail on every shot** | RLC discharge of the 66 mF bank into R_f48 63 mΩ + ESR 19 mΩ + 10 mΩ wiring: at 250 µs (breaker opens) 10 / 30 / 100 µH carry 116 / 70 / 27 A → 67 / 72 / 36 mJ; at 5 ms 17 / 57 / 292 mJ (the bank sags to ≈ 5 V by then). Repetitive avalanche of 30–300 mJ × 80 runs is outside any datasheet guarantee | **D_fw** Schottky (30 A continuous, few-hundred-A surge, e.g. STPS30 class) across (R_f48 + L_f48), anode at Q_f48's drain, cathode at the 12 V node. Verified for *both* cases: when Q_f48 opens, the coil current circulates through D_fw and R_f48; when Q_brk opens with Q_f48 still on, Q_f48's drain is at ground, so D_fw clamps the 12 V node at ≈ −0.5 V and the current circulates the same way. Reverse-biased during the fault → nothing the relay sees changes. Plus SMCJ18A across Q_brk (wiring inductance; check A: 23.8 V peak, 1.6 mJ) and a small diode across R_f + L_f on the feeder side (77 µJ, trivial but free) | both (feeder diode C only) |
| 5 | 74HC123 is retriggerable | **correct** | a toggling MCU pin extends the pulse indefinitely; the '123 also triggers on a rising CLR edge (power-up) | **74HC221** (non-retriggerable, no CLR-edge trigger). Arm key on CLR (held low = output forced low) *and* in series with the driver enable. Pulse width: HC221 t_w ≈ 0.7·R·C → 5 ms ≈ 71 kΩ × 100 nF; 10 ms (C only) ≈ 143 kΩ × 100 nF | both |
| 6 | Gate drivers powered from the bus they switch | **correct** | Sheet 3 feeds the drivers from the 12 V bench bus through a 1 A fuse. A bolted fault pulls that bus to ≈ 5 V within 5 ms → 5 V gate drive → every FET in linear mode; opening Q_brk removes the supply entirely if taken downstream | separate 12 V adapter → all TC4420 / UCC27517 and the two isolated DC-DCs. The breaker drivers' fail-safe then also covers "adapter off = breakers open" | both |
| 7 | Inrush when K1 closes onto 48 V | **correct** | Z₀ = √(20 µH / 370 µF) = 0.23 Ω → 206 A theoretical, ζ ≈ 0.06, half-period 270 µs. Check C: 102 A peak and **C_in overshoot to 58 V on a 63 V part** | power-up order: K1 closed with the supply *output off*, then output on (the supply's own ramp / CC limit precharges). Written into the procedure. 10 Ω precharge bypassed by K1 (τ = 3.7 ms) if the lab supply has no output on/off | both |
| 8 | Earth paths bypass Q_fb; scope clips | **correct** | if supply (−) is earthed and the bench ground is earthed via scope/PC, Q_fb in the return is shorted by the earth path | with the feeder breaker high-side (item 2) the supply (−) is bonded to the star on purpose; remaining rules: scope ground clips only on the star, feeder-side measurements by differential probe, USB isolator on the node links (HIL plan H6) | both |
| 9 | 20 A fuse in the fault loop | **correct in effect** | a bolted shot is ≈ 84 A²s; whether that melts a given 20 A fuse depends on the type, but a fuse in the loop also adds ≈ 5–10 mΩ and some inductance that then belong to R_f48 / L_f48 | F2 on the converter output, before the bank (its job is a continuous fault on the bank, where the converter's 14 A limit is the source) | both |
| 10 | Anti-alias filter values wrong | **correct, would break acceptance (1)** | Sheet 2 as drawn: stage 1 f₀ 97.5 kHz Q 0.742, stage 2 f₀ 143 kHz Q 0.337; overall −3 dB at **52.5 kHz**, −9.4 dB at 100 kHz, −45.1 dB at 400 kHz. Butterworth needs Q = 0.541 / 1.307 at one f₀. Corrected 1.5 nF / 1.3 nF and 3.9 nF / 560 pF with R = 1.1 kΩ: Q 0.537 / 1.319, f₀ 103.6 / 97.9 kHz, **−3 dB 100.6 kHz, −48.0 dB at 400 kHz** (ideal 4th-order −48.2 dB). Matches check D | the corrected values, low-Q stage first. The bench and HIL datasets synthesise with *this* filter (designed values now, measured step response once built), not the 0.4·f_s = 200 kHz of MODEL.md §7 — that is the front-end option of HIL_TESTBED_PLAN §2.8 | both |
| 11 | Coil DCR is part of R_f48 | **correct** | 100 µH single-layer on a 40–60 mm former: ≈ 40–56 turns, 7–8 m of 4 mm² → **30–35 mΩ** (a multi-layer coil in thinner wire is worse, 50 mΩ as flagged). Against 63 mΩ that is 50–80 % | resistor = target − measured DCR; copper strip or 6 mm² for the 30 / 100 µH coils. Note the bolted point need not be 63 mΩ exactly: it must land inside the scaled sweep 32–317 mΩ and be *measured* into PARAMS_BENCH — the acceptance compares against the simulation of what was built | both |
| 12 | INA240A3 is ×100; "150 kHz" leftovers | **correct** | INA240: A1 = 20, A2 = 50, A3 = 100, A4 = 200 V/V. SCHEMATIC_DESIGN §2 (voltage channel) and §6 still say 150 kHz | parts list row 3 → INA240A2; §2 / §6 → 100 kHz | both |
| 13 | Two more converter buy criteria | **correct, add them** | start-up into 66 mF at 14 A takes 57 ms — many modules hiccup before that; a synchronous buck with the output held up by the bank and the input collapsing can boost backwards into C_in (the MODEL.md ORing assumption, OPEN-24, broken at the converter level) | criteria (d) starts into 66 mF without hiccup; (e) pre-bias safe / no reverse current with the input removed. Both are 5-minute bench tests | both |

## 2. Extra findings (not in the list)

| # | finding | why it matters | fix |
|---|---|---|---|
| 14 | **Sheet 3's fail-safe note is inverted.** It says "10 kΩ pull-*down* on the driver input, inverting driver → unpowered node = breaker OPEN". With a pull-down and an inverting driver, a floating pin reads low → output high → breaker **CLOSED**. | the whole fail-safe argument of HIL_TESTBED_PLAN §2.7 | pull-**UP** on the isolated driver's IN− (or inverting input), so floating → high → inverted → low → breaker open; TRIP = 0 → closed; TRIP = 1 → open. Firmware stays TRIP-active-high as built |
| 15 | **Feeder breaker belongs on the high side** once an isolated driver exists anyway (item 2). The rev-1 reason for the return placement ("keeps every measurement referenced to bench ground") is only true while the breaker is closed; the isolated driver makes the high side equally simple and lets the supply (−) sit on the star | removes items 2 and 8 as hazards; one driver design for both breakers | adopted in rev 2 (dashed under option B) |
| 16 | **No logic-level FETs are needed anywhere.** Every gate is driven by a 12 V driver (TC4420 / UCC27517 / isolated driver at 15 V) | widens the purchasable set in Thailand; the standard-level IRFB4110 (100 V) can serve Q_fb, Q_f8 *and* the load branches | parts list: choose on Vds (≥ 100 V on the 48 V side, ≥ 40 V on the 12 V side) and Rds; no "logic-level" column |
| 17 | **ESR ballast pulse rating.** 15 mΩ in the bank's positive leg carries 130 A for 5 ms: 250 W peak, 1.3 J per shot | a thick-film or small wirewound part will drift or open | pulse-rated wirewound (≥ 5 W, pulse-capable), or make the ballast from the measured wiring + a short copper strip; it is "ESR" in the model and is measured anyway |
| 18 | **ADC source impedance.** R5 / R8 = 100 Ω into the H7 ADC at 16-bit with 8.5-cycle sampling (340 ns) is at the edge of ST's R_AIN table | gain error / settling at 16 bits | 1 nF C0G at the ADC pin (forms the last pole far above 100 kHz) or drive the pin from the op-amp through ≤ 47 Ω |
| 19 | **Rack node v_out tap is downstream of Q_brk** (Sheet 1 places the "48 V bus" node after the breaker). During the decision window Q_brk is closed (1.3 mΩ), so the observable is the model's; after a trip v_out → ≈ −0.5 V (D_fw clamp) and the record shows the breaker opening — fine for the demo, but the bench dataset's post-trip record will not match unless the breaker element is in the simulator | HIL plan §2.5 already asks for a breaker element in MODEL.md 0.4.5 | same breaker element serves the bench dataset; nothing to change on the sheet |
| 20 | **Every node reset opens its breaker** (fail-safe) — the bench loses power on each reflash | expected behaviour, not a fault; must be in the procedure | power-up order in §4 below; reflash nodes with the supply output off |

## 3. The four spice checks — do they help?

Yes, exactly for what they were used for. Prof. Supachai's remark was about the *system* model (800 V, control loops, constant-power load, where Simscape is the tool); the four checks are circuit-level questions — switch spikes, TVS energy, inrush, a filter response — which is what LTspice is good at. LTspice and ngspice agreeing to three digits says the netlist is right; it does not say the device models are. So:

- **A** (Q_brk turn-off, TVS): rerun with the vendor IRFP7430 model (still OPEN in HIL_TESTBED_PLAN §4.3) **with and without D_fw**; the "without" run is the evidence for item 4 (avalanche energy vs the datasheet E_AS). Confirm A already includes D_fw.
- **B** (Q_fb): only needed under option C; rerun with the high-side placement (the peak will be about the same, the gate problem disappears).
- **C** (inrush): rerun with the supply output ramping on *after* K1 (or the 10 Ω precharge) — it should show C_in staying far below 63 V. That run is the justification for the power-up rule.
- **D** (filter): done; keep as the design record. Add the input network (1 kΩ + clamp, R1 → 100 Ω) and re-check the −3 dB point stays at 100 kHz (HIL plan H2).

Present them to the professor as "pre-build verification of the bench circuit, four checks, two independent simulators"; that is the right framing.

## 4. What changes on each sheet (rev 2)

**Sheet 1 — power**
- Feeder breaker Q_fb: high side after F1, 100 V FET, isolated driver; dashed "option C only" (option B: wire link).
- Feeder-side fault injector + one-shot A: dashed "option C only"; 100 V FET; small diode across R_f + L_f.
- ORing diode: 100 V 10 A (STPS10H100 as listed; the "60 V" label on the sheet is stale).
- Converter box: add buy criteria (d) start-up into 66 mF, (e) no reverse boost.
- F2 20 A moved to the converter output, before the bank.
- Storage bank: ESR ballast pulse-rated; star ground; D_rp as before.
- Q_brk: isolated driver + isolated DC-DC, TVS SMCJ18A across D–S, pull-up + inverting (fail-safe).
- Rack fault injector: D_fw across (R_f48 + L_f48), anode at Q_f48 drain, cathode at the 12 V node; R_f48 = target − measured coil DCR; 74HC221 5 ms.
- Supply (−) bonded to the star (floating supply, link bar removed, one earth point).

**Sheet 2 — node front end**
- Filter: C1 1.5 nF / C2 1.3 nF (Q 0.54, first), C3 3.9 nF / C4 560 pF (Q 1.31, second), R = 1.1 kΩ; label "−3 dB 100.6 kHz, −48 dB at 400 kHz".
- Input protection for the replay / HIL path: 1 kΩ + clamp in front of *both* sources before JP1/JP2, R1 → 100 Ω (HIL plan H2); or a passive 3:1 pad when fed from a 0–10 V HIL output.
- INA240A2 for the feeder node (×50); the red note already on the sheet becomes the value in the parts list.
- 1 nF at each ADC pin (item 18).
- Nothing else changes: pins per `board.h`, 500 kSa/s dual ADC, TRIP active high.

**Sheet 3 — control and drivers**
- U15A/B: 74HC221; arm key on CLR of both and in series with the driver enables.
- U18/U19: isolated drivers (UCC5350 / ADuM4120) with 10 kΩ **pull-up** on the input, inverting; each with its isolated DC-DC referenced to its FET's source.
- Driver supply: separate 12 V adapter (not the bench bus); the Nucleo's 3.3 V only for logic.
- Option B: FAULT_A / U15A / U16 / U18 dashed "option C only".
- Scope note unchanged (ch1 SYNC, ch2 rack shunt diff probe, ch3 ONSET, ch4 TRIP).

**Power-up order (new, SCHEMATIC_DESIGN §8):** 1 nodes and bench control on USB (TRIP = 0 → breakers close) → 2 driver adapter on → 3 K1 closed, supply output off → 4 supply output on → 5 arm key only for a fault run. Reflash with the supply output off.

## 5. Parts list changes (rev 2)

| row | rev 1 | rev 2 |
|---|---|---|
| 3 | INA240A3 ×3 | **INA240A2** ×3 |
| 9 | 12 × single non-inverting driver | 10 × TC4420 / UCC27517 (loads, Q_f48, Q_f8, spares) + **2 × isolated driver** (UCC5350 / ADuM4120) + **2 × isolated DC-DC 12 → 15 V 1 W** |
| 11 | IRLB3034 ×3 (40 V) | **IRFB4110** ×3 (100 V) — option C only |
| 12 | IRLB8721 / IRLZ44 ×10 | any 40 V ≤ 10 mΩ standard-level part for the five loads; IRFB4110 for Q_f8 (option C) |
| 20 | 74HC123 ×2 | **74HC221** ×2 |
| new | — | **D_fw** Schottky 30 A / few-hundred-A surge ×2; **SMCJ18A** ×2; small Schottky for the feeder coil (C) ×2; **12 V adapter** 2 A; 1 nF C0G ×4; 1 kΩ + BAT54S ×4 for the replay inputs |
| 17 | 10–15 mΩ 5 W ballast | pulse-rated wirewound or copper strip |
| 23 | 20 A fuse "for the 12 V bus" | 20 A fuse at the converter output |

Everything else (shunts, coils, capacitors, load resistors, fault resistors, Nucleos, TCAN1042, OPA2350, converter modules) is unchanged.

## 6. Open for the professor (carried from SCALING_SHEET §9 and HIL_TESTBED_PLAN §5, plus this review)

1. Scope A / B / C — rev 2 is drawn as B with C dashed.
2. The breaker placement and drive (both high-side, isolated drivers, fail-safe by pull-up + inverting).
3. D_fw and the TVS; the 74HC221 one-shot with the arm key on CLR; the separate driver supply; the power-up order.
4. Lab inventory: 48 V supply with CC mode *and* output on/off, scope ≥ 100 MHz, differential probe ≥ 10 MHz, LCR/ESR meter; whether the lab has NUCLEO-H743ZI2 / H723ZG boards now.
5. Supervision and sign-off for fault runs; converter buy-vs-build rule (now five criteria); `load_model = "resistive"` in the core.
