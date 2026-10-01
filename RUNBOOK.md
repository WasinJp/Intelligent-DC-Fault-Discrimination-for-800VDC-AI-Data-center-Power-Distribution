# RUNBOOK.md — what to run, in what order (written 2026-09-18)

All commands from the repo root with the venv active (`(.venv) PS ...\repo>`), except MATLAB.

## Order (updated 2026-09-18, core 0.4.4). Rule: validation before generation.
1. **A** Simscape, all eight cases - done.  2. **B** validate the core - done (ALL PASS incl. (j)).  3. **C** regenerate v1-large on 0.4.4 and
prove nothing in Layer 2 moved.  4. **D** only then the 30 000-benign run.  Commit after each step.

## A. Simscape cross-check - DONE, 8 of 8 PASS (2026-09-18, build 18h). Re-run only if the core or the builder changes.
```
>> cd simscape
>> crosscheck('all')
```
Figure for the review package and the pitch (uses the sim_*.mat files that crosscheck wrote):
```
python scripts/plot_simscape_overlay.py high_z_48      # -> figures/fig5_simscape_overlay.png
python scripts/plot_simscape_overlay.py bolted_48 figures/fig5b_simscape_overlay_bolted48.png
```
Commit now: `git add -A; git commit -m "core 0.4.4: held-fault tiers, check (j); Simscape check (i) 8/8; operating study"`.
`dcsim_shelf.slx`, `data/simscape/*.mat` and `crosscheck_log.txt` are worth committing too (they are the evidence).

## B. Core validation (1 min)
```
python scripts/validate_model.py          # (a)-(h) and the new (j): must end with ALL PASS
```

## C. Regenerate v1-large on core 0.4.4 (about 1 h with 4 shards; keep the old events_v1large.h5 until C passes)
```
0..3 | % { Start-Process powershell -WorkingDirectory $PWD -ArgumentList "-NoExit","-Command","& .\.venv\Scripts\python.exe scripts\generate_dataset.py data\events_v1large044_s$_.h5 200 20260907 --large --shard $_/4" }
```
Each window ends with "wrote 1550 (or 1551) of 6201 events". Then:
```
python scripts/check_postrecord.py "data/events_v1large044_s*.h5"
python scripts/run_node_study.py "data/events_v1large044_s*.h5" data/nodes_v1large044
python scripts/compare_feature_tables.py data/nodes data/nodes_v1large044
```
Registered before the run: check_postrecord prints "clean" for all nine labels; the node-study table equals
the v1-large one; compare_feature_tables prints REGRESSION PASS (both tables bit-identical - the held-fault
rule never acts inside the event window). If it does not, stop and send the printout.

## D. v1-xl: 30 000 benign, to bound the false-trip rate (overnight; only after A is 8/8 and C passed)
Disk: about 5x the size of `data/events_v1large.h5`.
```
0..3 | % { Start-Process powershell -WorkingDirectory $PWD -ArgumentList "-NoExit","-Command","& .\.venv\Scripts\python.exe scripts\generate_dataset.py data\events_v1xl_s$_.h5 200 20260907 --large --benign 10000 --shard $_/4" }
```
Each window ends with "wrote 7800 of 31200 events". Then:
```
python scripts/check_postrecord.py "data/events_v1xl_s*.h5"
python scripts/run_node_study.py "data/events_v1xl_s*.h5" data/nodes_v1xl
python scripts/run_operating_study.py data/nodes_v1xl
```
Registered before the run: feeder + rack false trips 0.03-0.08 % at the default threshold, i.e. 9-24
events of 30 000; the 95 % upper limit is below 0.1 % only if the count is <= 19. Missed 800 V 0.3-0.5 %,
missed 48 V 0.7-1.2 % (the fault set is the same size, so these should not move).

## Optional, any time (15-30 min, no h5): second independent run of the operating study
```
python scripts/run_operating_study.py data/nodes
```

## E. Operating-study results — FINAL (2 Oct 2026, `data/nodes_v1xl6k`, early stopping off)
30 000 benign + 6 000 faults, feeder + rack, 5-fold x 10 seeds, mean +/- std in %.

| false-trip budget | calibration | false trips | missed | missed 800 V | high-Z | missed 48 V |
|---|---|---|---|---|---|---|
| 0.10 % | held-out | 0.09 +/- 0.01 | 0.31 +/- 0.05 | 0.33 +/- 0.06 | 0.99 +/- 0.17 | 0.29 +/- 0.06 |
| 0.05 % | held-out | 0.05 +/- 0.01 | 0.60 +/- 0.09 | 0.66 +/- 0.11 | 1.97 +/- 0.31 | 0.50 +/- 0.08 |
| 0.02 % | held-out | 0.02 +/- 0.00 | 2.16 +/- 0.17 | 2.37 +/- 0.17 | 6.91 +/- 0.51 | 1.85 +/- 0.20 |

By window, default threshold: 0.25 ms 0.03 / 0.42 / 1.25 / 0.63; 1 ms 0.04 / 0.46 / 1.36 / 0.53
(false trips / missed 800 V / high-Z / missed 48 V). Gate-2 percentile rows 57.8 / 39.6 %.

**History of this number.** v1-large 0.48 % -> v1xl (1 200 faults) 1.26 %, a class-imbalance effect; the
registered prediction failed -> v1xl6k 0.48 %, held -> early stopping found by the firmware export, `_fit`
fixed, rerun -> 0.31 %. Registered before that rerun: "about 0.40 %" — held in direction, better than
predicted. v1-large results are unaffected by the `_fit` fix.

Below 0.05 % the dataset still cannot support an operating-point claim; 0.02 % costs 2.2 % missed.

## E.1 Superseded — operating study on v1-large (2026-09-18)
Kept for the prediction scorecard, which is the record of what was registered and how it scored.
Feeder + rack, v1-large, 5-fold x 10 seeds, mean +/- std in %.

| false-trip budget | calibration | false trips (realised) | missed | missed 800 V | high-Z | missed 48 V |
|---|---|---|---|---|---|---|
| 0.10 % | in-sample | 0.10 | 0.49 ± 0.21 | 0.38 ± 0.27 | 1.15 ± 0.81 | 0.65 ± 0.25 |
| 0.10 % | **held-out** | **0.10 ± 0.04** (0.04-0.16) | **0.48 ± 0.16** | 0.35 ± 0.20 | 1.05 ± 0.61 | 0.68 ± 0.22 |
| 0.05 % | in-sample | 0.04 | 1.78 ± 2.00 | 1.72 ± 1.77 | 4.95 ± 4.78 | 1.88 ± 2.42 |
| 0.05 % | held-out | 0.07 ± 0.04 (0.02-0.14) | 0.87 ± 0.35 | 0.77 ± 0.46 | 2.30 ± 1.38 | 1.02 ± 0.36 |
| 0.02 % | in-sample | 0.02 | 2.41 ± 2.72 | 2.30 ± 2.21 | 6.65 ± 5.97 | 2.58 ± 3.59 |
| 0.02 % | held-out | 0.03 ± 0.03 (0.00-0.10) | 2.68 ± 0.47 | 2.68 ± 0.26 | 8.00 ± 0.84 | 2.67 ± 1.06 |

Two-node relay by decision window, default threshold: 0.25 ms 0.07 ± 0.04 / 0.37 ± 0.10 / 1.10 ± 0.30 /
0.93 ± 0.23; 0.5 ms 0.04 / 0.47 / 1.40 / 0.92; 1 ms 0.05 / 0.42 / 1.25 / 1.05 (false trips / missed 800 V /
high-Z / missed 48 V). Gate 2 percentile rows: gray zone (800 V high-Z) 72.0 / 57.0 / 36.5 % at 0 / 0.26 /
2.52 % false trips (max / 99.9th / 99th percentile of the benign envelope).

Prediction scorecard (registered in `scripts/run_operating_study.py` before the run):
P1 in-sample 0.1 % reproduces 0.33 ± 0.15 within one std — **held, marginally** (0.49 ± 0.21).
P2 held-out 0.1 %: missed <= 0.7 % — **held**; realised false trips "above the in-sample value" — **failed**:
   the mean is 0.10 %, calibration is unbiased, it only adds spread (0.04-0.16 %).
P3 held-out missed >= 2x in-sample at 0.02 % — **failed** (2.68 vs 2.41). In-sample is not optimistic
   there, it is unstable (std 2.7): one benign event sets the threshold and the seed decides which.
P4 Gate-2 percentile rows — **held exactly**.  P5 the 0.25 ms window matches the 1 ms table — **held**.
Reading: the 0.1 % point is supported with held-out calibration; below 0.05 % v1-large cannot support
any operating-point claim. That is what v1-xl is for.
