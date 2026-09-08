# RESULTS.md — Gate 2 and Gate 3 on dataset v0.2 (feature extractor v0.2.2)

**Dataset:** `data/events_v0.2.h5`, MODEL.md v0.2, master seed 20260907, 200 events per class × 7 classes = 1 400 events (600 benign, 600 trip-class faults, 200 series arcs). 164 system draws rejected by gate 1 (ζ < 0.15). The dataset was regenerated from seed on a second machine (Windows, Python 3.12.7, fresh environment) on 2026-09-08 and reproduced the v0.2 Gate 2 table to every reported decimal.

**Feature extractor:** v0.2.2 (`dcsim/features.py`). Physics core and sensor synthesis are unchanged from v0.2; every difference from the previous RESULTS.md comes from the feature extractor and the study code. See §"What changed since v0.2".

**Honest scope:** every number below is on *synthetic* events from a single-segment lumped model. Sweep ranges are wide on purpose (sensor noise 0.05–0.5 % FS, benign ramps 0.5–10 ms, segments 100 kW–1 MW, 35 % of faults inside an active workload transient). The 48 V testbed (final round) is what turns these into measured numbers.

---

## Gate 2 — the gray zone is real and it is high-impedance faults (Figure 1)

Conventional Layer-1 detectors on the observable line current and bus voltage, each threshold set at the edge of the benign envelope (**zero false trips on 600 benign transients**). Unchanged from v0.2 (these detectors use only magnitude, di/dt and voltage-sag features, none of which were touched).

| detector | bolted missed | resistive missed | high-Z missed |
|---|---|---|---|
| magnitude | 19 % | 28 % | 83 % |
| di/dt | 1.5 % | 19 % | 88 % |
| v-collapse | 0 % | 6 % | 85.5 % |
| **all three (OR) — Layer 1** | **0 %** | **3.5 %** | **72.5 %** |

- 72.5 % of high-Z fault events lie *inside* the benign envelope on all three axes (Figure 1a). 25 % of all trip-class faults do.
- No threshold setting reaches the MODEL.md targets (false trip < 0.1 % and missed < 1 %) — `targets_reachable = False` over a 41×41 sweep.
- Hypothesis H1 confirmed: bolted faults are threshold-separable; the ambiguous zone is high-Z (and to a small degree resistive) faults. Bolted fronts are ~400 A/µs at bus level, limited by L_f; the widely quoted >3 kA/µs figure is a core-delivery projection and never appears on this bus.
- *Robustness note:* the "zero false trip" thresholds are set at the maximum of 600 benign events, i.e. by a single outlier. This is the most conservative conventional setting and therefore the most pessimistic baseline. A sensitivity row at the 99th percentile is on the to-do list (OPEN-11).

## Gate 3 — the discriminator (Figure 2)

Gradient-boosted trees on features computed from the observable streams only, 1 ms decision window, three decision classes (TRIP / HOLD / ALERT). Events whose onset was never detected on the observables (6 of 1 400, all load-path series arcs) are excluded from training and scored as HOLD.

**Feature groups.** CONV: Δi, max|Δi|, max di/dt. PHYS: early voltage lead, early current, dynamic resistance, sag, minimum voltage, collapse flag, rise time, 1–100 kHz spectral floor (causal filter). WORK: `has_period`, `period_strength`, `phase_err` — the phase distance from event onset to the nearest edge predicted by the learned scheduler cadence, folded to [0, 0.5].

### Repeated cross-validation — the table to quote

5-fold stratified CV repeated over 10 fold seeds; mean ± std in %.

| feature set | false trips | faults missed | high-Z missed | periodic bg: FT / missed | flat bg: FT / missed |
|---|---|---|---|---|---|
| conventional | 10.50 ± 0.72 | 12.70 ± 0.65 | 36.15 ± 1.76 | 12.03 / 11.93 | 8.92 / 13.50 |
| + v–i physics | 2.43 ± 0.41 | 4.38 ± 0.22 | 13.15 ± 0.67 | 2.16 / 4.35 | 2.71 / 4.42 |
| **+ workload-aware** | **2.13 ± 0.39** | **3.23 ± 0.27** | **9.70 ± 0.81** | **0.92 / 1.47** | 3.39 / 5.07 |

- Workload-awareness improves every aggregate column over physics alone. The missed-fault and high-Z improvements are about four standard deviations.
- On periodic backgrounds — the events the feature is designed for — false trips fall 2.16 → 0.92 and missed faults 4.35 → 1.47, a threefold reduction.
- On flat backgrounds (no cadence to learn) the workload features cost about +0.7 pt false trips and +0.65 pt missed. This is ~1.5σ and was not removed by imputation; it is reported as a bounded cost, not engineered away.

### Single-seed ablation (seed 0, for continuity with v0.2)

| feature set | false trips | faults missed | high-Z missed | composite missed |
|---|---|---|---|---|
| conventional | 10.7 % | 14.3 % | 40.0 % | 12.8 % |
| + v–i physics | 3.2 % | 4.7 % | 14.0 % | 4.1 % |
| + workload-aware | 2.7 % | 3.5 % | 10.5 % | 4.6 % |

### What `phase_err` measures

Median phase error by class on periodic backgrounds: scheduled steps (`benign_train`) **0.016**; every other class 0.14–0.23, consistent with uniform random phase. AUC of `phase_err` alone, scheduled vs everything else: 0.84 (v0.2.1 extractor; higher with v0.2.2).

**The feature separates *scheduled* from *unscheduled* events, not benign from fault.** An unscheduled benign event (`benign_idle_drop`, median 0.167) correctly has no scheduler alibi and lands where faults do. The claim the data supports is: *a scheduled workload step arrives on time whatever its size, and a fault does not.*

### Operating curve (Figure 2c)

Sweeping the TRIP probability threshold: at zero false trips on 600 benign events the classifier misses 11.2 % of faults (high-Z: 32.5 %), against 25.3 % (high-Z: 72.5 %) for the best conventional detector at the same budget. This operating point is pinned by the single most fault-like benign event in the dataset (a 0.44 p.u. step in 0.7 ms) and did not move between extractor versions; only a larger benign set moves it (OPEN-8).

### Domain shift (train < 400 kW, test ≥ 400 kW; single fit)

| feature set | false trips | faults missed | high-Z missed |
|---|---|---|---|
| + physics | 3.7 % | 8.3 % | 24.6 % |
| + workload-aware | 2.3 % | 7.4 % | 21.7 % |

Improves on all three, but this is one fit on 481 held-out events (216 benign): 2.3 % is five events. Directional only.

### Decision latency (Figure 4a)

Faults missed is **3.5 % at 0.25, 0.5 and 1.0 ms** — identical. False trips 3.0 / 2.2 / 2.7 %. Everything the classifier uses is available 0.25 ms after onset; the window is not the bottleneck.

### Gating — tested and rejected

Routing events to two separate models on `has_period` (cadence / no cadence) was tested over 10 seeds and is worse than physics-only on every metric (missed +0.30, high-Z +0.90). Halving the training data per route costs more than removing NaN columns gains at n = 1 400. The code path is retained (`studies.GATED`) for reproducibility; revisit at dataset v1.

## Where the sensing point can and cannot see (Figure 3) — resolves feeder vs. per-rack

Two independent physical drivers, both pushing toward per-rack sensing nodes.

**(a) Fault current relative to segment rating.** High-Z misses by fault current in p.u. of rated current: 27 % below 0.15 p.u. (n = 11), 26 % at 0.15–0.3, 11 % at 0.3–0.6, 4.5 % above 0.6. A 10 Ω fault at 800 V is 80 A: 6 % of a 1 MW segment's rating, 32 % of a 200 kW segment's. *The lowest bin is 11 events and should be read as "about a quarter", not "27 %".*

**(b) Bus capacitance.** High-Z misses by C_bus tercile:

| C_bus tercile (median) | high-Z missed |
|---|---|
| 2.4 mF | **1.5 %** |
| 10.7 mF | 10.6 % |
| 30.2 mF | **19.4 %** |

A 30 mF bus into a 10 Ω fault has an R·C time constant of 300 ms: the capacitor holds bus voltage and feeds the fault locally, and the feeder sees only the converter's droop response through τ_c — a smeared ramp, not a front. Missed high-Z events sit on top of `benign_step` on every physics axis. This is the same mechanism that hides load-side arcs.

This finding has an industry-direction consequence. Rack power shelves are adding energy storage specifically to ride through lockstep workload transients (NVIDIA GB300 NVL72 power shelf with LITEON: electrolytic storage occupying half the PSU volume, ~65 J per GPU). Every joule added to smooth a workload step also feeds a small fault locally and hides it from the feeder sensor. **Feeder-level fault detection gets harder by design as the architecture matures.** Per-rack sensing is where the trend forces the design, not a refinement.

**(c) Series arcs.** 95.5 % of busbar-joint arcs (upstream of C_bus) are flagged; **38.2 %** of load-path arcs (downstream of C_bus). *Corrected from 51 % in v0.2:* the earlier figure was inflated by a non-causal (zero-phase) spectral filter that leaked post-onset arc energy into the pre-window baseline. Caught and missed load-path arcs have indistinguishable spectral features; the 1–100 kHz arc signature is attenuated by the L_line–C_bus divider by roughly (f_res/f)² before it reaches the feeder. The information is not in the feeder stream — this is a sensing floor, not a classifier shortfall.

**Conclusion:** feeder-level sensing is the right place for Layer 1 and for busbar faults. Small faults on large or heavily-buffered segments, and load-side arcs, need per-rack sensing nodes. The v0.3 multi-segment model and the 48 V testbed should both include one per-rack node.

## What changed since v0.2 (feature extractor and studies only; physics unchanged)

| item | v0.2 | v0.2.2 | effect |
|---|---|---|---|
| `phase_err` search | ±12 % window around one previous edge → feature bounded at 0.12 for every class | full-history phase, folded to [0, 0.5] | faults now span the full range; scheduled steps concentrate at the jitter floor |
| history edge locator | argmax of 1 ms difference series (mid-ramp; falling-edge ring-back logged as rising edges) | two-level model with hysteresis, walked back to onset | 8 of 10 scheduled-step phase failures eliminated |
| period estimator | first autocorrelation peak above 0.4 (locked at 15 ms lag floor for long periods) | prominence ≥ 0.1, earliest peak within 85 % of tallest | no lag-floor locks |
| `resid_period` | in feature set | diagnostic column only | +0.3–0.6 pt missed faults recovered; it was 0.92-correlated with Δi_max |
| spectral floor | `sosfiltfilt` (zero-phase, non-causal) | `sosfilt` (causal), settled start | arc figure corrected 51 → 38 % |
| undetected onsets | fed as features | excluded from training, scored HOLD | 6 events |
| ablation reporting | single seed | 10 fold seeds, mean ± std | differences of a few events no longer reported as findings |
| per-unit fault current | hard-coded 800 V | drawn V_ref | ±10 % bin error removed |
| waveform figures | pristine physics | synthesized observables | figures now show what the relay sees |

## Limitations that must be stated in any claim

1. **Statistical resolution (OPEN-8):** 600 benign events cannot measure a 0.1 % false-trip rate. "Zero false trips" here means 0 of 600. The zero-false-trip operating point is set by one event.
2. **Periodicity premise:** the workload model assumes scheduler-periodic transients. Published measurements confirm lockstep periodicity (Microsoft/NVIDIA/OpenAI, Oracle, several 2025–26 grid-stability papers) but at iteration periods of roughly 0.3–10 s; this dataset sweeps 20–200 ms, which corresponds to sub-iteration structure (pipeline stages, micro-batches), not the iteration itself. The two-tier cadence is OPEN-9.
3. **Jitter model:** independent ±5 % per edge (random-walk). Real training loops are phase-locked with tighter interval jitter; the two remaining scheduled-step phase failures are this model's artifact. OPEN-10.
4. Single lumped segment, monopolar. No bipolar ±400 V, no multi-segment coordination, no managed energy-storage controller on C_bus.
5. Sanity gate under-samples the largest segments (700 kW–1 MW at 82 % of log-uniform expectation). OPEN-11.
6. Classifier is untuned. The 0.1 % / 1 % targets are not demonstrated by any configuration.
7. Series arc uses the static Stokes–Oppenlander + noise model; no ignition/extinction dynamics.
8. All timings assume a 2 MSa/s, 12–16-bit front end with no i/v channel skew (OPEN-3). Sample-rate sensitivity is not yet studied (OPEN-12) and determines the testbed front end.
