# PITCH_BRIEF.md — paste-in replacements (2 Oct 2026, dataset v1xl6k)

Two blocks. Replace in place; nothing else in the brief changes.

---

## Replace the Slide 6 table and its footer (§2, Section 3)

**Slide 6 — Validation & performance data** (skip if the demo ended on step 8)

| Relay | False trips on normal work | Missed 800 V faults | Missed 48 V faults |
|---|---|---|---|
| Feeder node alone | TBD | TBD | cannot see them |
| Rack node alone | TBD | TBD | TBD |
| **Feeder + rack** | **0.09 %** | **0.33 %** | **0.29 %** |

- Footer: 36 000 simulated events (30 000 normal, 6 000 faults), segments 100 kW–1 MW, 5-fold cross-validation × 10 seeds, threshold calibrated on held-out data at a 0.1 % budget. Missed high-impedance 800 V faults 0.99 %. Same result at the 0.25 ms decision window.
- *แนวทาง:* ชี้ให้เห็นว่า "แต่ละโหนดมีจุดบอดของตัวเอง รวมกันแล้วปิดจุดบอดได้" คือประโยคเดียวที่ต้องพูดกับตารางนี้

---

## Replace §3 Numbers sheet

## 3. Numbers sheet (the only numbers allowed on slides)

| Quantity | Value | Source |
|---|---|---|
| Decision time | 0.25 ms after onset | RUNBOOK §E, window table |
| Two-node relay, threshold calibrated on held-out data (0.1 % budget) | 0.09 ± 0.01 % false trips; 0.33 ± 0.06 % missed 800 V; 0.29 ± 0.06 % missed 48 V; 0.99 ± 0.17 % missed high-Z | RUNBOOK §E |
| Two-node relay, default threshold, 0.25 ms window | 0.03 % false trips; 0.42 % missed 800 V; 1.25 % high-Z; 0.63 % missed 48 V | RUNBOOK §E, window table |
| Same at 1 ms | 0.04 / 0.46 / 1.36 / 0.53 % | RUNBOOK §E |
| Feeder alone (800 V duty) | TBD — v1xl6k node study | node study |
| Rack alone | TBD — v1xl6k node study | node study |
| Gray zone, 800 V high-Z faults, conventional thresholds | 57.8 % / 39.6 % at the 99.9th / 99th percentile of the benign envelope | Gate 2 percentile rows |
| Dataset | 36 000 events: 30 000 normal, 6 000 faults; 100 kW–1 MW | v1xl6k |
| Feeder vs rack view of the same 48 V fault | feeder 90 % in 1.4 ms; rack 90 % in 0.06 ms (normal step: 3.3 ms / 1.8 ms) | reference case high_z_48 |
| Simscape cross-check | 8 of 8 within 1 %; worst 0.42 %; UVLO edge at 0.00 µs | crosscheck_log 18 Sep |
| Front end | bits (12–16) and rate (100 kSa/s–2 MSa/s) not limiting | OPEN-12 |
| Alibi check | recovers about a third of laundered 48 V faults at the feeder | RESULTS_v04 §5 |

---

## §1 headline line

Replace the old "0.06 % on 5 001 events" wherever it appears with:

> false trips below 0.1 % on 30 000 normal events; about 0.3 % missed faults on each side; decision window 0.25 ms

---

## Four things I could not fill in

1. **Feeder-alone and rack-alone rows.** Both the slide-6 table and §3 need them from the v1xl6k node study, not v1-large. They are in `data/nodes_v1xl6k/node_study.json`. The old values (0.02 / 6.97 and 0.12 / 30 / 0.52) are v1-large and must not be mixed into a v1xl6k table.
2. **The zero-false-trip gray-zone number.** The old row had three points (72 / 57 / 36.5 % at 0 / 0.26 / 2.52 %). The update gives only two (57.8 / 39.6 %). If the max-of-benign point exists for v1xl6k, add it; if not, say which percentiles the two numbers correspond to on the slide, because "57.8 / 39.6" with no percentile labels is unreadable.
3. **The 95 % confidence claim.** The headline in the update says "below 0.1 % (95 % confidence)". 0.09 % of 30 000 is about 27 events; a Poisson 95 % upper limit on 27 is roughly 0.13 %, which is above 0.1 %. The RUNBOOK's own registered prediction for run D said the upper limit clears 0.1 % only if the count is ≤ 19. The 0.09 % figure is a CV mean across folds rather than one count, so the interval may be computed differently — but the claim needs the arithmetic shown before it goes on a slide. I have dropped "(95 % confidence)" from the headline above until that is settled. This is the single most checkable number in the pitch.
4. **Slide 7** quotes "9 validation checks". Confirm that still matches `validate_model.py` after check (j).
