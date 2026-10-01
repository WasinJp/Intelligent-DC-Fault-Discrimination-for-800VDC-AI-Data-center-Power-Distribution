# M6_M7_TEST_PROCEDURE.md — CAN link, record upload, cadence on the target, bench control

Companion to M3_TEST_PROCEDURE.md (do that first on each node). Everything below is **built,
untested** (MILESTONES.md M5-target / M6 / M7).

## A. Cadence learner on the node (M5 target)

1. Feed a periodic workload (bench profile or a signal generator: square wave 0.3–3 s period with a
   20–200 ms burst comb) into the current input for ≥ 8 s. `cadence` → `relearns` increasing every
   200 ms, `history` increasing by 5 000 per second, `tier 1: T ... strength ...` matching the generator.
2. `timing` → `relearn` mean / max cycles. Paste into TIMING.md §3. If mean > 19.2 M cycles (40 ms)
   change `CADENCE_PERIOD_MS` (cadence_task.h) to 1000 and note the CPU share.
3. Host cross-check: `capture` a record while the profile runs; decode it (`record_decoder.py`) and run
   `fx_cli extract --cadence f32` on the matching fixture-like record with its slow stream — not
   possible for bench records (no slow stream in the upload); instead compare `status` phase_err against
   the `cadence` tiers by hand for two or three events.

## B. CAN link and combined decision (M6, two nodes)

1. Wire PD0/PD1 of both Nucleos through TCAN1042 transceivers on a short twisted pair, 120 Ω at each end.
2. `can` on each node → `rx frames` increasing when the other node decides (fire `selftest` events with a
   signal generator step). `peer:` line shows the other node's decision, p_trip, onset sample.
3. Feeder `status` after a simultaneous event → `used_two_node 1` when the rack's three feature frames
   arrived within `can_wait_us` (settings; default 50 µs). Expectation (DEVIATIONS.md #13): at 5 Mbit/s
   the 3 × 64-byte frames take ≈ 150–250 µs, so the two-node path will be taken only with a larger
   `can_wait_us`; measure the arrival delay (`rx@` sample minus the rack's `onset` + 125) and decide
   the wait with the professor. `cyc_close_to_trip` grows by the wait.
4. Two-node decision parity: replay the same fixture pair (feeder and rack records of one event, `tools/
   replay_waveforms.py --node both`) through both front ends with one SYNC; compare the feeder's decision
   with `reference_scores.csv` (model `both`) for that event.

## C. Record upload over USB (M6)

1. Connect the node's user USB (CN13) to the PC; a CDC serial port appears (VID 0483 PID 5740, test ids).
2. `python firmware/tools/record_decoder.py --port COMx --out data/bench_records/test` then `capture` on
   the node → one `.bin` and one row in `node_trailers.csv`.
3. Fire an event: a frame arrives 5 ms after the onset. Then on the host:
   `fx_cli extract --dir data/bench_records/test --out host.csv` and
   `compare.py features data/bench_records/test/node_trailers.csv host.csv`
   → onset index identical and features bit-identical: the node's features on the bench record are
   reproduced by the host from the uploaded record (the record starts at the decision's baseline start).

## D. Bench control (M7)

1. Flash `fx_bench_control.hex`; terminal on its VCP; `status` → `armed 0` with the key off.
2. Load gates: `profile gates 0x1f` / `0x00` → all five branches on / off (LED on each driver). `profile
   step 0.4 5` → staircase to the subset closest to 40 % over 5 ms (scope on two gate lines: 1 ms apart).
3. Cadence: `profile set T1 1.0`, `profile start` → SYNC pulses at every rising edge, gates stepping
   low ↔ high with bursts; `status` shows `t` advancing.
4. UVLO: lower the 12 V supply slowly → at 9.6 V for 100 µs all gates drop (`uvlo TRIPPED`, red LED),
   back above 10.1 V they return. Set thresholds with `uvlo set 9.6 10.1`.
5. DAC replay: `python firmware/tools/replay_waveforms.py --node rack --n 5`, then from a terminal
   script: `replay load 5200` + the 20 800 bytes of a `.dac` file, `replay start` → SYNC then 5.2 ms on
   PA4/PA5 at 1 MSa/s (scope). Feed PA4/PA5 to a node's replay jumper inputs: this is the M4 latency test.
6. Faults: with the key OFF, `fault rack 0 1 now` → `REFUSED`. With the key ON and a second person
   present (SCALING_SHEET §7): `fault rack 0 1 now` → one 5 ms pulse on the rack fault switch, SYNC on
   the scope, both nodes decide. `fault rack 0 1 edge 500` schedules 500 µs after the next cadence edge.
7. Whole plan: `python firmware/tools/bench_run.py --bench COMa --feeder COMb --rack COMc --out
   data/bench_runs/run1` with `record_decoder.py` running on both nodes' USB ports; `--dry-run` first.
