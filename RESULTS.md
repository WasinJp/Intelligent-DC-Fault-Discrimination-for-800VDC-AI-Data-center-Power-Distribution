# RESULTS.md — Gates 2 and 3 on dataset v1 (workload v1, feature extractor v0.3.1)

**Dataset:** `data/events_v1.h5`, MODEL.md v0.3, workload v1, master seed 20260907, 200 events per class × 7 classes = 1 400 events (600 benign, 600 trip-class faults, 200 series arcs). Regenerate with `python scripts/generate_dataset.py data/events_v1.h5` (≈ 30 min), features and studies with `python scripts/run_studies.py data/events_v1.h5`, figures with `python scripts/make_figures.py data/events_v1.h5`. Physics core unchanged since v0.2; dataset v0.2 remains reproducible via `events.WORKLOAD_VERSION = "v0.2"`.

**What v1 changes (EVIDENCE.md).** The workload is now two-tier and sourced: an iteration cadence of 0.3–3 s (published lockstep measurements: Microsoft/OpenAI/NVIDIA arXiv:2508.14318; Oracle; grid-resonance studies) carrying EDP-peak bursts of 20–200 ms inside compute phases (the "electrical design power" overshoots the same paper describes at 50 ms scale). Two benign regimes, 50/50: unsmoothed (idle-to-near-TDP steps, 0.5–10 ms ramps) and smoothed (GPU power smoothing active: 0.10–0.35 p.u. steps, 2–20 ms programmed ramps). Edge jitter ≤ 2 % on a phase-locked grid. Scheduled events land on a tier-1 or tier-2 edge (`sched_tier`). Slow stream 5 kSa/s with sensor noise scaled to its bandwidth.

**Honest scope:** every number below is on *synthetic* events from a single-segment lumped model. Sweep ranges are wide on purpose. The 48 V testbed is what turns these into measured numbers.

---

## Cadence learning on the observables (v0.3.1 extractor)

The relay learns the workload cadence from the slow-stream current only; nothing here touches the schedule that generated it.

| | result |
|---|---|
| tier-1 (iteration) period within 3 % | 1 400 / 1 400 |
| tier-2 (EDP) period found where present | 404 / 423 (95.5 %), 0 false detections |
| scheduled events on tier 1 (n = 143): phase error median / p95 / max | 0.008 / 0.031 / 0.074 |
| scheduled events on tier 2 (n = 57) | 0.009 / 0.099 / 0.147 |
| unscheduled events on periodic backgrounds: median phase error | 0.14–0.20 by class |
| alibi coverage: unscheduled events with phase error < 0.05 | 20.5 % (one uniform tier: 10 %; two tiers with `min`: 19 %) |
| false cadence on flat backgrounds | 1 / 682 |

`phase_err` is the distance from event onset to the nearest predicted rising edge of *either* learned tier, folded to [0, 0.5]. The second tier roughly doubles alibi coverage; it is kept because tier 1 alone is measurably worse (10-seed CV: missed 2.87 vs 2.58 %, high-Z 8.60 vs 7.75 %). `phase_err = min(tier 1, tier 2)` outperformed split-tier features (which trade false trips for missed faults with wider spread).

**What the feature measures.** It separates *scheduled* from *unscheduled* events, not benign from fault. `benign_idle_drop` — benign but unscheduled — sits at median 0.139, where faults are. The claim the data supports: *a scheduled workload step arrives on time whatever its size; a fault does not.*

## Gate 2 — the gray zone is high-impedance faults (Figure 1)

Conventional Layer-1 detectors on line current and bus voltage, thresholds at the edge of the benign envelope (zero false trips on 600 benign transients):

| detector | bolted missed | resistive missed | high-Z missed |
|---|---|---|---|
| magnitude | 16 % | 16 % | 73 % |
| di/dt | 0.5 % | 17 % | 85 % |
| v-collapse | 0 % | 4.5 % | 84.5 % |
| **all three (OR) — Layer 1** | **0 %** | **0 %** | **66.5 %** |

- 66.5 % of high-Z fault events lie inside the benign envelope on all three axes; 22 % of all trip-class faults do.
- No threshold setting reaches the targets (false trip < 0.1 %, missed < 1 %); `targets_reachable = False` over a 41×41 sweep.
- The gray zone is slightly narrower than on v0.2 (72.5 %) because the smoothed regime lowers the largest benign step (envelope Δi_max 0.84 vs 0.96 p.u.). Two thirds of high-Z faults remain inside it.
- *Robustness note:* thresholds are set at the maximum of 600 benign events — by a single outlier. Most pessimistic conventional baseline; 99th-percentile sensitivity row is OPEN-11.

## Gate 3 — the discriminator (Figure 2)

Gradient-boosted trees on observable-stream features only, 1 ms decision window, TRIP / HOLD / ALERT. Undetected onsets (6 of 1 400, all load-path arcs) are excluded from training and scored HOLD.

**Feature groups.** CONV: Δi, max|Δi|, max di/dt. PHYS: early voltage lead, early current, dynamic resistance, sag, minimum voltage, collapse flag, rise time, 1–100 kHz spectral floor (causal). WORK: `has_period`, `period_strength`, `phase_err`.

### Repeated cross-validation — the table to quote

5-fold stratified CV over 10 fold seeds; mean ± std in %.

| feature set | false trips | faults missed | high-Z missed | periodic bg: FT / missed | flat bg: FT / missed |
|---|---|---|---|---|---|
| conventional | 9.90 ± 0.76 | 10.58 ± 0.66 | 31.65 ± 1.90 | 9.15 / 10.82 | 10.68 / 10.34 |
| + v–i physics | 2.55 ± 0.47 | 4.02 ± 0.38 | 12.05 ± 1.13 | 2.36 / 4.22 | 2.75 / 3.81 |
| **+ workload-aware** | **1.48 ± 0.22** | **2.43 ± 0.20** | **7.30 ± 0.60** | **0.95 / 1.24** | 2.03 / 3.67 |

- Workload-awareness improves every aggregate column over physics alone: false trips −1.07, missed −1.59, high-Z −4.75 points. Each is four to five standard deviations.
- On periodic backgrounds — the events the feature is designed for — false trips fall 2.36 → 0.95 and missed faults 4.22 → 1.24, a 3.4× reduction.
- On flat backgrounds (no cadence to learn) the workload features cost nothing: false trips 2.75 → 2.03, missed 3.81 → 3.67. The +0.7-point flat-background cost seen on dataset v0.2 did not reproduce.

### Single-seed ablation (seed 0)

| feature set | false trips | faults missed | high-Z missed | composite missed |
|---|---|---|---|---|
| conventional | 9.0 % | 10.7 % | 31.5 % | 14.2 % |
| + v–i physics | 2.2 % | 3.8 % | 11.5 % | 4.0 % |
| + workload-aware | 1.5 % | 2.5 % | 7.5 % | 4.0 % |

### Operating curve (Figure 2c)

At zero false trips on 600 benign events the classifier misses 10.2 % of faults (high-Z 29.5 %), against 22.2 % (high-Z 66.5 %) for the best conventional detector at the same budget. This point is pinned by the single most fault-like benign event and only a larger benign set moves it (OPEN-8).

### Domain shift (train < 400 kW, test ≥ 400 kW; single fit, 481 events)

| feature set | false trips | faults missed | high-Z missed |
|---|---|---|---|
| conventional | 10.2 % | 19.6 % | 58.0 % |
| + physics | 3.2 % | 4.9 % | 14.5 % |
| + workload-aware | 1.9 % | 4.9 % | 14.5 % |

Missed-fault columns are identical for the last two rows: 20 predictions differ and the counts cancel. Single fit; directional only. No domain-shift gain in missed faults from workload-awareness on this dataset.

### Decision latency (Figure 4a)

| window | false trips | faults missed | high-Z missed | arcs flagged |
|---|---|---|---|---|
| 0.25 ms | 1.3 % | 2.3 % | 7.0 % | 70 % |
| 0.5 ms | 2.0 % | 2.3 % | 7.0 % | 76.5 % |
| 1.0 ms | 1.5 % | 2.5 % | 7.5 % | 80.5 % |

TRIP decisions are fully available at 0.25 ms. ALERT (arc) decisions benefit from the longer window because the spectral features integrate. The two decisions have different natural latencies; the architecture should let them.

### Gating — tested and rejected

Two models routed on `has_period`: ties the single model on periodic backgrounds (1.0 / 1.3 %) and is worse on flat ones (3.1 vs 2.0 % false trips). Halving the training data per route costs more than four NaN columns. Retained as `studies.GATED`; revisit at ≥ 5 000 events.

## Where feeder-level sensing ends (Figure 3)

Two independent physical drivers, both pointing to per-rack sensing nodes.

**(a) Fault current in p.u. of segment rating.** High-Z misses: 23 % below 0.15 p.u. (n = 13), 20 % at 0.15–0.3, 5.9 % at 0.3–0.6, 3.6 % above 0.6. *The lowest bin is 13 events; read it as "about a fifth".*

**(b) Bus capacitance.**

| C_bus tercile (median) | high-Z missed |
|---|---|
| 2.4 mF | **0.0 %** |
| 10.7 mF | 4.5 % |
| 30.2 mF | **17.9 %** |

A 30 mF bus into a 10 Ω fault has an R·C time constant of 300 ms: the capacitor holds bus voltage and feeds the fault locally; the feeder sees only the converter's droop response — a smeared ramp, not a front. Zero misses on low-capacitance buses; one in six on high-capacitance ones.

This is the industry direction. Rack power shelves are adding stored energy on the DC side to ride through lockstep transients (NVIDIA GB300 NVL72 shelf: electrolytic storage in half the shelf volume, ~65 J/GPU, with a charge-management controller; Delta 800 VDC in-row rack: 80 kW BBU embedded in each of six 110 kW shelves, 480 kW per rack). Stored energy that smooths a workload step also feeds a small fault locally and hides it from the feeder. **Feeder-level fault detection gets harder by design as the architecture matures.** Per-rack sensing is where the trend forces the design.

**(c) Series arcs.** 96.8 % of busbar-joint arcs (upstream of C_bus) are flagged; **66.4 %** of load-path arcs (downstream of C_bus). On flat backgrounds load-path arcs are flagged 58 %; on periodic backgrounds ~72 %, because an arc at random phase has no scheduler alibi. *Corrected from 38 % on dataset v0.2:* the v0.2 20–200 ms train buried the arc's 0.02 p.u. current step in background transients; the quiet iteration-scale train does not. The classifier uses that small DC step, not the 1–100 kHz arc noise, which the L_line–C_bus divider attenuates by ~(f_res/f)². Load-path arcs at the feeder are **weak** evidence, not absent evidence: 58–66 % against 97 % for busbar arcs.

**Conclusion:** feeder-level sensing is the right place for Layer 1 and for busbar faults. Small faults on heavily-buffered segments and load-side arcs need per-rack nodes. The v0.4 multi-segment model and the 48 V testbed should both include one.

## What changed since RESULTS.md v0.2.2 (physics unchanged)

| item | v0.2.2 | v1 / v0.3.1 |
|---|---|---|
| workload | single 20–200 ms train, per-edge jitter ≤ 5 %, event edge unjittered | two-tier (iteration 0.3–3 s + EDP 20–200 ms), two regimes, interval jitter ≤ 2 %, event edge jittered — EVIDENCE.md |
| history | ≤ 0.52 s at 2 µs | ≤ 7.6 s: 10 µs history tier + last 200 ms at 2 µs; validation (d) at baseline and stiffest sweep corner |
| slow stream | 50 kSa/s, full sensor rms | 5 kSa/s, rms scaled by √(bandwidth ratio) |
| cadence estimator | one tier, single autocorrelation peak | envelope search for tier 1; tier 2 from compute-phase segments; tier-2 phase from the current phase only |
| workload-aware gain (10 seeds) | −0.30 FT / −1.15 missed / −3.45 high-Z | **−1.07 / −1.59 / −4.75** |
| periodic-background missed | 4.35 → 1.47 | 4.22 → 1.24 |
| flat-background cost | +0.7 FT | none |
| load-path arcs flagged | 38 % | 66 % (see (c)) |

## Limitations that must be stated in any claim

1. **Statistical resolution (OPEN-8):** 600 benign events cannot measure a 0.1 % false-trip rate. "Zero false trips" means 0 of 600; the zero-false-trip operating point is set by one event.
2. **Workload model:** sourced but still synthetic. Iteration periods above 3 s are out of sweep (compute). Absolute iteration-edge jitter at rack level is not published; ≤ 2 % is the working assumption. Tier-2 bursts with 20–30 ms periods and multi-ms ramps are barely formed and are missed ~5 % of the time.
3. **Alibi coverage:** two learned tiers put 20 % of the timeline within a scheduler alibi. The classifier still improves because magnitude features override it, but a fault that happens to coincide with a scheduled edge is the residual weakness by construction.
4. Single lumped segment, monopolar. No bipolar ±400 V, no multi-segment coordination, no managed energy-storage controller on C_bus (OPEN-13 — expected to worsen the feeder's view).
5. Sanity gate under-samples the largest segments (OPEN-11).
6. Classifier untuned. The 0.1 % / 1 % targets are not demonstrated by any configuration.
7. Series arc: static Stokes–Oppenlander + noise; no ignition/extinction dynamics.
8. All timings assume a 2 MSa/s, 12–16-bit front end with no i/v channel skew (OPEN-3). Sample-rate sensitivity not yet studied (OPEN-12); it determines the testbed front end.
