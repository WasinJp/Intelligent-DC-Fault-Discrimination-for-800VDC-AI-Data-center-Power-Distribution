# MODEL.md — 800 VDC Distribution Segment Simulation Model

**Version:** 0.3
**Status:** Single source of truth for the physics model. All simulator code, dataset generation, and proposal claims about the model MUST match this document. Changes require a version bump and an entry in the revision log.
**Project:** Intelligent DC Fault Discrimination for 800 VDC AI Data Center Power Distribution — Delta Cup 2026

---

## 1. Purpose and scope

This document specifies the circuit-level model of a single 800 VDC distribution segment used to:

1. **Quantify the gray zone** — the region of event space where legitimate AI-workload load transients and genuine faults are not separable by simple threshold (magnitude / di/dt) protection.
2. **Generate the labeled event dataset** used to train and validate the discrimination classifier.
3. **Study protection coordination** between the fast analog trip layer and the intelligent discrimination layer.

**In scope (v0.2):** one source converter, one busbar run, one lumped bus node, one aggregated constant-power load bank, one switchable fault branch, one series-arc element (busbar-joint or load-path placement), monopolar 800 V topology, full §5 event taxonomy with composite events, §7 sensor synthesis, §9 gates 1–3.

**Out of scope (v0.2, planned later):** bipolar ±400 V variant, multi-segment tree with distributed per-rack sensing nodes (v0.3 — now motivated by the gate-3 results, see RESULTS.md), Mayr dynamic arc conductance, source-shelf transient-overload timer (OPEN-1), SSCB device thermal model, grounding/insulation-fault modeling, EMI/common-mode effects, benign train periods above 200 ms (dataset limit, §5 note).

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

    L_line · di_L/dt = v_c − R_line · i_L − V_arc(t)·[arc in busbar] − v_bus

**v0.2:** the source shelf is unidirectional — i_L is clamped ≥ 0 (**[OPEN-7]**: explicit output-diode model). Without the clamp an arc striking in the busbar drove i_L to −300 A through the source.

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

Arc inserted in the LOAD path (downstream of C_bus: i_load = P/(v_bus − V_arc)) or in the BUSBAR (upstream of C_bus, §4.2 KVL). Placement is a per-event parameter (`arc_place`) because the two are observed very differently at the feeder sensor (RESULTS.md, Figure 3b):

    V_arc(t) = ( V_arc0 + eta(t) ) · min(1, (t − t_arc)/t_arc_on)

    eta(t): band-limited noise, 1/f-weighted power spectral density over [f_arc_lo, f_arc_hi],
            RMS amplitude = m_arc · V_arc0, regenerated per event from seed.

**v0.2 upgrade path:** Mayr conductance model dg/dt = (g/tau_arc)·(P_arc/P_loss − 1) for ignition/extinction dynamics. Not required for v0.1 classifier work.

---

## 5. Event models (label taxonomy)

Every generated event carries exactly one label and the full parameter draw that produced it.

| Label | Model | Key randomized parameters |
|---|---|---|
| `benign_step` | P(t) = P0 + ΔP·min(1, (t−t0)/t_ramp) | ΔP (±10–80% P_rated), t_ramp (0.5–10 ms) |
| `benign_train` | Two-tier periodic step train (Workload v1) | regime, T₁, duty₁, ΔP₁, ramp₁, j₁; T₂, duty₂, ΔP₂, ramp₂, j₂ — see below |
| `benign_idle_drop` | Fast drop to communication-idle floor | drop fraction (50–85%), t_ramp (1–5 ms) |
| `bolted_pp` | Fault branch, R_f ≤ 20 mΩ | R_f, L_f, t_f (phase vs. workload) |
| `resistive_pp` | Fault branch, 20 mΩ < R_f ≤ 1 Ω | R_f, L_f, t_f |
| `high_z` | Fault branch, 1 Ω < R_f ≤ 10 Ω | R_f, L_f, t_f |
| `series_arc` | Arc element in load path | V_arc0, m_arc, band, onset ramp |

Composite events (fault DURING workload transient) are REQUIRED in the dataset — they are the hardest cases and the honest test. Generation rule: for each fault class, ≥30% of samples have t_f drawn inside an active benign transient window (v0.2 implementation: 35%).

**Workload v1 (two-tier cadence).** Selected by `events.WORKLOAD_VERSION = "v1"`; `"v0.2"` reproduces dataset v0.2 exactly. Sources in EVIDENCE.md.

*Regime* (50/50 per event): **unsmoothed** — steps of 0.30–0.80 p.u. with free ramps 0.5–10 ms (bulk-synchronous training without GPU power smoothing); **smoothed** — GPU power smoothing active (minimum power floor ≤ 90 % TDP, EDP 1.1×): steps 0.10–0.35 p.u. with programmed ramps 2–20 ms.

*Tier 1 — iteration cadence.* Square wave, period T₁ log-uniform 0.3–3 s (the 0.2–3 Hz band of measured training traces; the 10 s tail is out of sweep for compute), duty 0.3–0.7. Rising edges on a phase-locked grid, each perturbed by U(−j, j)·T₁ with j ≤ 2 % (interval jitter, not drift). The event edge carries its own jitter.

*Tier 2 — EDP-peak bursts.* Present with p = 0.6 on periodic backgrounds. Period T₂ log-uniform from 20 ms to min(200 ms, duty·T₁/3); duty 0.3–0.7; amplitude 0.05–0.25 p.u.; ramps 0.5–5 ms; jitter ≤ 2 % of T₂. Bursts exist only inside compute phases and are phase-locked to each phase's start (offset 2–10 % of T₁), i.e. bursts in different compute phases are not coherent modulo T₂.

*Scheduled event.* `benign_train` is the next rising edge of tier 1, or of tier 2 when present (50/50); recorded as `sched_tier`. Other events on periodic backgrounds land at a random phase, ≥ 1.2 ramps from the nearest rising edge of either tier unless `composite` (35 %), in which case inside a ramp.

*Background rule.* `benign_train` always periodic; `benign_step` always flat; all other labels 50/50.

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
| Workload regime | — | — | unsmoothed / smoothed, 50/50 | GPU power smoothing, Choukse et al. §IV-B |
| Iteration period | T₁ | — | 0.3–3 s, log-uniform | measured 0.2–3 Hz training-trace band |
| Iteration duty | duty₁ | — | 0.3–0.7 | — |
| Iteration edge jitter | j₁ | — | 0–2 % of T₁ | working assumption **[OPEN-18]**; not published |
| Iteration step amplitude | ΔP₁ | — | 0.30–0.80 p.u. (unsmoothed) / 0.10–0.35 (smoothed) | regime-dependent |
| Iteration ramp | ramp₁ | — | 0.5–10 ms (unsmoothed) / 2–20 ms (smoothed) | regime-dependent |
| EDP tier present | — | — | p = 0.6 | periodic backgrounds only |
| EDP burst period | T₂ | — | 20 ms – min(200 ms, duty₁·T₁/3), log-uniform | EDP peaks at ~50 ms scale |
| EDP burst amplitude | ΔP₂ | — | 0.05–0.25 p.u. | — |
| EDP burst duty | duty₂ | — | 0.3–0.7 | — |
| EDP burst ramp | ramp₂ | — | 0.5–5 ms | — |
| EDP burst jitter | j₂ | — | 0–2 % of T₂ | per j₁ |

Dropped from v0.2: single period 20–200 ms; per-edge jitter 0–5 %.

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

Two observable streams are produced, mirroring a protection relay:

- **Fast stream:** 2 MSa/s capture buffer, from 0.2 ms before to 5 ms after the event anchor.
- **Slow stream:** 5 kSa/s supervisory log over the whole record (2 kHz anti-alias), ample for ms-scale edge timing across seconds of history. The slow stream is the same sensor averaged down: its additive noise rms is `noise_frac × FS × √(f_slow / f_fast)`. (v0.2 wrote the full sensor rms onto a 50 kSa/s stream, overstating slow-stream noise 6×; that behaviour is retained only under `WORKLOAD_VERSION = "v0.2"`.)

Observables exposed to the classifier: i_L[n], v_bus[n] on those two streams only, plus the segment's configuration ratings (I_rated, V_ref). The classifier NEVER sees hidden states (v_c, i_fault, i_load) or ground truth. Onset detection is done by the feature extractor on the observables, not taken from the truth anchor. Cadence learning is done on the observable slow stream by the feature extractor (v0.3.1): tier 1 by an envelope search (the history smoothed over two periods of the shortest strong cadence, then the longest fundamental), tier 2 from averaged per-compute-phase autocorrelation, edges by a two-level model with onset walk-back, tier-2 phase referenced to the current compute phase only. Nothing in the extractor touches the generating schedule. Feature-extractor behaviour is versioned separately from the physics model (v0.3.1 as of 2026-09-08; see RESULTS.md v1). All feature filtering is **causal**: no feature at decision time t depends on samples after t.

---

## 8. Numerical methods

- Integrator: fixed-step RK4, Numba-JIT (same pattern as `simjoint`).
- **Event-segmented time base (implemented v0.2):** history and post-event segments at Δt = 2 µs (fastest healthy time constant tau_c ≥ 16 µs); event window at Δt = 50 ns from 0.2 ms before to 5 ms after the anchor. Fault branches are active for 5 ms (the SSCB clears by then; the discrimination window is ≤1 ms). Validation (c): the segmented schedule reproduces the uniform 50 ns solution on the stiffest fault-branch case (R_f = 10 Ω, tau_f = 0.2 µs) to 1e-13 RMS.
- **History tier (v0.3):** records longer than `HIST_MARGIN + FINE_PRE` = 200.2 ms before the anchor run the deep history at `DT_HIST = 10 µs`; the final 200 ms before the fine window stay at 2 µs. RK4 at 10 µs is stable for τ_c ≥ 16 µs (dt/τ = 0.6) and resolves the fastest healthy bus resonance (5 kHz) at 20 steps per period. A 7.6 s history costs ~0.75 M steps. Validation (d): compares the tiered schedule against an all-2 µs reference on a two-tier train at baseline parameters and at the stiffest §6 corner (τ_c 16 µs, L 1 µH, C 1 mF, ζ ≈ 0.2), after the 2 kHz slow-stream anti-alias: normalised RMS ≤ 3.5 × 10⁻⁴. 20 µs passes the corner with no margin; 40 µs fails. The tier does not touch the event window.
- Stiffness check: fastest healthy time constant is the L_line–C_bus resonance, f_res = 1/(2π√(L_line·C_bus)) ≈ 712 Hz at baseline; fault-branch front requires the 50 ns step. Δt = 50 ns gives ≥40 steps per fault L_f/R_f time constant at baseline (τ_f = 400 µs for bolted; shortest relevant τ at high-R_f draws checked per draw).
- Determinism: one master seed per event → all stochastic draws (parameters, arc noise, sensor noise) derived via seeded substreams. A dataset sample is fully reproducible from (MODEL.md version, seed).
- Validation of integrator: closed-form checks — (a) RLC discharge of C_bus into R_f–L_f with source disconnected vs. analytic solution, ≤0.1% RMS error; (b) droop steady state v_bus = V_ref − (R_droop + R_line)·I vs. algebra, exact to solver tolerance.

---

## 9. Experiment gates (ordered)

1. **Sanity gate:** healthy-system stability for every parameter draw. v0.2 implements the linearized source-R/L/C/CPL characteristic s² + (R/L − P/(CV²))s + (1/LC)(1 − RP/V²) = 0 with R = R_line + R_droop and requires damping ratio ζ ≥ 0.15 (a designed bus is not marginally damped; a ζ ≈ 0.09 draw rang ±500 A on a high-Z fault). Draws failing the check are logged and excluded (v0.2 dataset: 164 of 1564 draws, 10.5%).
   - **(d) `check_history_tier`** (v0.3): must pass before dataset generation. Four checks total.
2. **Gray-zone study (first result, pre-classifier):** for each event class, compute threshold-detector performance (magnitude, di/dt, and dual-criterion AND) over the sweep. The gray zone = parameter region where no threshold setting achieves both false-trip < 0.1% on benign events and missed-trip < 1% on faults. Output: gray-zone maps per event class. Tests hypothesis H1.
3. **Classifier study:** feature extraction + lightweight classifier on the event dataset; report false-trip rate, missed-detection rate, decision-latency distribution, robustness under held-out parameter regions (domain-shift protocol identical to the arm project's holdout methodology).
   - **Cadence report** (v0.3), emitted at `run_studies.py` startup: tier-1 period within 3 % of truth; tier-2 detection and false-detection counts; scheduled-event phase error by tier (median / p95 / max); alibi coverage (unscheduled events with phase error < 0.05); regime split. Acceptance for dataset v1: tier-1 ≥ 99 %, tier-2 false = 0, scheduled tier-1 max < 0.1.

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
| OPEN-7 | Unidirectional source: replace i_L ≥ 0 clamp with explicit output-diode model | — | before 48 V testbed |
| OPEN-8 | Statistical resolution: 600 benign events cannot measure a 0.1% false-trip rate (1 event = 0.17%). Dataset v1 needs ≥5 000 benign events to resolve the §9 target | — | before proposal claims |
| OPEN-9 | ~~Two-tier workload cadence: iteration-scale envelope carrying sub-iteration steps.~~ **Resolved v0.3** — Workload v1, §5–§6. | — | closed |
| OPEN-10 | ~~Jitter model: independent per-edge ±5 % random walk is not physical.~~ **Resolved v0.3** — interval jitter ≤ 2 % on a phase-locked grid, §5. Two of ten v0.2.2 scheduled-step phase failures were artifacts of the old model, not detection failures. | — | closed |
| OPEN-11 | Sanity-gate censoring: ζ ≥ 0.15 rejects 24 % of 700 kW–1 MW draws vs 2 % of 100–200 kW. Either report the accepted P_rated marginal alongside every p.u. result, or resample to restore the log-uniform marginal. Also: Gate 2 sensitivity row at 99th-percentile thresholds. | — | dataset v1 |
| OPEN-12 | Sample-rate / resolution sensitivity: sweep f_s ∈ {100 k, 250 k, 500 k, 1 M, 2 M} Sa/s × ADC {12, 14, 16} bit on the existing dataset. Determines the testbed acquisition front end. | — | **before testbed hardware selection** |
| OPEN-13 | Managed energy storage on C_bus: rack power shelves now include a charge-management controller over the storage capacitors (GB300-class shelves, ~65 J/GPU). A controlled discharge during a fault sustains it and hides it from the feeder; model as a current-source overlay on C_bus. | — | v0.3 |
| OPEN-14 | Hold-and-confirm decision stage: the residual ~2 % false trips are sharp large benign steps (≥ 0.4 p.u. in < 1 ms) indistinguishable from resistive faults at 1 ms. A benign step settles; a fault does not. Evaluate a second-stage confirmation over 2–5 ms on ambiguous events (I²t budget permits this for high-Z faults). Requires FINE_POST ≥ 5 ms (already true). | — | v0.3 |
| OPEN-15 | Flat-background false cadence: 1 of 682 flat events acquired a learned period after the candidate threshold was lowered to 0.15. Harmless at this rate; monitor at dataset v1-large. | — | dataset v1-large |
| OPEN-16 | Short tier-2 periods (20–30 ms) with multi-ms ramps are barely formed and missed ~5 %. Physically marginal; state as a limit rather than tune. | — | — |
| OPEN-17 | Iteration periods above 3 s (measured up to ~10 s). History cost scales linearly; a 10 s upper bound needs ≈ 2.5 M steps/event. Decide at v1-large. | — | dataset v1-large |
| OPEN-18 | Absolute iteration-edge jitter at rack level is not in the published literature; ≤ 2 % is the working assumption. Ask Delta / measure on the testbed. | — | finalist round |

## 12. Revision log

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-08-13 | Initial draft: topology, state equations, event taxonomy, parameter table, numerical plan, dataset schema |
| 0.1.1 | 2026-08-13 | First implementation feedback: added C_bus ESR (R_esr) and freewheel clamp (OPEN-6) after ideal fault loop rang v_bus to −446 V; documented I_lim hard-clamp behavior (capacitor-backed overload) under OPEN-1; RLC validation window restricted to pre-clamp interval |
| 0.2 | 2026-09-07 | Stage 2. Segmented time base implemented (§8) with validation (c). Series-arc element with busbar/load-path placement (§4.2, §4.6). Unidirectional source clamp (OPEN-7). Sanity gate tightened to ζ ≥ 0.15 (§9). Full §5 taxonomy with background-workload rule and composite events. Sensor synthesis with fast/slow streams (§7). Dataset v0.2 (1 400 events, seed 20260907) and gates 2–3 run: see RESULTS.md. OPEN-8 added. Package restructured to `dcsim/`; all figures regenerated by `scripts/make_figures.py`. |
| 0.2.2 | 2026-09-08 | **No physics change.** Feature extractor and studies revised after a code audit; dataset v0.2 regenerated from seed on a second machine and Gate 2 reproduced exactly. Extractor: `phase_err` rebuilt as full-history folded phase (was bounded at 0.12 by a search-window artifact); two-level edge locator with onset walk-back; prominence-based period estimate; `resid_period` demoted to diagnostic (0.92-collinear with Δi_max); causal spectral filter (was zero-phase; load-path arc detection corrected 51 → 38 %); undetected onsets excluded from training. Studies: 10-seed repeated CV with mean ± std; `has_period` gating tested and rejected; V_ref carried into the feature table; C_bus identified as a second sensing-floor driver. Figures: waveform pairs now drawn from synthesized observables; Figure 2b re-axed to phase error vs step magnitude; Figure 3 gains a C_bus panel. OPEN-9 to OPEN-14 added. See RESULTS.md. |
| 0.3 | 2026-09-08 | **Workload v1** (§5–§6): two-tier cadence — iteration 0.3–3 s + EDP-peak 20–200 ms — with smoothed/unsmoothed regimes and ≤ 2 % interval jitter, sourced in EVIDENCE.md; v0.2 workload retained behind a switch. **Time base** (§8): 10 µs history tier with validation (d) at baseline and stiffest corner. **Sensor** (§7): slow stream 5 kSa/s, noise scaled to bandwidth. **Extractor v0.3.1**: envelope-based tier-1 search, compute-phase tier-2 search, current-phase tier-2 reference, uncapped harmonic filter. Physics core unchanged; dataset v1 generated (1 400 events, seed 20260907). OPEN-9/10 closed; OPEN-15..18 added. See RESULTS.md (v1). |