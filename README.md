# Intelligent DC Fault Discrimination for 800 VDC AI Data Center Power Distribution

Physics-based digital twin, Monte Carlo event dataset and discrimination pipeline for the "nuisance trip" problem in 800 VDC AI data center power distribution.
**Built for Delta Cup 2026 (Energy Track).**

## The problem

As rack power densities approach 1 MW, AI training workloads draw power in lockstep: every GPU in a cluster alternates compute and communication together, and rack power traces a square wave at the iteration period. The resulting current transients look, at a protection relay, very much like DC faults. Tripping on a workload step interrupts a multi-million-baht training run. Holding through a real fault burns a busbar.

This repository quantifies where that ambiguity actually lives, and finds that the answer is an architecture question before it is a classifier question.

## Scope

One distribution segment, simulated end to end: source converter with droop → 800 VDC busbar → rack conversion stage stepping down to a 48 V rack bus → GPU load behind point-of-load converters. Eleven states, fixed-step RK4 on an event-segmented time base.

Two sensing points, and the study is largely about the difference between them:

- **feeder node** — line current and bus voltage at the 800 V busbar, where a conventional relay sits
- **rack node** — 48 V busbar current downstream of the rack's energy storage, and the 48 V bus voltage

Nine event classes across both buses: three benign (commanded step, scheduled workload edge, idle drop), three 800 V faults (bolted / resistive / high-impedance), two 48 V faults, and a series arc on either the busbar or the rack input path. 35 % of faults ignite inside an active workload ramp, because those are the hard ones.

What the pipeline is allowed to see is deliberately constrained: two synthesized sensor streams per node and the segment's ratings. No hidden states, no ground-truth labels, no true event time. Onset is detected on the observables, and cadence is learned from the slow stream. This is what makes the numbers mean anything.

## Headline result (dataset v04, 1 800 events — see RESULTS_v04.md)

**The feeder relay has two operating points and neither is acceptable.**

| relay | false trips | missed 800 V | high-Z (800 V) | missed 48 V |
|---|---|---|---|---|
| feeder only, catching everything | 11.82 % | 0.42 % | 1.25 % | 22.15 % |
| feeder only, 800 V duty only | **0.13 %** | 6.88 % | 19.95 % | — |
| rack only | 1.58 % | 26.70 % | 61.45 % | **0.00 %** |
| **feeder + rack** | **0.45 %** | **0.38 %** | **1.15 %** | **0.30 %** |

5-fold stratified CV over 10 fold seeds. Asked to catch everything, the feeder runs at 11.8 % false trips. Told that 48 V faults are the rack's problem, it drops to 0.13 % — and then misses a fifth of 800 V high-impedance faults, because the storage-smeared ones look like the load steps it was told to ignore. A rack node does not improve that trade-off. It removes it.

**48 V faults are laundered by the conversion stage.** A bolted 48 V fault collapses the rack's output, so the feeder sees the rack disappear — an idle drop. A high-impedance one clamps the converter at its current limit, so the feeder sees a load step. On early-window features the 48 V classes sit on top of the benign steps (di_early 0.024–0.028 against 0.015 benign, and 0.18 for an 800 V high-Z fault). A smoother rack hides its own faults better: with the converter's input ramp limiter active, the magnitude cue shrinks 3.5×.

**Workload-awareness works where the physics has nothing.** A laundered fault has no fault signature at the feeder — but it has no scheduler alibi either. A load step arriving when no load step was scheduled is the only thing the feeder can hold against a 48 V fault, and it recovers a third of the ones the physics features miss (48 V misses 33.5 % → 22.3 %), while cutting periodic-background false trips from 18 % to 6.4 %.

**The two nodes see disjoint fault sets.** The rack misses 27 % of 800 V faults (61 % of high-Z) because the converter keeps regulating its output until the input UVLO trips. The feeder misses 22 % of 48 V faults for the laundering reason above. Neither node is a superset of the other, which is why the combined relay beats both.

**Which side of the input stage the storage sits on decides whether it hides faults.** Bus-side storage — a capacitance shelf, or a BBU without reverse blocking — feeds a bus fault locally and smears the front the feeder sees: gray zone 73.9 % with it, 41.0 % without. Storage behind an ORing input stage cannot feed a bus fault and does not hide one. This is a design lever, not a nuisance.

**The EDP cadence tier is learnable only at the rack.** A slow voltage loop on a farad-class output bank turns a 1 ms burst into a roughly 10 ms ramp at the 800 V bus, and a soft edge cannot be phase-located inside the decision window. The iteration tier is learned equally well at both nodes; the burst tier belongs to the rack (OPEN-26).

## Repository layout

```
MODEL.md               versioned model specification — single source of truth (v0.4.2)
EVIDENCE.md            external sources for the workload model and the storage argument
RESULTS_v04.md         current: gates 2-3 and the node study on dataset v04
RESULTS.md             dataset v1 — feeder only, rack as a constant-power load
results/               archived results from superseded datasets
CHANGES_*.md           what changed at each step, and why
dcsim/
  model_v04.py         v0.4 core: conversion stage, 48 V bus, storage, UVLO
  model.py             v0.3 core, retained (CORE_VERSION = "v0.3")
  events.py            taxonomy, parameter draws, sanity gate, workload schedule
  synth.py             two nodes x fast/slow streams, front-end sweep
  features.py          rate-aware, node-agnostic, observables only
  confirm.py           hold-and-confirm second stage (tested, rejected)
  dataset.py           Monte Carlo generation to HDF5
  studies.py           gates 2-3, node study, front-end study
scripts/
  validate_model.py    validation checks (a)-(h); (i) Simscape cross-check pending
  generate_dataset.py
  run_studies.py       gates 2 and 3
  run_node_study.py    feeder / rack / combined relay
  run_rate_study.py    acquisition front-end sweep
  run_confirm_study.py hold-and-confirm study
  make_figures.py
figures/
```

## Reproduce

```bash
pip install -r requirements.txt
python scripts/validate_model.py                            # 8 checks
python scripts/generate_dataset.py data/events_v042.h5 200  # 1 800 events, ~1 h
python scripts/run_node_study.py
python scripts/run_studies.py
python scripts/make_figures.py
```

Datasets and feature tables are not tracked — regenerate them from the seed. An event is determined by (MODEL.md version, CORE_VERSION, WORKLOAD_VERSION, master seed), and every dataset records them. The v0.3 core and the v0.2 workload are both retained behind switches, so earlier datasets remain reproducible.

Validation runs before generation, and the checks are analytic or independent-implementation comparisons rather than self-consistency: analytic RLC discharge, droop steady state, the segmented time base against a uniform 50 ns reference, the 10 µs history tier against an all-2 µs reference, converter steady state, the closed-loop response against an exact linearisation, the ramp limiter's energy balance, and the 48 V fault front. A Simscape Electrical cross-check against an independent implementation is the outstanding one.

## How this repository is meant to be read

MODEL.md is the specification that everything else must match. §9.4 holds the predictions registered before each run; §11 tracks open items; §12 records what changed and why. RESULTS_v04.md is the current evidence, including the prediction scorecard. EVIDENCE.md holds the external sources behind the workload model.

Expected results are written down before a run, and a prediction that fails is reported as failed. On the v0.4.2 run, prediction 3 failed: bus-side storage did not raise the feeder's high-impedance misses as predicted, because the conversion stage smears the benign transients by a comparable amount. Two earlier runs were discarded outright — v0.4, where the smoothing front end decoupled the storage from the bus and left half the dataset generated on a ringing bus, and v0.4.1, where the rack slow stream was wired to the converter output. Both were caught by predictions that did not come true.

Some negative results are recorded so they are not re-litigated: routing events to separate models on `has_period` is worse than one model; a hold-and-confirm second stage at 2.5–4.5 ms does not earn its latency, and the residue is routed to a slower monitoring layer instead; acquisition rate and ADC depth are irrelevant to the discriminator across 100 kSa/s–2 MSa/s and 12–16 bits, so the testbed front end is specified at 500 kSa/s / 14-bit for margin rather than for accuracy.

## Status

- **v0.1–v0.2** (Aug–Sep 2026): four-state core, event taxonomy, sensor synthesis, dataset v0.2, gates 2–3.
- **v0.3.x** (Sep 2026): two-tier workload model sourced in EVIDENCE.md; 10 µs history tier; acquisition front-end sweep; hold-and-confirm tested and rejected.
- **v0.4.2** (Sep 2026): rack conversion stage, 48 V bus and fault classes, second sensing node, feeder + rack node study.
- Next: Simscape cross-check; a larger benign set for the 0.1 % false-trip target; 48 V testbed for the final round; multi-shelf rack with current sharing.

## Limitations

Every number here is synthetic: a single segment, one aggregated rack, no measured trace yet. 600 benign events cannot resolve a 0.1 % false-trip rate — "zero false trips" means zero of 600, and that operating point is set by a single event. The rack storage value and its 48 V placement are inferred from public shelf descriptions rather than a datasheet, and the ORing input assumption is a design choice that a bidirectional input stage would invalidate. Absolute iteration-edge jitter at rack level is not published; ≤ 2 % is a working assumption. The series-arc model has no ignition or extinction dynamics, and the topology is monopolar with no multi-segment coordination. The full list is in RESULTS_v04.md §11.
