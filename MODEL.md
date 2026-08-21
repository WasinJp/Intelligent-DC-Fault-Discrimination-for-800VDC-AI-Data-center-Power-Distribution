# MODEL.md — 800 VDC Distribution Segment Simulation Model

**Version:** 0.1.1
**Status:** Single source of truth for the physics model. All simulator code, dataset generation, and proposal claims about the model MUST match this document. Changes require a version bump and an entry in the revision log.
**Project:** Intelligent DC Fault Discrimination for 800 VDC AI Data Center Power Distribution — Delta Cup 2026

---

## 1. Purpose and scope

This document specifies the circuit-level model of a single 800 VDC distribution segment used to:

1. **Quantify the gray zone** — the region of event space where legitimate AI-workload load transients and genuine faults are not separable by simple threshold (magnitude / di/dt) protection.
2. **Generate the labeled event dataset** used to train and validate the discrimination classifier.
3. **Study protection coordination** between the fast analog trip layer and the intelligent discrimination layer.

**In scope (v0.1):** one source converter, one busbar run, one lumped bus node, one aggregated constant-power load bank, one switchable fault branch, monopolar 800 V topology.

**Out of scope (v0.1, planned later):** bipolar ±400 V variant (v0.2), multi-segment tree with distributed sensing nodes (v0.3), Mayr dynamic arc conductance (v0.2), SSCB device thermal model, grounding/insulation-fault modeling, EMI/common-mode effects.

**Design rule carried over from the arm project:** the physics layer is kept pristine and deterministic given a seed; all sensor imperfection lives in a separate synthesis layer (§7). No exceptions.

---

## 2. Segment topology

```
                +-----------+   R_line, L_line   +----------+
   V_ref -----> |  Source   | ---/\/\--- ^^^ --->|  Bus     |----+----------+
   (droop,      | converter |    busbar          |  node    |    |          |
    tau_c)      +-----------+                    |  C_bus   |  CPL load   Fault
                                                 +----------+  bank       branch
                                                                P(t)/v     R_f, L_f
                                                                           (+ arc)
```

Five lumped elements:

| Element | Represents |
|---|---|
| Source converter | SST output stage / 800 V power shelf group with droop control and finite control bandwidth |
| Busbar (R_line, L_line) | Copper busway run from shelf to rack segment |
| Bus node (C_bus) | Aggregate DC-link + capacitance-shelf energy storage at the rack interface |
| CPL load bank | Aggregated rack DC-DC converters, drawing constant power with slew limit and UVLO |
| Fault branch | Switchable series R_f + L_f path across the bus; optionally contains the series-arc element in the load path |

---

## 3. Notation

| Symbol | Meaning | Unit |
|---|---|---|
| v_c | Converter internal voltage command (state) | V |
| i_L | Line (busbar) current (state) | A |
| v_bus | Bus node voltage (state) | V |
| i_load | CPL bank current draw | A |
| i_fault | Fault branch current (state, when branch active) | A |
| P(t) | Commanded load power profile | W |
| V_ref | Nominal bus voltage setpoint | V |
| R_droop | Droop resistance (voltage sag per amp of share) | Ω |
| tau_c | Converter control time constant (1 / control bandwidth × 2π approx.) | s |
| V_uvlo | Load undervoltage-lockout threshold | V |
| V_arc0 | Static arc voltage (Stokes–Oppenlander regime) | V |
| eta(t) | Stochastic arc noise process | V |

Sign convention: current positive from source toward bus; i_fault positive into the fault branch.

---

## 4. State equations

### 4.1 Source converter (droop + first-order control lag)

    dv_c/dt = ( V_ref − R_droop · i_L − v_c ) / tau_c

Rationale: the converter regulates toward a droop-adjusted setpoint but with finite bandwidth. This equation is the origin of the primary discriminant: under a load step the converter succeeds in holding v_bus (sag ≈ R_droop·ΔI plus a transient governed by tau_c and C_bus); under a fault the converter is bandwidth- and current-limited and v_bus collapses.

**v0.1 simplification:** no explicit source current limit. A current-limit clamp i_L ≤ I_lim (with I_lim = 1.5–2.0 × I_rated) SHOULD be added before dataset generation for fault realism; flagged as **[OPEN-1]**.

### 4.2 Busbar

    L_line · di_L/dt = v_c − R_line · i_L − v_bus

### 4.3 Bus node (KCL, with capacitor ESR)

State is the capacitor voltage v_C; the bus node voltage is algebraic:

    C_bus · dv_C/dt = i_C            where  i_C = i_L − i_load − i_fault
    v_bus = max( v_C + R_esr · i_C , 0 )

The max(·, 0) is the freewheel clamp: converter output-stage body diodes pin the
node at ~0 V during capacitor-discharge ring-back; v_C is likewise clamped ≥ 0
(**[OPEN-6]**: replace with explicit diode branch model). Without ESR + clamp the
ideal underdamped C–L_f–R_f loop rings v_bus to large negative values, which is
unphysical for a converter-terminated bus.

### 4.4 Constant-power load bank

    i_load = P(t) / max(v_bus, V_uvlo_floor)        with UVLO shedding:

    if v_bus < V_uvlo for longer than t_uvlo_delay:  P(t) → 0 (load shed)
    recovery: load re-ramps at S_P after v_bus > V_uvlo + V_hyst for t_recover

The UVLO shed is itself a discriminating signature: during genuine voltage collapse the load current *disappears*; during a benign step it never does.

Small-signal note (for proposal §stability): linearized CPL incremental resistance is

    r_cpl = − v_bus² / P

At P = 200 kW, v_bus = 800 V: r_cpl = −3.2 Ω. Healthy-system stability MUST be verified against the Middlebrook / impedance-ratio condition for every parameter draw before events are injected (sanity gate, §9).

### 4.5 Fault branch (when active)

    L_f · di_fault/dt = v_bus − R_f · i_fault − V_arc(t)·[arc present]

Initial fault front (arc absent, i_fault = 0⁺):

    di_fault/dt |_(t=t_f) = v_bus(t_f) / L_f

### 4.6 Series arc element (v0.1: static + stochastic)

Arc inserted in the LOAD path (series arc) or fault branch (arcing fault):

    V_arc(t) = V_arc0 + eta(t)

    eta(t): band-limited noise, 1/f-weighted power spectral density over [f_arc_lo, f_arc_hi],
            RMS amplitude = m_arc · V_arc0, regenerated per event from seed.

**v0.2 upgrade path:** Mayr conductance model dg/dt = (g/tau_arc)·(P_arc/P_loss − 1) for ignition/extinction dynamics. Not required for v0.1 classifier work.

---

## 5. Event models (label taxonomy)

Every generated event carries exactly one label and the full parameter draw that produced it.

| Label | Model | Key randomized parameters |
|---|---|---|
| `benign_step` | P(t) = P0 + ΔP·min(1, (t−t0)/t_ramp) | ΔP (±10–80% P_rated), t_ramp (0.5–10 ms) |
| `benign_train` | Periodic step train, iteration cadence | period (20 ms–2 s), duty, shape jitter ≤5%, amplitude |
| `benign_idle_drop` | Fast drop to communication-idle floor | drop fraction (50–85%), t_ramp (1–5 ms) |
| `bolted_pp` | Fault branch, R_f ≤ 20 mΩ | R_f, L_f, t_f (phase vs. workload) |
| `resistive_pp` | Fault branch, 20 mΩ < R_f ≤ 1 Ω | R_f, L_f, t_f |
| `high_z` | Fault branch, 1 Ω < R_f ≤ 10 Ω | R_f, L_f, t_f |
| `series_arc` | Arc element in load path | V_arc0, m_arc, band, onset ramp |

Composite events (fault DURING workload transient) are REQUIRED in the dataset — they are the hardest cases and the honest test. Generation rule: for each fault class, ≥30% of samples have t_f drawn inside an active benign transient window.

---

## 6. Parameter table (v0.1 baseline + sweep ranges)

All values are declared assumptions pending literature anchoring; each row cites its anchor class. Changing a baseline value = version bump.

| Parameter | Symbol | Baseline | Sweep range | Anchor |
|---|---|---|---|---|
| Nominal bus voltage | V_ref | 800 V | 760–840 V | NVIDIA monopolar architecture |
| Segment rated power | P_rated | 200 kW | 100 kW–1 MW | shelf group → full rack |
| Rated current | I_rated | 250 A | derived | P_rated / V_ref |
| Droop resistance | R_droop | 16 mΩ (0.5%) | 0.2–5% of V_ref/I_rated | OCP droop-sharing requirement |
| Converter control time constant | tau_c | 80 µs (~2 kHz BW) | 16–320 µs | typical DC-DC voltage-loop BW |
| Bus capacitance | C_bus | 10 mF | 1–50 mF | DC-link + capacitance shelf; ~65 J/GPU embedded storage scale |
| Busbar inductance | L_line | 5 µH | 1–50 µH | 0.1–1 µH/m × 5–50 m |
| Busbar resistance | R_line | 5 mΩ | 1–20 mΩ | copper busway, segment length |
| Bus capacitor ESR | R_esr | 8 mΩ | 2–20 mΩ | electrolytic bank ESR, aggregate |
| Load slew (bus level) | S_P | 100 kW / 2 ms | 10 kW/ms–1 MW/ms | OCP <2 ms, 175–180% TDP step |
| Max transient overload | — | 180% TDP | 150–200% | OCP/Meta dynamic-loading spec |
| Fault resistance | R_f | 5 mΩ | 1 mΩ–10 Ω | bolted → high-impedance sweep |
| Fault loop inductance | L_f | 2 µH | 0.5–10 µH | fault position along busbar |
| Arc static voltage | V_arc0 | 25 V | 15–40 V | Stokes–Oppenlander, mm-scale gaps |
| Arc noise modulation | m_arc | 15% | 5–25% | PV/aero arc-detection literature |
| Arc noise band | [f_arc_lo, f_arc_hi] | 1–100 kHz | up to 1 MHz | detection-band practice |
| UVLO threshold | V_uvlo | 640 V (80%) | 600–700 V | typical converter UVLO |
| UVLO delay / hysteresis | t_uvlo_delay, V_hyst | 100 µs, 20 V | — | assumption **[OPEN-2]** |
| Source current limit | I_lim | 1.75 × I_rated | 1.5–2.0× | assumption **[OPEN-1]**; NOTE: modeled as a hard clamp in v0.1.1, so sustained load above I_lim drains C_bus (linear v_bus ramp-down). Real shelves allow 175–180% *transient* overload backed by energy storage; a thermal-limit timer model is part of OPEN-1 |
| Sensor sample rate | f_s | 2 MSa/s | 1–10 MSa/s | arc-band Nyquist + margin |
| ADC resolution | — | 14 bit | 12–16 bit | acquisition front-end study |
| Sensor noise | — | 0.1% FS RMS | 0.05–0.5% | acquisition front-end study |

### 6.1 Derived sanity numbers (baseline draw)

- Bolted-fault initial front: v_bus / L_f = 800 / 2 µH = **400 A/µs**
- Fastest benign bus-level slew: 100 kW / 2 ms at 800 V ≈ 62.5 A/ms ≈ **0.06 A/µs**
- Separation at bus level for bolted faults: ~4 orders of magnitude → **bolted faults are threshold-separable at bus level.**
- Working hypothesis **[H1]**: the bus-level gray zone is dominated by `high_z`, `series_arc`, and composite events — NOT bolted shorts. The widely quoted >3 kA/µs figure is a core-delivery (downstream of rack conversion) projection and does not apply to this bus. The gray-zone study (§9) tests H1 quantitatively.

---

## 7. Sensor synthesis layer

Applied to pristine physics output, in order:

1. Anti-alias filter (4th-order Butterworth, f_c = 0.4 · f_s)
2. Decimation to f_s
3. Additive sensor noise (white, RMS per table)
4. ADC quantization (mid-tread, per resolution)
5. Optional channel latency skew between i and v channels (≤1 µs, **[OPEN-3]**: measure realistic skew for chosen front-end)

Observables exposed to the classifier: i_L[n], v_bus[n] only. The classifier NEVER sees hidden states (v_c, i_fault) or ground truth.

---

## 8. Numerical methods

- Integrator: fixed-step RK4, Numba-JIT (same pattern as `simjoint`).
- **Event-segmented time base:** quiescent segments at Δt = 1 µs; event windows at Δt = 50 ns from 10 ms before to 50 ms after each injected event (window edges configurable per event class).
- Stiffness check: fastest healthy time constant is the L_line–C_bus resonance, f_res = 1/(2π√(L_line·C_bus)) ≈ 712 Hz at baseline; fault-branch front requires the 50 ns step. Δt = 50 ns gives ≥40 steps per fault L_f/R_f time constant at baseline (τ_f = 400 µs for bolted; shortest relevant τ at high-R_f draws checked per draw).
- Determinism: one master seed per event → all stochastic draws (parameters, arc noise, sensor noise) derived via seeded substreams. A dataset sample is fully reproducible from (MODEL.md version, seed).
- Validation of integrator: closed-form checks — (a) RLC discharge of C_bus into R_f–L_f with source disconnected vs. analytic solution, ≤0.1% RMS error; (b) droop steady state v_bus = V_ref − (R_droop + R_line)·I vs. algebra, exact to solver tolerance.

---

## 9. Experiment gates (ordered)

1. **Sanity gate:** healthy-system stability for every parameter draw (Middlebrook check + no-event simulation shows bounded, settling response). Draws failing the check are logged and excluded (they represent mis-designed systems, not events).
2. **Gray-zone study (first result, pre-classifier):** for each event class, compute threshold-detector performance (magnitude, di/dt, and dual-criterion AND) over the sweep. The gray zone = parameter region where no threshold setting achieves both false-trip < 0.1% on benign events and missed-trip < 1% on faults. Output: gray-zone maps per event class. Tests hypothesis H1.
3. **Classifier study:** feature extraction + lightweight classifier on the event dataset; report false-trip rate, missed-detection rate, decision-latency distribution, robustness under held-out parameter regions (domain-shift protocol identical to the arm project's holdout methodology).

---

## 10. Dataset schema (HDF5)

```
/session_meta          model_version, master_seed, generation timestamp, git hash
/events/<event_id>/
    waveforms/         i_L, v_bus (post-synthesis), float32, @ f_s
    truth/             pristine i_L, v_bus, i_fault, v_c @ physics rate (optional, debug only)
    label              one of §5 taxonomy
    params             full parameter draw (all §6 symbols)
    windows            event onset index, pre/post window lengths
```

Classifier training MUST use `/waveforms` only. `/truth` is retained for debugging and figure generation and MUST be excluded from any training pipeline.

---

## 11. Open items

| ID | Item | Owner | Target |
|---|---|---|---|
| OPEN-1 | Source current-limit clamp model and I_lim anchoring | — | before dataset v1 |
| OPEN-2 | UVLO delay/hysteresis values from real converter datasheets | — | before dataset v1 |
| OPEN-3 | Realistic i/v channel skew for candidate front-end | — | before 48 V testbed design |
| OPEN-4 | ±400 V bipolar variant equations (v0.2) | — | post-proposal |
| OPEN-5 | Mayr arc upgrade decision after v0.1 classifier results | — | post-proposal |
| OPEN-6 | Replace freewheel clamp (v_C, v_bus ≥ 0) with explicit diode branch | — | before dataset v1 |

## 12. Revision log

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-08-13 | Initial draft: topology, state equations, event taxonomy, parameter table, numerical plan, dataset schema |
| 0.1.1 | 2026-08-13 | First implementation feedback: added C_bus ESR (R_esr) and freewheel clamp (OPEN-6) after ideal fault loop rang v_bus to −446 V; documented I_lim hard-clamp behavior (capacitor-backed overload) under OPEN-1; RLC validation window restricted to pre-clamp interval |
