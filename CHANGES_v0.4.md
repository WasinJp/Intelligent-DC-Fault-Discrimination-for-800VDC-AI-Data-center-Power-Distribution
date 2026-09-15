# v0.4 — rack conversion stage (800 VDC → 48 V), per-rack node, 48 V faults

Spec: `MODEL_v0.4_conversion_stage_spec.md`. The v0.3 core (`model.py`), extractor (`features.py`) and confirm study are untouched. The switch is `events.CORE_VERSION` (`"v0.4"` default; `"v0.3"` reproduces dataset v1 exactly).

## Files (drop-in)

| file | change |
|---|---|
| `dcsim/model_v04.py` | new core, 11 states. Averaged DC-DC with PI voltage loop, inner-loop lag, output current limit, loss model; input L-C filter and storage C_in; controlled current-source front end with ramp-rate limit when `smooth_on`; 48 V bus, POL constant-power load with its own UVLO; 48 V fault branch. Checks (e) steady state, (f) voltage loop vs linear model, (g) node energy balance / slew / tracking, (h) 48 V current limit, (d) history tier on both nodes. |
| `dcsim/events.py` | `CORE_VERSION`; `draw_system_v04` (§4 sweep: C_in takes the 1–50 mF range, C_bus → 0.1–2 mF distribution capacitance, converter/front-end/48 V parameters); `sanity_gate_v04` (800 V loop with C_bus + C_in, 48 V loop with POL CPL); labels `bolted_48`, `high_z_48`; 48 V fault windows; under v0.4 the GPU workload is one regime — smoothing is the front end's job. |
| `dcsim/synth.py` | rack-node observables `rack_fast_i/v`, `rack_slow_i/v` (converter output current, 48 V bus), same front end, own full scale, independent noise substream. Feeder streams unchanged. |
| `dcsim/dataset.py` | core selection; 48 V fault indices; rack streams and v0.4 truth rows (`i_f48`, `v_Cin`, `i_pol`, `load_on48`, `P_in`) stored; `load_obs(e, config, node="feeder"|"rack")`. |
| `dcsim/studies.py` | `DECISION` for 48 V classes (TRIP); `TRIP_800` / `TRIP_48`; `_metrics` reports `missed_800`, `missed_48`; `feature_table(..., node=)` normalised to the node's rating; `feature_table_both`; `node_study` — feeder-only, rack-only, feeder + rack over 10 seeds, with "detected at either node" as the onset rule for the combined relay. |
| `scripts/validate_model.py` | runs the v0.3 set or the v0.4 set (eight checks) by `CORE_VERSION`. |
| `scripts/run_node_study.py` | new: node study + prediction printout (gray zone by smoothing state, onset-found by node and fault side, C_in terciles). |
| `scripts/generate_dataset.py`, `run_studies.py` | unchanged logic; work on either core. |

## Run

```
python scripts/validate_model.py                         # 8 checks, ALL PASS expected
python scripts/generate_dataset.py data/events_v04.h5 200   # 9 classes x 200 = 1 800 events, ~40 min
python scripts/run_node_study.py data/events_v04.h5     # feeder / rack / both
python scripts/run_studies.py data/events_v04.h5        # feeder-only tables as before
```

## Pre-registered predictions (spec §7) — read these against the run

1. Feeder-only Layer 2 misses > 80 % of `high_z_48` and > 80 % of `bolted_48`; rack node catches > 99 % of both.
2. Feeder gray zone for 800 V high-Z falls from 66 % toward 40–50 % when `smooth_on`; stays near 66 % when off.
3. Feeder high-Z (800 V) misses track C_in terciles at least as steeply as C_bus did on v1 (0 → 18 %).
4. Workload-aware gain persists at the feeder; stronger at the rack node.
5. Feeder + rack matches or beats v1 on 800 V faults and covers 48 V faults; this is the architecture claim.

If (1) fails the converter model is too transparent (current limit or input filter), not the classifier.

## Pilot (54 events)

All validation checks pass (history tier 3.1e-4 on both nodes). Feeder onset fires on 100 % of 800 V faults, 83 % of 48 V faults, 72 % of benign (small steps attenuated by the stage); rack onset fires on 100 % of 48 V faults, 28 % of 800 V faults. The two nodes see disjoint fault sets. ~0.7 s/event, 0.21 MB/event.

## Open

OPEN-19 C_out range is an assumption. OPEN-20 charge-state controller. OPEN-21 multi-shelf rack. Simscape cross-check (i) is the independent-implementation credential and can be built from the spec in parallel.
