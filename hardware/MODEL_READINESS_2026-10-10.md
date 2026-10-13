# MODEL_READINESS_2026-10-10.md — what "the model works" must mean before the HIL meeting, and how we show it

**Context (10 Oct):** Prof. Supachai will book a meeting with the HIL owner (a former student's company) once we confirm the model works; the owner will then advise how to tap the model's signals out as real signals. His DAC: 16-bit at 5 or 10 MS/s. He asked what to simulate, whether we want current signals out, and for a block diagram + I/O list → answered in `HIL_INTERFACE_BRIEF_2026-10-10.docx` (Thai) and `hil_interface_diagram.svg`.

## 1. What "works" has to mean to a HIL engineer

Three different statements, in increasing strength. We have the first; the second is the one that unblocks the meeting; the third is what the meeting itself produces.

| level | statement | status | evidence |
|---|---|---|---|
| A | The equations are right and two independent implementations agree | **done, 18 Sep** | Python core (9 analytic checks) vs Simscape Electrical `dcsim_shelf.slx`: check (i) 8 of 8 cases, discontinuity-excluded RMS ≤ 1 % on i_L, v_bus, i_rack, v_out (`simscape/crosscheck_log.txt`, Figure 5 overlay) |
| B | A **fixed-step, explicit, real-time-shaped** implementation reproduces the same eight cases at a step a HIL can run | **to build (this week)** | new `simscape/dcsim_rt.slx`: one discrete MATLAB Function block, RK4 of the 11 states (a line-for-line port of `model_v04._derivs`), Ts = 1 µs (and 2 / 5 / 10 µs), scored by the existing `scripts/compare_simscape.py` through `run_case.m`'s `sim_<case>.mat` format |
| C | The box runs it, the nodes decide on its outputs, the breaker opens on TRIP, latency is measured | the meeting and the week after | open-loop waveform match on the scope → node decisions match → closed loop → latency table |

Why B is the one that matters: the Simscape network in A is solved by `ode23t` (variable step, implicit) — exactly what a real-time target cannot do and what MODEL.md §4.8 says breaks the anti-windup rule. The HIL owner will convert *a fixed-step model*, so handing him A alone leaves the conversion risk with him; handing him B means the conversion is a format change, not a numerical one.

## 2. Level B — the fixed-step explicit model, design

- **One block.** A discrete MATLAB Function (sample time `dt`) with 11 persistent states, inputs `P_gpu`, `V_arc`, `fault_on`, `fault48_on`, `brk_f_closed`, `brk_r_closed`, parameter vector `prm` (the 17-entry vector already defined by `run_case.m` + the fault and breaker parameters), outputs `i_L, v_bus, i_rack, v_out` (+ `dbg_*`). Inside: `_derivs` ported line for line (same operation order), RK4 step, the UVLO state machines, the quasi-static fault rule when `dt > 0.5·τ_f`, the `v ≥ 0` / `i_Lin ≥ 0` / `i_L ≥ 0` clamps, the breaker element (open = branch current forced to zero over one step; a configurable opening delay). No Simscape blocks, no algebraic loops, no continuous states.
- **Breaker element** is new (MODEL.md 0.4.5 entry, needs Wasin's OK): `brk_f` sits in the feeder branch (i_L → 0 when open), `brk_r` in the rack busbar between storage and load/fault (i_pol + i_f48 → 0 when open). During the decision window both are closed, so Layer-1/2 results are unaffected; the element only shapes the post-trip record and the demo.
- **Validation = check (i), unchanged criterion.** `run_rt_case.m` loads a case with `load_case.m`, runs `dcsim_rt` at dt, resamples to the 1 µs reference grid, writes `sim_<case>.mat`, and `compare_simscape.py` scores it. Pre-registered expectation: at dt = 1 µs all eight cases pass with excluded-RMS ≤ 3 × 10⁻⁴ (same order as the Python 50 ns-vs-uniform check (c), since this is the same scheme at a coarser step); at 10 µs the step cases pass and the stiff fault cases depend on the quasi-static rule — report both.
- **Step sweep = the plant half of check (k).** dt ∈ {1, 2, 5, 10, 20} µs, eight cases each, one table. This is the number to put next to the box's solver step when it is known.
- **What it costs:** the port is mechanical (the Python core is already an explicit fixed-step RK4 — this is the same algorithm in MATLAB). One MATLAB Function block of ~250 lines plus a 60-line builder/runner. Testing needs MATLAB (Wasin's machine); the harness conventions (`load_case`, `project_paths`, `compare_simscape.py`) are reused as they are.

## 3. What to show at the meeting (≈ 15 min, in this order)

1. `pitch/two_node_explainer.html` — what the relay does and why two nodes (3 min).
2. Open `dcsim_shelf.slx`, run one case live (`crosscheck` → `step`, about a minute), show the eight-case Python-vs-Simscape overlay (Figure 5) — "the physics is validated twice" (4 min).
3. `hil_interface_diagram` — what the box simulates, the four outputs, the three inputs, scaling; the I/O table (4 min).
4. `dcsim_rt.slx` running at 1 µs with the same eight cases passing — "this is the model you convert; it is already fixed-step and explicit" — and the step-sweep table (3 min).
5. His six questions (solver step, import path, DI/DO levels, AO range and noise, PC link, venue) and the joint test sequence (open loop → node decisions → closed loop → latency) (rest).

Bring: the laptop with MATLAB R2026a and the repo, the brief printed (Thai), the diagram printed A3, and — if a NUCLEO-H743 exists by then — one node flashed with M3 so he can see the TRIP pin on his own scope from a replayed waveform.

## 4. What we answer him now (summary of the brief)

- Yes: four analog outputs (i_L, v_bus, i_rack, v_out) as 0–10 V, scaled per the table; three digital inputs (TRIP ×2, FAULT_CMD) and one digital output (SYNC), 3.3 V logic.
- Simulate: the MODEL.md 0.4.4 segment — source, feeder, 800 V bus (+ bus storage), ORing + input filter, averaged converter with its controller and UVLO, 48 V bus + storage, constant-power GPU load with UVLO, two fault branches, the workload generator, a fault-scenario block, two breakers, output scaling. 11 states, all explicit.
- DAC: 16-bit at 5 MS/s is ample (the nodes sample at 500 kSa/s behind a 100 kHz filter). The quantity that matters is the solver step — and in which form he takes the model.

## 5. Decisions needed from Wasin

1. OK to build `dcsim_rt` (level B) now — it is a second independent implementation like Simscape, not a change to the core or the generator.
2. OK to add the breaker element as MODEL.md 0.4.5 (text + the rule above), used by `dcsim_rt` and later by the bench dataset.
3. Whether to send the brief to the professor as is (he forwards it) or to let him present it himself with the diagram only.
