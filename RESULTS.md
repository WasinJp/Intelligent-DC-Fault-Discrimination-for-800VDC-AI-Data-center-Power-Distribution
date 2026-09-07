# RESULTS.md — Gate 2 and Gate 3 on dataset v0.2

**Dataset:** `data/events_v0.2.h5`, MODEL.md v0.2, master seed 20260907, 200 events per class × 7 classes = 1 400 events (600 benign, 600 trip-class faults, 200 series arcs). 164 system draws rejected by gate 1 (ζ < 0.15). Regenerate with `python scripts/generate_dataset.py` (≈2.5 min), features and studies with `python scripts/run_studies.py`, figures with `python scripts/make_figures.py`.

**Honest scope:** every number below is on *synthetic* events from a single-segment lumped model. Sweep ranges are wide on purpose (sensor noise 0.05–0.5 % FS, benign ramps 0.5–10 ms, segments 100 kW–1 MW, 35 % of faults inside an active workload transient). The 48 V testbed (final round) is what turns these into measured numbers.

---

## Gate 2 — the gray zone is real and it is high-impedance faults (Figure 1)

Conventional Layer-1 detectors on the observable line current and bus voltage, each threshold set at the edge of the benign envelope (**zero false trips on 600 benign transients**):

| detector | bolted missed | resistive missed | high-Z missed |
|---|---|---|---|
| magnitude | 19 % | 28 % | 83 % |
| di/dt | 1.5 % | 19 % | 88 % |
| v-collapse | 0 % | 6 % | 85.5 % |
| **all three (OR) — Layer 1** | **0 %** | **3.5 %** | **72.5 %** |

- 72.5 % of high-Z fault events lie *inside* the benign envelope on all three axes (Figure 1a). 25 % of all trip-class faults do.
- No threshold setting reaches the MODEL.md targets (false trip < 0.1 % and missed < 1 %) — `targets_reachable = False` over a 41×41 sweep.
- Hypothesis H1 confirmed: bolted faults are threshold-separable; the ambiguous zone is high-Z (and to a small degree resistive) faults. The quoted >3 kA/µs core-delivery figure never appears at bus level (bolted fronts are ~400 A/µs, limited by L_f).

## Gate 3 — the discriminator (Figure 2)

Gradient-boosted trees on features computed from the observable streams only, 1 ms decision window, 5-fold stratified CV, three decision classes (TRIP / HOLD / ALERT).

| feature set | false trips | faults missed | high-Z missed | composite missed |
|---|---|---|---|---|
| conventional (Δi, max di/dt) | 10.0 % | 13.5 % | 38.5 % | 12.3 % |
| + v–i physics | 3.0 % | 3.8 % | 11.5 % | 4.6 % |
| + workload-aware | 3.0 % | 3.8 % | 11.5 % | 4.6 % |

**Operating curve (Figure 2c).** Sweeping the TRIP probability threshold: at zero false trips on the 600 benign events the classifier misses 10.2 % of faults (high-Z: 30 %), versus 25.3 % (high-Z: 72.5 %) for the best conventional detector at the same zero-false-trip budget. High-Z detection goes from 27.5 % to 70 % with no additional false trips.

**Where workload-awareness acts.** In aggregate it changes nothing at 1 ms, because the v–i physics features already separate faults from ramps in most draws. It acts on the two subsets it was designed for:

| subset | +physics | +workload-aware |
|---|---|---|
| periodic-background events, false trips | 3.9 % | **2.0 %** |
| domain shift (train < 400 kW, test ≥ 400 kW), false trips | 5.6 % | **1.9 %** |
| domain shift, faults missed | 5.9 % | 8.3 % |

So: it halves nuisance trips on scheduled workloads and generalises better to larger segments on the false-trip side, at a small cost in missed faults under extrapolation. Figure 2b shows why — scheduled steps land within ~1 % of the learned period and within a few percent of the predicted size; faults land anywhere.

**Decision latency (Figure 4a).** At 0.25 / 0.5 / 1.0 ms after onset: false trips 4.2 / 2.5 / 3.0 %, faults missed 4.8 / 4.3 / 3.8 %. Most of the separation is available by 0.5 ms; the 1 ms window is not the bottleneck.

## What the sensing point can and cannot see (Figure 3) — resolves the feeder vs. per-rack question

- **High-Z miss rate scales with fault current relative to the segment rating:** 45 % missed below 0.15 p.u., 32 % at 0.15–0.3 p.u., 7 % at 0.3–0.6 p.u., 4 % above 0.6 p.u. A 10 Ω fault at 800 V is 80 A: 6 % of a 1 MW segment's rated current, 32 % of a 200 kW segment's.
- **Series arcs:** 96 % of busbar-joint arcs (upstream of C_bus) are flagged; only 51 % of load-path arcs (downstream of C_bus), because the bus capacitor shunts the arc noise before it reaches the feeder sensor.
- **Conclusion:** feeder-level sensing is the right place for Layer 1 and for busbar faults; small faults on large segments and load-side arcs need per-rack sensing nodes. The v0.3 multi-segment model is the next modelling step; the 48 V testbed should include one per-rack node.

## Limitations that must be stated in any claim

1. **Statistical resolution (OPEN-8):** 600 benign events cannot measure a 0.1 % false-trip rate. "Zero false trips" here means 0 of 600.
2. Single lumped segment, monopolar. No bipolar ±400 V, no multi-segment coordination, no converter output-capacitor dynamics beyond droop + lag.
3. Classifier is untuned (fixed hyper-parameters, no cost-sensitive loss). The 0.1 % / 1 % targets are not yet demonstrated by any configuration.
4. Series arc uses the static Stokes–Oppenlander + noise model; no ignition/extinction dynamics (Mayr deferred).
5. All timings assume a 2 MSa/s, 12–16-bit front end with no i/v channel skew (OPEN-3).
