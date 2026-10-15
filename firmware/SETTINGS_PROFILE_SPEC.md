# SETTINGS_PROFILE_SPEC.md — named settings profiles (HIL / bench), Layer 1 on, bench-control items (milestone S1)

**Written:** 2026-10-15. Owner: Wasin (design sessions). Implementer: Claude Code, one session, host-testable. Status: DRAFT for Wasin's review. Working rules: `FIRMWARE_SPEC.md` §1 unchanged — `common/` feature code is the contract and is not touched; every change host-tested; deviations into `docs/DEVIATIONS.md`.
**Read first:** `FIRMWARE_SPEC.md` §3, §7.1, §8; `node/settings.[ch]`, `node/cli.c` (`print_status`, `settings` command), `node/stream.c` (where `fs_i`/`fs_v`, `theta`, `l1_*` are consumed), `common/fx_relay.h`; `hardware/SCALING_SHEET.md`; `simscape/HIL_MODEL_INTERFACE.md` §2 (AO full scales); `DEADLINE_STUDY_2026-10-15.md` §3 (why Layer 1 goes on); `README_RT.md` §check (k) (θ = 0.067, the retrained model).

## 0. Why

Today the node has one set of defaults per role (bench scaling, θ = 0.5, Layer 1 off) and a dozen `settings set` keys. For the HIL the node must read the box's analog outputs (through the panel or scaled in the model), use the retrained model's threshold, the training-domain onset floors, and — new from the deadline study — a per-sample Layer 1 at the rack node. Getting any of these wrong gives plausible but wrong features *silently*. So: **named profiles** chosen by one command, printed in `status`, with the numbers below as the single source.

## 1. Node: profiles

### 1.1 Interface
- New key `settings profile <hil|bench>`: loads the profile table for the jumpered role into `g_set` (not saved until `settings save`), prints the table. `settings show` and the first line of `status` print `profile <name> role <feeder|rack> model <id>`. Unknown name → usage line.
- `settings_t` gets `uint32_t profile` (0 bench, 1 hil); `version` 1 → 2; a stored v1 block is migrated by loading the bench profile for its role and keeping its calibration (`gain_*`, `offset_*`) — record in DEVIATIONS.
- Every value remains individually overridable with `settings set` afterwards (calibration will override `gain_*` / `offset_*`).

### 1.2 Profile tables

Design-point bases (MODEL.md / `params.json`): P_rated 132 kW, V_ref 800 V, V_ref48 = `V_ref48` of params.json (50 V), I_rated = 165 A, I_out_rated = 2 640 A, I_lim = 1.75 × I_rated, I_lim_out = 1.4 × I_out_rated (take the exact factors from `params.json`, do not hard-code 1.75 / 1.4 if they differ).

| key | **hil / feeder** | **hil / rack** | bench / feeder (today's defaults) | bench / rack | note |
|---|---|---|---|---|---|
| `I_rated` | 165 | 2 640 | 2.5 | 10 | per-unit base of the features |
| `V_ref` | 800 | 50 | 48 | 12 | |
| `fs_i` | 2·I_lim = **577.5** | 2·I_lim,out = **7 392** | 5.0 | 130 | onset floor 0.004·fs — **training-domain value** (synth.py `fs_i = 2·I_lim`), not the ADC range; pinned #3 |
| `fs_v` | 1.25·V_ref = **1 000** | **62.5** | 60 | 15 | synth.py `fs_v = 1.25·V_ref` |
| `gain_i` [A/code] | 2.64·165·k/65536 = **6.69e-3** | 16.5·2 640·k/65536 = **0.6687** | 7.63e-5 | 2.52e-3 | k = 3.3 / 3.28 = 1.0061 (ADC FS 3.3 V ↔ AO FS at the node 3.28 V); nominal — two-point calibration replaces it |
| `gain_v` [V/code] | 1.45·800·k/65536 = **1.781e-2** | 1.45·50·k/65536 = **1.113e-3** | 1.06e-3 | 2.65e-4 | same |
| `offset_i`, `offset_v` | 0 | 0 | 0 | 0 | unipolar AO; calibration may set a few codes |
| `theta` | **0.067** | **0.067** | 0.5 | 0.5 | retrained 5 µs model, held-out calibration (README_RT check (k)); bench keeps 0.5 until its own dataset exists |
| `l1_di` [p.u.] | off | **2.0** | off | off | Layer 1 per-sample |Δi| vs the running baseline, 5 µs-smoothed (FIRMWARE_SPEC §7.1). Validated 15 Oct on the `hil_5us` tables (30 000 benign): benign window-max `di_max` = 1.128 max / 0.374 p99.9 → 1.77× margin at 2.0; catches 57 % of bolted_48 inside the window (70 % at 1.5, 85 % at 1.0), the rest trips in Layer 2 at 0.35 ms. **Candidate 1.7 (1.5× margin) after the hardware idle soak shows the per-sample benign maximum.** |
| `l1_v` [p.u.] | **0.80** | off | off | off | Layer 1 v_bus < 0.80 p.u. Validated 15 Oct: benign `v_min` ≥ 0.908 (p0.1 0.981) → a 20 % dip threshold vs a 9.2 % worst benign dip, 2.2× margin; catches 83.5 % of bolted/resistive 800 V inside the window (80 % at 0.75, 87 % at 0.85 — 0.85 rejected, 1.6× margin with droop variation). |
| `model_id` | 0 (by role) | 0 | 0 | 0 | the retrained `fx_model_data.h` (S1 ships it, §3) |
| `can_wait_us` | 50 | 50 | 50 | 50 | unchanged |
| `onset_tol` | 500 | 500 | 500 | 500 | unchanged |

Notes for the table: training used per-event `fs_i = 2·I_lim` with I_lim drawn in 1.5–2× rated, so the HIL floor is within ±15 % of the per-event training floor — stated, accepted (HANDOFF §4). If the AO is scaled to 3.28 V in the model (no panel divider), the gains are identical; if the box's AO is 0–10 V and the panel divides by 0.3280, also identical. Only a different `ao_fs_V`/divider pairing changes k.

### 1.3 Layer 1 — pre-registered validation before it ships
Layer 1 ON must not add false trips. Two checks, both host-side:
1. **Table check — DONE 15 Oct 23:40 (Wasin):** on `data/hil_frontend_aa/features_*_hil_5us.csv`, W = 0.25 ms: benign events with rack `di_max > 2.0`: **0 of 30 000**; benign with feeder `v_min < 0.70`: **0 of 30 000** (and 0 below 0.80, min 0.908). Coverage inside the window: bolted_48 `di_max > 2.0` 57 %; bolted/resistive_pp `v_min < 0.80` 83.5 %. *Recorded mis-specification:* the first draft expected ≥ 90 % from the deadline study, which counts absolute `i_rack > 2 × rated` anywhere in the record on the raw stream; `di_max` is the rise above the pre-event baseline, inside the window, on the node stream — a different quantity, so 90 % was not the right target. Layer 1 is for the fastest events; Layer 2 covers the rest. (`di_max` is the window maximum of the 10 µs-smoothed |Δi|; the per-sample 5 µs-smoothed value is noisier, hence the margin rule ≥ 1.5× and the conservative 2.0 first.)
2. **Fixture check (Claude Code):** `fx_cli stream` gets `--l1-di <pu>` / `--l1-v <pu>` and reports the count of records where Layer 1 fired and at which sample; on the committed fixture set with the HIL thresholds: **benign L1 trips = 0**, and for `bolted_48` records the L1 sample is reported (expect median < 50 samples after onset).
If either check fails, Layer 1 stays off in the profile and the failure goes into DEVIATIONS with the numbers.

### 1.4 Acceptance (host, `ctest`)
- `unit_settings`: `settings profile hil` on a feeder/rack struct yields the §1.2 columns exactly (doubles compared to 1e-12 relative, `INFINITY`/`-INFINITY` for "off"); v1 → v2 migration keeps `gain_*`/`offset_*` and sets `profile = bench`; CRC round trip.
- `status` / `settings show` text contains `profile hil role rack model ...` (string test in the unit test through the print callback).
- Fixture check 1.3(2) passes with the numbers pasted into `MILESTONES.md` row **S1**.

## 2. Node build: `FX_MCU` option
`node/CMakeLists.txt` and `bench_control/CMakeLists.txt`: `option`/cache variable `FX_MCU` ∈ {`H743`, `H753`}, default `H753`; selects exactly one of `STM32H743xx` / `STM32H753xx` (the device header admits one); linker script unchanged (`STM32H743ZITX_FLASH.ld` fits both). `firmware/host/README.md` gets the two build lines. Wasin's board today is an H743 (`-DFX_MCU=H743`); note the silicon-revision check (rev Y = 400 MHz max → `clock.c` would need a 400 MHz tree; **do not change `clock.c` in this milestone**, only document the check in `M3_TEST_PROCEDURE.md` §1).

## 3. Model export (Wasin runs, Claude Code verifies)
Wasin: `python firmware/tools/train_model.py --cache data/hil_frontend_aa_hil5 --early-stopping off --features firmware/host/tests/fixtures/reference_features.csv --scores firmware/host/tests/fixtures/reference_scores.csv` with `features_feeder.csv` / `features_rack.csv` = the `hil_5us` chain tables copied into that dir → new `fx_model_data.h`, `host/models/models.json`, regenerated `reference_scores.csv`. Claude Code: rerun `m2_model_agreement` (bit-identical), update `MILESTONES.md` M2 row with the new training-set hash and model sizes, keep the old header as `host/models/v1xl6k_ref/` for reference. The committed `nodes_v1xl6k` model is not used on hardware (README_RT check (k), consequence a).

## 4. Bench control (same session, small)
- `dac_replay.c`: keep `DAC_OUTPUTBUFFER_ENABLE` (unbuffered output ≈ 15 kΩ would limit bandwidth into the cable); add a code offset `dac_offset_codes` (default 248 ≈ 0.2 V, the buffered floor; console `replay offset <codes>`) added at `replay load` and saturated at 4095; `tools/replay_waveforms.py` writes the offset into `manifest.json` so the node's offset calibration removes it. Record the decision in DEVIATIONS (supersedes "buffer off").
- `board_bc.h`: `DEMO_FAULT` output (PE11 "D5", candidate) and `RE_ARM` output (PE13 "D3", candidate) with console `fault hil` / `rearm hil` (pulse 1 ms) — only used if the HIL takes FAULT_CMD/RE_ARM from the bench control instead of ControlDesk.
- Text: `74HC123` → `74HC221` in `board_bc.h` / `fault.h` / `bench_run.py`; selector comments → "manual terminal block under option B; outputs kept for option C"; `NUCLEO-H743ZI2` → `NUCLEO-H753ZI (H743 pin-compatible)`; `FIRMWARE_SPEC.md` §9 "150 kHz" → "100 kHz", §2 board line → H753ZI (`FX_MCU`).

## 5. Out of scope
`clock.c`, any `common/` feature code, CAN protocol, dashboard, N6 display, telemetry stream (F7).

## 6. Deliverables and order
1. §2 `FX_MCU` (10 min) → 2. §1 profiles + unit test → 3. §1.3(2) `fx_cli stream --l1-*` + fixture numbers → 4. §4 bench-control items + text → 5. after Wasin's export, §3 M2 rerun → `MILESTONES.md` S1 row + DEVIATIONS entries. PR description lists every file touched and every deviation.
