# Deadline study — what is 0.25 ms *for*? (Prof. Supachai's question, 15 Oct 2026)

**Source:** `scripts/run_deadline_study.py` on `data/events_v1xl6k_s*.h5` (MODEL.md 0.4.4): 300 events per class (500 for the two high‑Z classes); W = 0.25 ms, processing budget 96 µs (onset granularity 16 + ≤ 80 µs; to be replaced by the M3 measurement), SSCB opening t_brk = 20 µs (assumption — OPEN‑25 for Delta's experts). Tables: `data/deadline/deadline_table.md`, `data/deadline_hz/deadline_table.md`, per‑event CSVs, ECDF figures.

**Question.** For each fault class, how long after inception until something goes wrong — and how does that compare with our time: onset → decision → TRIP → breaker open (T_brk ≈ 0.37 ms)?

**"Something goes wrong" (deadlines, first occurrence after inception):** D1/D2 fault current exceeds 2× (and 3×) rated at the feeder / rack — the current an SSCB is assumed to have to interrupt; D3 the 800 V bus falls below the rack converter's input UVLO (a fault starts taking healthy racks down — selectivity lost); D4 the 48 V bus falls below the POL UVLO for its delay (the GPUs drop — the training run is lost).

## 1. Result

| class | our T_brk (median) | bus < converter UVLO (D3) | GPUs drop (D4) | rack current > 2× (D2) | feeder current > 2× (D1) |
|---|---|---|---|---|---|
| **bolted 800 V** | 0.37 ms | **100 % of events, median 28 µs** (p95 121 µs) — before any window‑based relay | 12 % within the record, median 3.1 ms; **1 % before T_brk** | 0 % | 5 % (median 64 µs) |
| **resistive 800 V** | 0.37 ms | 98 %, median 68 µs; **76 % before T_brk** | 12 %, median 2.8 ms; 0 % before T_brk | 0 % | 4 % |
| **high‑Z 800 V** | 0.38 ms | **35 % ever**, median 2.9 ms (p5 0.16 ms); **4 % of all events before T_brk** | 5 % ever, median 5.9 ms; **0 % before T_brk** | 0 % | < 1 % |
| **bolted 48 V** | 0.37 ms | 1 % | **21 % within the record, median 0.17 ms; 15 % of all events before T_brk** | **92 %, median 68 µs; 83 % before T_brk** (3×: 56 %) | 0 % |
| **high‑Z 48 V** | 0.37 ms | 1 % | 7 % ever, median 1.8 ms; **1 % before T_brk** | **22 %, median 92 µs; 16 % before T_brk** (the 5–10 mΩ end of the class) | 0 % |

Percentages are of all events in the class ("ever" = the condition occurs within the stored record, i.e. within seconds; the rest never reach it — the storage bank and the converter ride through).

## 2. Reading

**Bolted and resistive 800 V faults.** The bus is below the converter UVLO within 30–70 µs — *no* window‑based decision can prevent that, and neither can a per‑sample one with a 20 µs breaker. The architecture is what rides through it: the converter sheds on UVLO, the 48 V storage carries the GPUs, and the GPUs drop in only 12 % of events, median 3 ms later. So for bolted faults the relay's job is **isolation in time for selectivity and energy let‑through, not preventing the dip** — and the per‑sample **Layer 1** threshold (TRIP within a few samples) is the right tool; the 0.25 ms window is not in the critical path for this class. Say this plainly: bolted faults are the conventional case, handled conventionally.

**High‑Z 800 V — the class the project exists for.** Where a deadline exists at all (35 % of events reach the bus UVLO, 5 % reach GPU dropout), it is **milliseconds** (median 2.9 / 5.9 ms). Our 0.37 ms meets the bus‑UVLO deadline in 96 % of all events and the GPU‑dropout deadline in 100 %. The 4 % it misses are at the resistive boundary of the class (bus UVLO at 0.16–0.37 ms). So **0.25 ms is a choice, not a necessity**: it is the earliest point at which the relay separates a high‑Z fault from a GPU load step at the 0.1 % false‑trip budget, and it leaves ≈ 8× margin to the median deadline. A 1 ms window would be more accurate on paper (RESULTS_v04: 0.33 % vs 0.42 % missed) but would eat most of the margin on the fast tail (p5 0.16 ms) — that trade‑off is the honest justification of 0.25 ms. (The window itself was chosen before this study from the feature‑separation argument, OPEN‑14: maximal separation in the first 50 µs; this study is the deadline side of the same answer.)

**48 V side.** Bolted 48 V faults push the rack current past 2× rated within ~70 µs in 92 % of events and drop the GPUs within ~0.17 ms in a fifth of them — a Layer 1 class, and even Layer 1 with a 20 µs breaker cannot save the GPUs in those 15 %; the storage bank's ESR and the fault resistance decide. *(Added 16 Oct, HIL final fixes F1.)* For the 48 V classes the GPUs share the faulted busbar with the fault — the rack SSCB sits between the storage bank and that busbar — so D4 (GPUs drop) is not a deadline any breaker can meet on that rack; the 48 V deadline is D2: current and energy let‑through (in the HIL demo case, Layer 1 at 75 µs vs the 0.25 ms relay at 375 µs: peak 6 vs 18 p.u., I²t ≈ 50× lower). **High‑Z 48 V is two populations:** the low‑resistance end (5–10 mΩ, ≈ 22 % of the class) behaves like a bolted fault (rack current > 2× within ~90 µs) and belongs to Layer 1; the rest has ms deadlines or none, and the 0.25 ms relay meets them (GPU dropout before T_brk: 1 % of events).

## 3. Consequences

1. **Layer 1 at the rack node goes ON for the HIL and bench profiles**, threshold ≈ 2–2.5 × I_out_rated on i_rack (benign rack current never exceeds ≈ 1.3 p.u. with bursts): it catches bolted 48 V and the fast quarter of high‑Z 48 V in a few samples, which the deadline table says is the only way to meet their deadlines. The feeder node's Layer 1 stays as designed for bolted 800 V. The exact k (2 or 3) is OPEN‑25 — what an SSCB must interrupt — for Delta's experts; the table is computed for both.
2. **The timing claim is restated as a chain:** inception → onset (3–10 µs median) → decision window 0.25 ms → TRIP (+ ≤ 96 µs, M3 measures it) → breaker (+ t_brk) = 0.37 ms, against a median deadline of 2.9 ms (bus) / 5.9 ms (GPUs) for the class it is designed for. Bolted classes: Layer 1, µs.
3. **Honest limits to state:** t_brk = 20 µs and the 2× / 3× interrupt levels are assumptions (OPEN‑25); the deadlines come from the simulator (validated), not from a data centre; 300–500 events per class; the 96 µs processing figure is a budget until M3.
4. **For the pitch:** one slide — the five‑row table above with T_brk marked, the sentence "for high‑Z faults the deadline is milliseconds; we decide in a quarter of one, with 8× margin; for bolted faults a per‑sample threshold trips in microseconds — both are in the same node."

**One more number to pull for the slide** (from `deadline_events.csv`, high_z): the fraction of events with *any* deadline below 1 ms — the fast tail that a 1 ms window would have lost:
`python -c "import pandas as pd,numpy as np; d=pd.read_csv('data/deadline_hz/deadline_events.csv'); d=d[d.label=='high_z']; m=np.nanmin(d[[c for c in d if c.startswith('D')]].replace(np.inf,np.nan).values,axis=1); print((m<1e-3).mean(), (m<0.37e-3).mean(), np.isfinite(m).mean())"`
