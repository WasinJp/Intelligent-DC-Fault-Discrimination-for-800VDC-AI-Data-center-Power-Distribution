# RESULTS_v04.md — Gates 2 and 3 on dataset v04 (MODEL.md v0.4.2, rack conversion stage)

**Dataset:** `data/events_v042.h5`, MODEL.md v0.4.2, workload v1, master seed 20260907, 200 events per class × 9 classes = 1 800 events (600 benign, 600 800 V faults, 400 48 V faults, 200 series arcs). Front end: smoothing on 924 / off 876; bus-side storage present on 1 010. Regenerate with `python scripts/generate_dataset.py data/events_v042.h5 200` (≈ 1 h); studies with `python scripts/run_node_study.py` and `python scripts/run_studies.py`.

**What v04 adds over v1 (RESULTS.md).** The rack is no longer a constant-power load on the 800 V bus. It is an explicit conversion stage: passive input filter behind an ORing stage, averaged DC-DC with cascaded control, output current limit and loss model, converter-input ramp-rate limiter (power smoothing), the rack energy storage on the 48 V side (65 J/GPU → 0.2–5 F), POL constant-power load with UVLO, and a 48 V fault branch. Two sensing nodes: feeder (i_L, v_bus) and rack (48 V busbar current downstream of the storage, v_out). Two new fault classes on the 48 V bus. Bus-side storage (capacitance shelf / BBU without reverse blocking) as a sweep flag.

**Honest scope:** synthetic, single segment, one aggregated rack. The Simscape cross-check (§8 (i)) and any measured trace are still pending. Two earlier runs on this core were discarded: v0.4 (2026-09-15, front end decoupled the storage from the bus and half the dataset was generated on a ringing bus) and v0.4.1 (rack slow stream wired to the converter output). Both were caught by pre-registered predictions; the corrections are in MODEL.md §12.

---

## 1. Node study — the architecture result

5-fold stratified CV over 10 fold seeds; mean ± std in %. "Missed" is split by fault side. The onset rule for the combined relay is "detected at either node".

| relay | false trips | missed 800 V faults | high-Z (800 V) missed | missed 48 V faults |
|---|---|---|---|---|
| feeder only, asked to catch everything | 11.82 ± 0.85 | 0.42 ± 0.08 | 1.25 ± 0.25 | 22.15 ± 0.74 |
| feeder only, 800 V duty (48 V faults are the rack's job) | **0.13 ± 0.07** | 6.88 ± 0.56 | 19.95 ± 1.59 | — |
| rack only | 1.58 ± 0.23 | 26.70 ± 0.26 | 61.45 ± 0.65 | **0.00 ± 0.00** |
| **feeder + rack** | **0.45 ± 0.13** | **0.38 ± 0.08** | **1.15 ± 0.23** | **0.30 ± 0.10** |

For comparison, dataset v1 (feeder only, no conversion stage, no 48 V faults): 1.48 / 2.43 / 7.30 / no coverage.

**The feeder alone has two operating points and neither is acceptable.** Asked to catch everything, it runs at 11.8 % false trips. Told that 48 V faults are not its responsibility, it runs at 0.13 % false trips — and then misses 20 % of 800 V high-impedance faults, because the storage-smeared ones now look like the load steps it has been told to ignore. The rack node does not improve the feeder's trade-off; it removes it: 0.45 % false trips, 0.4 % missed on the 800 V side, 0.3 % on the 48 V side.

**The two nodes see disjoint fault sets.** The rack node misses 27 % of 800 V faults (61 % of high-Z) because the converter keeps regulating its output until the input UVLO trips; the feeder misses 22 % of 48 V faults because the converter launders them (§4). Neither node is a superset of the other.

## 2. Why the feeder cannot own 48 V faults — laundering

A fault on the 48 V bus is seen from the 800 V bus through the converter. A bolted fault collapses v_out; delivered power goes to zero; the feeder sees the rack disappear — an idle drop. A high-impedance fault clamps the converter at its current limit; the feeder sees drawn power rise — a load step. On the early-window features that separate 800 V faults from workload steps:

| at the feeder, 1 ms, medians | di_early | dv_early |
|---|---|---|
| benign step | 0.015 | 0.001 |
| bolted_48 | 0.028 | 0.005 |
| high_z_48 | 0.024 | 0.004 |
| high_z (800 V), no bus storage | 0.18 | 0.007 |

The 48 V classes sit with the benign steps. What the feeder does catch (78 % of them) it catches on magnitude — an unsmoothed 48 V fault pulls the converter to 1.2–1.6 × rated, a 40–60 % step — and on the workload alibi (§5). With the ramp limiter on, the magnitude cue shrinks 3.5× (bolted_48 di_max 0.61 → 0.17), so a smoother rack hides its own faults better.

At the rack node, downstream of the storage, a bolted 48 V fault is the storage bank discharging: 4.7 p.u. on the busbar against 0.1 for a benign step. Missed 48 V faults at the rack: 0 of 400.

## 3. Gate 2 — the gray zone, four ways

Conventional thresholds at the edge of the benign envelope (zero false trips). Fraction of 800 V high-impedance faults inside the benign envelope on all three axes:

| | smoothing off | smoothing on |
|---|---|---|
| no bus storage | 41.0 % | 29.4 % |
| bus storage on the 800 V bus | **73.9 %** | 31.2 % |

Overall 60.5 % (v1: 66.5 %). 48 V faults: 81–98 % inside the envelope. No threshold setting reaches the targets.

Two mechanisms, both physical. Bus-side storage feeds the fault locally and smears the front the feeder sees (the dataset-v1 finding, here as the top-right cell). The converter-input ramp limiter smears the *benign* transients, pulling the benign envelope in and shrinking the gray zone regardless of storage (right column). The feeder resolves the difference between the two.

## 4. Gate 3 at the feeder — repeated CV

| feature set | false trips | missed (all TRIP classes) | high-Z (800 V) missed | periodic bg: FT / missed | flat bg: FT / missed |
|---|---|---|---|---|---|
| conventional | 23.63 ± 0.95 | 14.22 ± 0.66 | 11.70 ± 2.12 | 23.69 / 16.02 | 23.58 / 12.45 |
| + v–i physics | 17.45 ± 0.56 | 12.93 ± 0.56 | 1.35 ± 0.63 | 18.01 / 13.76 | 16.89 / 12.11 |
| + workload-aware | 11.82 ± 0.85 | 9.11 ± 0.29 | 1.25 ± 0.25 | **6.35 / 6.64** | 17.32 / 11.55 |

These are the feeder asked to catch everything, so the absolute rates carry the 48 V classes it cannot see (§2); the *deltas* are the result. Physics features take 800 V high-Z misses from 11.7 % to 1.4 %. Workload-awareness then takes false trips from 17.5 % to 11.8 %, missed faults from 12.9 % to 9.1 %, and on periodic backgrounds false trips from 18.0 % to 6.4 %.

Decision latency: missed 8.5 % at 0.25 ms, 8.5 % at 0.5 ms, 9.2 % at 1 ms. The decision is available at 0.25 ms; the longer window helps only arc detection (59 → 69 %). Domain shift (train < 400 kW, test ≥ 400 kW, single fit): workload-aware 10.1 % false trips against 17.6 % for physics alone; missed-48V columns dominate the rest.

## 5. Workload-awareness on laundered faults — a new role for the feature

At the feeder, adding `phase_err` cut 48 V-fault misses from 33.5 % to 22.3 % (bolted_48 22.5 → 15.0, high_z_48 44.5 → 29.5) and periodic-background false trips from 18 % to 6.4 %. A laundered fault has no fault signature at the feeder — but it has no scheduler alibi either. A load step that arrives when no load step was scheduled is the only thing the feeder can hold against a 48 V fault, and it recovers a third of the ones the physics features cannot. This is a stronger claim for the feature than dataset v1 supported, because here it works on events where the physics has nothing.

## 6. Cadence learning by node

| | feeder | rack |
|---|---|---|
| has_period on periodic backgrounds | 1.000 | 1.000 |
| tier-1 period within 3 % | 99.8 % | 99.7 % |
| tier-2 found / present | 497 / 541 | 510 / 541 |
| scheduled tier-1 events, phase error p95 | 0.032 | 0.032 |
| scheduled tier-2 events, phase error p95 | **0.208** | **0.096** |
| alibi coverage (unscheduled events < 0.05) | 19.4 % | — |

Tier 1 (the iteration cadence) is learned equally well at both nodes in both smoothing states. Tier 2 (EDP bursts) is learnable only at the rack: a slow voltage loop on a farad-class output bank turns a 1 ms burst into a ~10 ms ramp at the bus, and a soft edge cannot be phase-located in the decision window (OPEN-26). Independent of the smoothing switch. The EDP-tier alibi belongs to the rack node.

## 7. Bus-side storage versus storage behind the input stage

800 V high-Z misses at the feeder, feeder + rack relay: 0.0 % with no bus storage; with bus storage 2.7 / 0.0 / 5.4 % across C_store terciles (2 / 8 / 31 mF). The fault-front smearing seen on dataset v1 is reproduced in the early-window features (di_early 0.18 → 0.10 → 0.08 → 0.05 across terciles), but the miss rate stays low because the conversion stage smears the benign transients by a comparable amount (§3). The v1 statement "bus capacitance hides high-impedance faults" becomes: *storage on the bus degrades the fault signature; the conversion stage degrades the benign signature; the feeder resolves the difference, and on this sweep the difference held.* Storage behind an ORing stage (the 48 V-side C_out) cannot feed a bus fault and does not hide one.

## 8. Series arcs

Busbar arcs 91 % flagged (onset found 100 %); rack-path arcs 51 % (onset 91 %). Load-path arcs remain weak evidence at the feeder; a 48 V-side arc class is not yet in the taxonomy.

## 9. Prediction scorecards

**v0.4 run (2026-09-15), half discarded; scored on the valid half.** 1 failed (feeder caught 89 % of 48 V faults on magnitude), 3 inverted (storage behind the input stage did not hide faults), 4 failed at the rack node — which is what exposed the gate mismatch, 5 held.

**v0.4.1/0.4.2 run, re-registered predictions (MODEL.md §9.4):**

| # | predicted | result | |
|---|---|---|---|
| 1 | feeder misses ≥ 50 % of 48 V faults at ≥ 4 % FT; rack > 99 % | 22 % at 11.8 % FT; rack 100 % | half |
| 2 | gray zone ~45 % without bus storage, ≥ 60 % with | 41 % / 74 % (smoothing off) | ✓ |
| 3 | feeder high-Z misses ≥ 10 % with bus storage | ≤ 5.4 % at any tercile | ✗ (§7) |
| 4 | cadence at both nodes; workload gain persists | has_period 1.00 both; FT 17.5 → 11.8 | ✓ |
| 5 | feeder + rack ≤ 3 / 1 / 3 % | 0.45 / 0.38 / 0.30 | ✓ |
| 6 | smoothing halves the feeder's 48 V magnitude cue | 0.61 → 0.17 | ✓ |

## 10. What changed since RESULTS.md (v1)

| | v1 (core 0.3) | v04 (core 0.4.2) |
|---|---|---|
| rack model | constant-power load on the bus | conversion stage, storage at 48 V, ramp limiter, ORing input |
| sensing | feeder only | feeder + rack node |
| fault classes | 800 V only | + bolted_48, high_z_48 |
| best relay | 1.48 / 2.43 / 7.30, no 48 V coverage | **0.45 / 0.38 / 1.15 / 0.30** |
| storage finding | bus capacitance hides high-Z faults (0 → 18 %) | depends on which side of the input stage; feeder resolves the difference |
| EDP-tier cadence | learned at the feeder | learnable only at the rack |
| workload-aware | separates scheduled from unscheduled | additionally recovers a third of laundered 48 V faults at the feeder |

## 11. Limitations that must be stated in any claim

1. Synthetic; single segment; one aggregated rack (OPEN-21). Simscape cross-check pending.
2. 600 benign events cannot resolve a 0.1 % false-trip target (OPEN-8); the zero-false-trip operating point is set by one event.
3. C_out (0.2–5 F) and its 48 V placement are inferred from public shelf descriptions, not a datasheet (OPEN-19); the ORing assumption is a design choice (OPEN-24); Delta's BBU is represented by bus-side C_store (OPEN-25).
4. The rack observable is the busbar downstream of the storage; a sensor upstream of it (converter output) sees a 48 V fault only as the current limit, and this study does not cover that placement.
5. Tier-2 cadence at the feeder is a stated limit (OPEN-26); tier-2 periods near the 20 ms floor are missed ~6 % at either node (OPEN-16).
6. Absolute iteration jitter, arc dynamics, bipolar topology, multi-segment coordination: as in RESULTS.md.
7. Layer 3 (hold and monitor on the workload timescale) is designed, not simulated; requires the extended post-event record of dataset v1-large.
