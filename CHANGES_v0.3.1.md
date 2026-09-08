# v0.3.1 — cadence estimator fixes (features.py only; no regeneration needed)

The dataset `events_v1.h5` is unchanged. Replace `dcsim/features.py`, run `scripts/run_studies.py data/events_v1.h5`; the hash guard regenerates the feature table.

## What was wrong on the v1 run (1 400 events)

| symptom | cause | fix |
|---|---|---|
| tier-2 found on 361 / 423 (85 %); miss rate 41 % for 100–200 ms bursts | `_tier2_from_segments` set the lag window from the **shortest** compute-phase segment, which is always a partial one (history start, or the current phase cut at the event) | lag window from the longest segment; each segment contributes autocorrelation up to 0.45 of its own length, averaged with per-lag counts |
| tier-2 scheduled events p95 = 0.157 | the 14 of 57 with tier 2 not found fell back to the tier-1 phase, which is random mid-compute-phase | follows from the above; when tier 2 is found these events sit at median 0.008 / p95 0.048 |
| 3 of 143 tier-1 scheduled events at random phase; `T1_est / T1 ≈ 0.1` | estimator took the 9th–12th harmonic of a 20 ms burst comb (height ≈ 0.8) over the true iteration peak (≈ 0.6); harmonic filter was capped at order 8 | envelope search: take the shortest strong cadence T_s, smooth the history over 2·T_s (removes the comb and all harmonics), search the smoothed history for a longer fundamental → tier 1; T_s → tier 2. Harmonic filter uncapped as a secondary guard. Candidate threshold 0.25 → 0.15. |

## Verified by regenerating the failing events from seed

- tier-1 failures: 0.499 → 0.000, 0.184 → 0.006, 0.239 → 0.013
- long-T2 misses: 11 / 12 recovered; short-T2 (20–30 ms, 5 ms ramps) misses mostly remain — bursts are barely formed at that ratio
- regression, 60 events: T1 within 3 % on 60/60; T2 within 5 % on 47/50; false tier-2 0; scheduled phase error median / p95 / max unchanged

## Also settled on the v1 feature table (10-seed CV)

- `phase_err = min(tier 1, tier 2)` is the right combination: split-tier features trade false trips for missed faults with wider spread; tier 1 alone is worse than both tiers (missed 2.87 vs 2.58, high-Z 8.60 vs 7.75). Learning the EDP tier earns its keep despite the ~19 % alibi coverage.
- Load-path arc detection 38 % (v0.2) → 68 % (v1) is entirely on periodic backgrounds (23 % → 72 %); flat backgrounds are 58 % in both. The v0.2 20–200 ms train buried a 0.02 p.u. arc step in background transients; the v1 iteration train is quiet, and the periodicity alibi applies to arcs (77 % flagged when phase_err > 0.05 vs 33 % when ≤ 0.05). RESULTS.md wording: load-path arcs at the feeder are **weak** evidence (58 % on a quiet bus vs 96 % busbar), not "no information".
- Domain-shift rows identical for physics and workload-aware: 20 predictions differ, counts cancel. Coincidence, not a bug; no domain-shift gain on v1, single fit.
