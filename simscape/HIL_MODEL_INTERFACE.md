# dcsim_rt_hil — the model we hand to the dSPACE team (interface, parameters, first tests)

**Written:** 2026-10-15. **Status:** DRAFT — files written, not yet built in MATLAB (Wasin runs `rt_hil_check` first). **For:** the dSPACE alumni team (ASEAN distributor) and Prof. Supachai's review; EN with a Thai summary at the end.
**Files (repo `simscape/`):** `dcsim_rt_hil_plant.m` (the model body), `dcsim_rt_step.m` + `dcsim_rt_derivs.m` (the validated physics core, unchanged), `dcsim_rt_hil_params.m` (tunable parameters), `build_dcsim_rt_hil.m` (builds `dcsim_rt_hil.slx`), `dcsim_rt_hil_y0.m` (steady state), `rt_hil_check.m` (validation), `dcsim_rt_hil_demo.m` (desktop demo), `ctrldesk_to_simmat.m` (box capture → comparator).

## 1. What the model is

One real-time plant: 800 VDC source → feeder (L, R) → 800 V bus (C, optional storage) → rack converter (averaged, cascaded voltage/current loops, input UVLO) → 48 V storage bank → GPU constant-power load with its own UVLO; two fault branches (800 V side, 48 V side) and a series arc; two ideal breakers (SSCB) opened by the external TRIP lines. 11 states, explicit RK4 at a fixed step, no Simscape blocks, no continuous states, no algebraic loops, doubles. Validated: bit-identical to the Python reference at 1 µs; 8 reference cases within 1 % up to 5 µs; 10 µs within 0.5 %; 20 µs fails the 48 V fault cases (`README_RT.md`). The HIL wrapper adds only bookkeeping (fault scenario, workload generator, re-arm, SYNC, scaling) — `rt_hil_check` proves the eight cases are unchanged through it.

**Structure (Simulink):** 4 Inports → one MATLAB Function block (`plant`, which calls `dcsim_rt_hil_plant`) → 8 Outports. Parameters are `Simulink.Parameter` objects, storage class ExportedGlobal (tunable in ControlDesk), fed through Constant blocks. Solver: FixedStepDiscrete, step `hil_dt`.

## 2. Ports

| # | port | dir | type | meaning | hardware |
|---|---|---|---|---|---|
| In 1 | `TRIP_feeder` | in | 0/1 | feeder node TRIP, sampled every step; held ≥ `brk_delay` → feeder breaker opens (latched) | DI1 (3.3 V node logic → level shift) |
| In 2 | `TRIP_rack` | in | 0/1 | rack node TRIP | DI2 |
| In 3 | `FAULT_CMD` | in | 0/1 | fault trigger, rising edge (OR-ed with parameter `fault_trigger`) | DI3 (optional; ControlDesk can trigger instead) |
| In 4 | `RE_ARM` | in | 0/1 | re-arm, rising edge (OR-ed with `rearm_cmd`) | DI4 (optional) |
| Out 1–4 | `AO1..AO4` | out | V, 0..`ao_fs_V` | i_L, v_bus, i_rack, v_out scaled: full scale = `ao_pu_n` × base (2.64 × I_rated, 1.45 × V_ref, 16.5 × I_out_rated, 1.45 × V_ref48); saturated — the saturation is part of the design (same as the node's own clip) | AO1–AO4 → adapter panel → nodes |
| Out 5 | `SYNC` | out | 0/1 | 1 for `sync_width` from fault inception | DO1 → both nodes + scope |
| Out 6–7 | `BRK_F`, `BRK_R` | out | 0/1 | breaker state (1 closed) | ControlDesk (DO optional) |
| Out 8 | `SIG` | out | 28×1 | ControlDesk signals (below) | none |

**SIG (test points, named):** 1 `k` step count · 2 `t` [s] · 3 `P_gpu` [W] · 4 `fault_active` · 5 `fault_pending` · 6 `t_inception` [s] (−1 none) · 7 `clear_f_us` inception → feeder breaker open · 8 `clear_r_us` · 9/10 `trip_f_steps`, `trip_r_steps` · 11 `wl_edge` (1 on a workload rising edge) · 12 `wl_phase` · 13 `conv_on` · 14 `load_on48` · 15 `i_f` · 16 `i_f48` · 17 `v_Cin` · 18 `P_in` · 19 `i_co` · 20 `v_c` · 21 `fault_type_active` · 22 `V_arc` · 23 `rearm_count` · 24 `n_faults` · **25–28 `i_L`, `v_bus`, `i_rack`, `v_out` in A / V, unclipped** (the ControlDesk plots and the check (i) capture).

Bases: I_rated = P_rated / V_ref = 165 A, I_out_rated = P_rated / V_ref48 = 2 640 A at the design point (132 kW, 800 V, 50 V).

## 3. Tunable parameters (ControlDesk)

| group | name | default | range / meaning |
|---|---|---|---|
| fault | `fault_type` | 0 | 0 none · 1 800 V branch · 2 48 V branch · 3 series arc |
| | `fault_Rf`, `fault_Lf` | 3 Ω, 2 µH | 800 V fault: 1 mΩ (bolted) … 10 Ω (high-Z); 0.5–10 µH |
| | `fault_Rf48`, `fault_Lf48` | 20 mΩ, 0.5 µH | 48 V fault: 0.5 mΩ (bolted) … 100 mΩ (high-Z); 0.1–2 µH |
| | `fault_Varc` | 25 V | series arc voltage 15–40 V (type 3) |
| | `fault_mode` | 0 | 0 inception now · 1 on the next workload rising edge (the "hidden in a load step" demo) |
| | `fault_trigger` | 0 | ControlDesk button: 0 → 1 fires once |
| | `step_dP`, `step_ramp` | 0 W, 2 ms | benign load step applied at the trigger (0.4 × P_rated = the reference step case; type 0 + step = pure benign event) |
| workload | `wl_on` | 1 | 0 = constant `wl_P0` |
| | `wl_P0`, `wl_dP1`, `wl_T1`, `wl_duty1`, `wl_ramp1`, `wl_jit1` | 0.5 P_r, 0.3 P_r, 1 s, 0.6, 2 ms, 1 % | tier-1 iteration cadence (0.3–3 s, 0.1–0.8 P_rated, ramps 0.5–10 ms, jitter ≤ 2 %) |
| | `wl_dP2`, `wl_T2`, `wl_duty2`, `wl_ramp2`, `wl_jit2` | 0.1 P_r, 80 ms, 0.5, 1 ms, 1 % | tier-2 bursts during the compute phase (0 = off) |
| | `wl_seed` | 12345 | xorshift32 seed — same seed, same workload |
| config | `hil_dt` | 5 µs | model step = solver FixedStep (**≤ 5 µs required, 10 µs usable, 20 µs not**) |
| | `qs_dt_min` | 1.5 µs | quasi-static fault-branch floor — do not change |
| | `brk_delay` | 0 | TRIP hold before the breaker opens (0 = next step) |
| | `uvlo_tol` | 0.5 | 0.5 = UVLO timers count steps (HIL); 0 = reference float accumulation |
| | `sync_width` | 20 µs | SYNC pulse (≥ 20 µs) |
| | `ao_fs_V` | 10 | AO full-scale volts: 10 (with the panel's 0.328 divider) · 4.5 · 3.28 (no divider) |
| | `rearm_cmd`, `run_enable` | 0, 1 | ControlDesk re-arm button; hold |
| | `ao_pu_1..4` | 2.64, 1.45, 16.5, 1.45 | AO full scale in p.u. (= the node front-end clip) |

Fixed (not tunable): `pv` (36 physics parameters, MODEL.md) and `y0` (steady state) — set at build from the design point; a different operating point = rebuild (`dcsim_rt_hil_y0`).

## 4. Behaviour

- **Fault lifetime:** trigger → pending → inception (now, or on the next workload rising edge) → SYNC → fault held on; the breaker isolates it when TRIP arrives; everything stays until **re-arm**, which resets the states to `y0`, closes the breakers, clears the fault and timers — and leaves the workload generator running (the nodes keep their learned cadence).
- **Clearing time** = (step of breaker opening − step of inception) × dt, in `clear_f_us` / `clear_r_us`. It is quantised to `dt` and includes the box's DI sampling delay; the box's AO/DI latencies are reported separately (ask the team for the figures).
- **run_enable = 0** freezes the model (states held, outputs held) — for wiring checks.

## 5. Validation we do on the box (first session)

1. **Turnaround time** of `dcsim_rt_hil` with 4 AO + 4 DI + 1 DO configured, at `hil_dt` = 5 µs; if it overruns, at 10 µs. Reading: ≤ 5 µs planned (5 µs‑trained relay), 10 µs acceptable (10 µs‑trained relay, physics within 0.5 %), 20 µs not acceptable.
2. **Check (i) on the target:** for each of the 8 cases set `wl_on 0`, `wl_P0`, the fault parameters and `step_dP` as `rt_hil_check` does (we bring the eight parameter sets), fire `fault_trigger`, capture SIG 25–28 + SYNC in ControlDesk at the task rate, export, `ctrldesk_to_simmat.m` → `compare_simscape.py`. Expected: the same table as `rt_sweep` at that step.
3. **Closed loop:** nodes connected; a high‑Z 48 V fault; read `clear_r_us` (expected ≈ 350 µs at a 5 µs step).

## 6. Desktop checks before we come (Wasin)

```
% MATLAB R2026a, repo root on the path, cd simscape
T = rt_hil_check(5e-6, 'loop')      % 8/8 PASS, identical to rt_sweep — the wrapper changes nothing
build_dcsim_rt_hil('dcsim_rt_hil', 5e-6, shared)   % shared from load_case; writes dcsim_rt_hil.slx
T = rt_hil_check(5e-6, 'slx')       % same through the .slx
D = dcsim_rt_hil_demo('highz800');  % workload on, fault on the next edge, scripted TRIP -> clearing time ~ 0.35 ms
Simulink.exportToVersion('dcsim_rt_hil', 'dcsim_rt_hil_R20xx.slx', 'R20xx')   % their release
```

## สรุปภาษาไทย

โมเดล `dcsim_rt_hil` คือระบบจ่ายไฟ 800 VDC หนึ่งส่วน (แหล่งจ่าย → สายป้อน → บัส 800 V → คอนเวอร์เตอร์แร็ค → บัส 48 V → โหลด GPU) จำลองแบบ real-time ด้วย RK4 ขั้นเวลาคงที่ 11 สถานะ ไม่มีบล็อก Simscape ตรวจสอบแล้วว่าตรงกับโมเดลอ้างอิง Python ที่ 1 µs และผ่าน 8 กรณีทดสอบถึง 5 µs. **อินพุต 4:** TRIP จากโหนด 2 เส้น, FAULT_CMD, RE_ARM. **เอาต์พุต:** AO1–AO4 (กระแส/แรงดันที่จุด feeder และ rack สเกลเป็น 0–`ao_fs_V` V), SYNC (พัลส์ตอนเกิด fault), สถานะเบรกเกอร์ 2, และสัญญาณสำหรับ ControlDesk 28 ค่า (รวมเวลาตัดวงจรเป็น µs). **พารามิเตอร์ปรับได้ใน ControlDesk:** ชนิด fault และค่า R/L, โหมดเกิด fault (ทันที / ขอบโหลดถัดไป), ปุ่มสั่ง fault, ตัวสร้างโหลด GPU (คาบ แอมพลิจูด seed), ขั้นเวลา, สเกล AO. **ข้อกำหนดหลัก:** ขั้นเวลา ≤ 5 µs (10 µs ใช้ได้, 20 µs ไม่ได้), AO 4 ช่อง, DI 2–4, DO 1. **การทดสอบครั้งแรกกับบริษัท:** วัด turnaround time พร้อม I/O, รัน 8 กรณีอ้างอิงบนกล่องแล้วเทียบด้วยสคริปต์ของเรา, แล้วทดสอบวงปิดกับโหนดจริง.
