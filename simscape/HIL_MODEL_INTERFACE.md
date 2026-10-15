# dcsim_rt_hil — the model we hand to the dSPACE team (interface, parameters, first tests)

**Written:** 2026-10-15, revised 2026-10-16 after the model review (§8). **Status:** 16 Oct build (review fixes #1–#23, H1–H4, F1–F2): `rt_hil_check` 8/8 at 5 µs, loop and slx; the six demo runs re-done (`rt_hil_demo_*.png`): no workload steps, v_bus decays after a feeder trip (0.53 p.u. at +3 ms), clearing 380 / 375 µs, Layer-1 emulation 70 µs. Ready for the dSPACE team. **For:** the dSPACE alumni team (ASEAN distributor) and Prof. Supachai's review; EN with a Thai summary at the end.
**Files (repo `simscape/`):** `dcsim_rt_hil_plant.m` (the model body; 38 tunables), `dcsim_rt_step.m` + `dcsim_rt_derivs.m` (the validated physics core + breaker element), `dcsim_rt_hil_params.m` (tunable parameters), `build_dcsim_rt_hil.m` (builds `dcsim_rt_hil.slx`), `dcsim_rt_hil_y0.m` (steady state), `rt_hil_check.m` (validation), `dcsim_rt_hil_demo.m` (desktop demo), `ctrldesk_to_simmat.m` (box capture → comparator), `export_hil_param_sets.m` / `apply_hil_param_set.m` (`hil_param_sets.csv`), `dcsim_rt_hil_data.mat` (pv, y0 and the 38 parameter objects — written by the build, loaded by the model's PreLoadFcn; must sit next to the `.slx`).

## 1. What the model is

One real-time plant: 800 VDC source → feeder (L, R) → 800 V bus (C, optional storage) → rack converter (averaged, cascaded voltage/current loops, input UVLO, optional ramp-rate front end) → 48 V storage bank → GPU constant-power load with its own UVLO; two fault branches (800 V side, 48 V side) and a series arc; two ideal breakers (SSCB) opened by the external TRIP lines. 11 states, explicit RK4 at a fixed step, no Simscape blocks, no continuous states, no algebraic loops, doubles. Validated: bit-identical to the Python reference at 1 µs; 8 reference cases within 1 % up to 5 µs; 10 µs within 0.5 %; 20 µs fails the 48 V fault cases (`README_RT.md`). The HIL wrapper adds only bookkeeping (fault scenario, workload generator, re-arm, SYNC, scaling) — `rt_hil_check` proves the eight cases are unchanged through it.

**Structure (Simulink):** 4 Inports → one MATLAB Function block (`plant`, which calls `dcsim_rt_hil_plant`) → 8 Outports. Parameters are `Simulink.Parameter` objects, storage class ExportedGlobal (tunable in ControlDesk), fed through Constant blocks. Solver: FixedStepDiscrete, step `hil_dt`. **Data:** `pv`, `y0` and the parameter objects live in `dcsim_rt_hil_data.mat` next to the model; the model's PreLoadFcn loads it into the base workspace, so the `.slx` opens on a fresh MATLAB / the dSPACE PC without any script. The three `.m` files of the plant must be on the path (same folder).

## 2. Ports

| # | port | dir | type | meaning | hardware |
|---|---|---|---|---|---|
| In 1 | `TRIP_feeder` | in | 0/1 | feeder node TRIP, sampled every step; seen high for `brk_delay` → feeder breaker opens (latched) | DI1 (3.3 V node logic → level shift) |
| In 2 | `TRIP_rack` | in | 0/1 | rack node TRIP | DI2 |
| In 3 | `FAULT_CMD` | in | 0/1 | fault trigger, rising edge (OR-ed with parameter `fault_trigger`) | DI3 (optional; ControlDesk can trigger instead) |
| In 4 | `RE_ARM` | in | 0/1 | re-arm, rising edge (OR-ed with `rearm_cmd`) | DI4 (optional) |
| Out 1–4 | `AO1..AO4` | out | V, 0..`ao_fs_V` | i_L, v_bus, i_rack, v_out scaled: full scale = `ao_pu_n` × base (2.64 × I_rated, 1.45 × V_ref, 16.5 × I_out_rated, 1.45 × V_ref48); saturated — the saturation is part of the design (same as the node's own clip) | AO1–AO4 → adapter panel → nodes |
| Out 5 | `SYNC` | out | 0/1 | 1 for `sync_width` from fault inception | DO1 → both nodes + scope |
| Out 6–7 | `BRK_F`, `BRK_R` | out | 0/1 | breaker state (1 closed) | ControlDesk (DO optional) |
| Out 8 | `SIG` | out | 28×1 | ControlDesk signals (below) | none |

**SIG (test points, named):** 1 `k` step count · 2 `t` [s] · 3 `P_gpu` [W] · 4 `event_active` (1 from inception of a fault **or** a benign step until re-arm) · 5 `fault_pending` · 6 `t_inception` [s] (−1 none) · 7 `clear_f_us` inception → feeder breaker open · 8 `clear_r_us` · 9/10 `trip_f_steps`, `trip_r_steps` · 11 `wl_edge` (1 on a workload rising edge) · 12 `wl_phase` · 13 `conv_on` · 14 `load_on48` · 15 `i_f` · 16 `i_f48` · 17 `v_Cin` · 18 `P_in` · 19 `i_co` · 20 `v_c` · 21 `fault_type_active` · 22 `V_arc` (the applied arc voltage, noise included — the signal to plot for the arc demo) · 23 `rearm_count` · 24 `n_faults` · **25–28 `i_L`, `v_bus`, `i_rack`, `v_out` in A / V, unclipped** (the ControlDesk plots and the check (i) capture).

Bases: I_rated = P_rated / V_ref = 165 A, I_out_rated = P_rated / V_ref48 = 2 640 A at the design point (132 kW, 800 V, 50 V).

## 3. Tunable parameters (ControlDesk)

| group | name | default | range / meaning |
|---|---|---|---|
| fault | `fault_type` | 0 | 0 none · 1 800 V branch · 2 48 V branch · 3 series arc |
| | `fault_Rf`, `fault_Lf` | 3 Ω, 2 µH | 800 V fault: 1 mΩ (bolted) … 10 Ω (high-Z); 0.5–10 µH |
| | `fault_Rf48`, `fault_Lf48` | 20 mΩ, 0.5 µH | 48 V fault: 0.5 mΩ (bolted) … 100 mΩ (high-Z); 0.1–2 µH |
| | `fault_Varc` | 25 V | series arc voltage 15–40 V (type 3) |
| | `fault_arc_m`, `fault_arc_ramp` | 0.15, 0.5 ms | arc noise modulation (0.05–0.25; pink-like 1 kHz … min(100 kHz, 0.4/dt), generated in-model — demo only, ALERT rates not quoted from the HIL) and ignition ramp (0.1–2 ms) |
| | `fault_mode` | 0 | 0 inception now · 1 on the next workload rising edge (the "hidden in a load step" demo) |
| | `fault_trigger` | 0 | ControlDesk button: 0 → 1 fires once |
| | `step_dP`, `step_ramp` | 0 W, 2 ms | benign load step applied at the trigger (0.4 × P_rated = the reference step case; type 0 + step = pure benign event) |
| workload | `wl_on` | 1 | 0 = constant `wl_P0` |
| | `wl_P0`, `wl_dP1`, `wl_T1`, `wl_duty1`, `wl_ramp1`, `wl_jit1` | 0.5 P_r, 0.3 P_r, 1 s, 0.6, 2 ms, 1 % | tier-1 iteration cadence (0.3–3 s, 0.1–0.8 P_rated, ramps 0.5–10 ms, jitter ≤ 2 %); every edge is a ramp — P_gpu never steps |
| | `wl_dP2`, `wl_T2`, `wl_duty2`, `wl_ramp2`, `wl_jit2` | 0.1 P_r, 80 ms, 0.5, 1 ms, 1 % | tier-2 bursts inside the compute phase, whole ramped pulses only (0 = off) |
| | `wl_seed` | 12345 | xorshift32 seed — same seed, same workload |
| config | `hil_dt` | 5 µs | model step = solver FixedStep. **Range 1.5–5 µs required** (below 1.5 µs the quasi-static rule is off and the stiffest 800 V high-Z branches, R_f·dt/L_f > 2.8, diverge — review #8); **10 µs usable, 20 µs not** |
| | `qs_dt_min` | 1.5 µs | quasi-static fault-branch floor — do not change |
| | `brk_delay` | **20 µs** (seconds) | SSCB opening time: TRIP seen high for round(`brk_delay`/dt) steps → breaker opens on the step after; 0 = opens on the step TRIP is first seen. 20 µs = the value of the deadline study (T_brk = T_on + 0.25 ms + 96 µs + 20 µs), so `clear_*_us` includes the breaker's own opening time |
| | `uvlo_tol` | 0.5 | 0.5 = UVLO timers count steps (HIL); 0 = reference float accumulation (the check-(i) rows set 0, as `rt_sweep`) |
| | `sync_width` | 20 µs | SYNC pulse (≥ 20 µs) |
| | `ao_fs_V` | 10 | AO full-scale volts. 10 = 16-bit ±10 V card with the panel's 0.328 divider · 3.28 = no divider · **4.5 (MAB 1511, 12-bit 0–4.5 V) only with a 0.729 divider** — the node ADC is 3.3 V; without the divider set 3.28 and only 2 985 of 4 096 codes are used (the 12-bit check (k) assumed the full code range) |
| | `rearm_cmd`, `run_enable` | 0, 1 | ControlDesk re-arm button; hold |
| | `ao_pu_1..4` | 2.64, 1.45, 16.5, 1.45 | AO full scale in p.u. (= the node front-end clip) |
| | `conv_smooth` | 1 | rack converter ramp-rate front end (MODEL.md §4.7 `smooth_on`): 1 on (GB300-class power smoothing with embedded storage — the demo regime) · 0 off. MODEL.md sweeps it 50/50, so the check-(i) rows carry the case's own value and all 8 run on one build |

Fixed (not tunable): `pv` (the other 35 physics parameters, MODEL.md) and `y0` (steady state) — set at build from the design point; a different operating point = rebuild (`dcsim_rt_hil_y0`).

## 4. Behaviour

- **Fault lifetime:** trigger → pending → inception (now, or on the next workload rising edge) → SYNC → fault held on; the breaker isolates it when TRIP arrives; everything stays until **re-arm**.
- **Re-arm** is latched on the edge and executed at the next **idle** phase of the workload (immediately when the workload is off or already idle; at most one compute phase later, `wl_duty1 · wl_T1`), so that `y0` — the steady state at `wl_P0` — matches the load: states to `y0`, breakers closed, fault and timers cleared, `rearm_count` + 1 when it executes; the workload generator keeps running (the nodes keep their learned cadence). A TRIP line still high at re-arm is ignored until it has been seen low once, so the order "re-arm the box, then re-arm the nodes" (or the reverse) both work.
- **Clearing time** = (step of breaker opening − step of inception) × dt, in `clear_f_us` / `clear_r_us`: the node's whole chain plus `brk_delay`, quantised to `dt`, and including the box's DI sampling delay; the box's AO/DI latencies are reported separately (ask the team for the figures).
- **Breaker open:** feeder — i_L forced to zero in every RK4 stage, the bus discharges into whatever is on it (fault branch, converter until its UVLO), v_bus decays — no plateau (review #2, fixed 16 Oct); rack — load and 48 V fault branch isolated, downstream node reads 0.
- **run_enable = 0** holds the states and keeps the last computed outputs on all AO/SIG — for wiring checks.

## 5. Validation we do on the box (first session)

1. **Turnaround time** of `dcsim_rt_hil` with 4 AO + 4 DI + 1 DO configured, at `hil_dt` = 5 µs; if it overruns, at 10 µs. Reading: ≤ 5 µs planned (5 µs-trained relay), 10 µs acceptable (10 µs-trained relay, physics within 0.5 %), 20 µs not acceptable.
2. **Check (i) on the target:** for each of the 8 cases apply the `check_i_*` row of `hil_param_sets.csv` (workload off, P0, fault, `uvlo_tol` 0, `conv_smooth` from the case, `brk_delay` 0), fire `fault_trigger`, capture SIG 25–28 + SYNC in ControlDesk at the task rate, export, `ctrldesk_to_simmat.m` → `compare_simscape.py`. Expected: the same table as `rt_sweep` at that step.
3. **Idle soak:** workload on, no fault, 60 s — the nodes must not report an onset outside the ramps (P_gpu is ramp-limited by construction; max |ΔP_gpu| per step ≤ dP1·dt/ramp1 + dP2·dt/ramp2, the desktop demo prints it).
4. **Closed loop:** nodes connected; a high-Z 48 V fault; read `clear_r_us` (expected ≈ 370–380 µs at a 5 µs step: onset 3–11 µs + 0.25 ms + ≤ 96 µs + 20 µs breaker; the desktop script with the scripted node gives 375).

## 6. Desktop checks before we come (Wasin)

```
%% MATLAB R2026a, repo root on the path, cd simscape   (run as a script: the Constant blocks resolve in the base workspace)
P = project_paths(); [c, shared] = load_case('high_z', P.data); dt = 5e-6;
T1 = rt_hil_check(dt, 'loop')                    % 8/8 PASS, worst values identical to rt_sweep — the wrapper changes nothing
pv = dcsim_rt_pv(shared, c);                     % design point; pv(20) is overridden by conv_smooth at run time
pv_y0 = pv; pv_y0(20) = 1;                       % y0 in the regime the box runs (conv_smooth 1)
y0 = dcsim_rt_hil_y0(pv_y0, 0.5 * shared.P_rated, dt);
build_dcsim_rt_hil('dcsim_rt_hil', dt, shared);  % writes dcsim_rt_hil.slx AND dcsim_rt_hil_data.mat (pv, y0, 38 parameters),
                                                 % sets the model's PreLoadFcn to load it — the .slx opens on its own
T2 = rt_hil_check(dt, 'slx')                     % same through the .slx (runs with sim() options, leaves the model clean)
bdclose all; clear; load_system('dcsim_rt_hil'); set_param('dcsim_rt_hil', 'SimulationCommand', 'update')   % proof: no undefined variable
export_hil_param_sets                            % hil_param_sets.csv (14 rows, 19 columns)
for s = {'benign','highz800_hard','highz48','bolted48','bolted48_l1','arc'}, dcsim_rt_hil_demo(s{1}); end
%   each prints: clearing time (380 µs feeder / 375 µs rack with the 20 µs breaker; bolted48_l1 ≈ 70–75 µs), "workload check ... PASS", and after a feeder trip "v_bus ... at +3 ms" (must be falling)
% their release: run_hil_handover.m step 4 — SAME file name in a subfolder (the data loader keys on the model name;
% if exportToVersion refuses the loaded model's name, export as _export and rename), dcsim_rt_hil_data.mat beside it,
% dcsim_rt_hil_pv_y0.mat (numbers only) + README.txt as the fallback if the parameter objects do not load on their release
```

## 7. Known limits (say them before they find them)

- Steps below 1.5 µs are outside the validated range (§3 `hil_dt`); 2 and 5 µs are the validated points, 10 µs usable.
- The series-arc noise is an online approximation of MODEL.md's offline 1/f band; the ALERT rate is quoted from the dataset, not from the box.
- The per-sample Layer 1 of the node (bolted faults in tens of µs) is specified (`firmware/SETTINGS_PROFILE_SPEC.md` §1.5) but in the current firmware it is gated behind the onset detector and cannot fire before Layer 2 (review #3, milestone S1); until S1 is done, the bolted-48 demo shows Layer 2 alone (≈ 0.37 ms) — which is the argument for Layer 1, not a failure.
- `pv` and `y0` are fixed at build; a different segment rating is a rebuild.

## 8. Review 2026-10-16 — disposition

Review: `HIL_MODEL_REVIEW_2026-10-16.md` (23 items, code reading + Python transliteration). All items reproduced from the source. Fixed in this revision: **#1** tier-1 jitter decided one edge ahead (edges never step P_gpu); **#2** open feeder breaker: di_L/dt forced to 0 in every RK4 stage (`dcsim_rt_step.m`, `rt_port_check.py`; bit-identical with breakers closed — `rt_sweep`/`rt_hil_check` must still give 8/8); **#4** tier-2 bursts phase-locked, whole pulses only; **#5** TRIP high at re-arm ignored until seen low; **#6** re-arm executes in an idle phase; **#7** `conv_smooth` tunable (38 parameters; MODEL.md has no single design regime — it sweeps `smooth_on` 50/50 — so the demo regime is stated instead); **#9** `brk_delay` exact (`>` instead of `>=`); **#10** hold mode outputs the last computed values; **#11** SIG 4 → `event_active`; **#12** `uvlo_tol`, `conv_smooth`, `brk_delay` columns in the parameter sets; **#13** arc top pole = min(100 kHz, 0.4/dt); **#14–#23** text (this file, the rulebook, the demo comment). Documented, not changed: **#8** step range (§3, §7). Firmware (Claude Code, S1): **#3** Layer 1 gated by the onset detector. Handover review (H1 model loaded once before the check loop; H2 numbers; H3 export fallback; H4 numbers-only data file) and final fixes (F1 Layer-1 claim corrected — the rack SSCB drops the GPUs with the fault either way; F2 tolerant PreLoadFcn) applied the same night. **Re-run 16 Oct 02:30 (Wasin):** `rt_hil_check` 8/8 at 5 µs loop and slx; six demos as predicted — `highz800_hard` TRIP +355 → breaker 380 µs, v_bus 0.53 p.u. at +3 ms and falling; `highz48` / `bolted48` 375 µs, `bolted48` peak ≈ 18 p.u., v_out 0.67 at opening; `bolted48_l1` 70 µs, peak ≈ 6 p.u., v_out 0.91; `benign` / `arc` no trip, P_gpu ramps end at 2.0 ms exactly. One residual found on the arc plot and fixed after the run: the three noise bands shared one white sample and summed to 1.27 rms (19 % modulation instead of 15 %); now independent bands with a fixed gain, unit rms within 3 % for 2–10 µs — affects the `arc` demo only, not the checks.

## สรุปภาษาไทย

โมเดล `dcsim_rt_hil` คือระบบจ่ายไฟ 800 VDC หนึ่งส่วน (แหล่งจ่าย → สายป้อน → บัส 800 V → คอนเวอร์เตอร์แร็ค → บัส 48 V → โหลด GPU) จำลองแบบ real-time ด้วย RK4 ขั้นเวลาคงที่ 11 สถานะ ไม่มีบล็อก Simscape ตรวจสอบแล้วว่าตรงกับโมเดลอ้างอิง Python ที่ 1 µs และผ่าน 8 กรณีทดสอบถึง 5 µs. **อินพุต 4:** TRIP จากโหนด 2 เส้น, FAULT_CMD, RE_ARM. **เอาต์พุต:** AO1–AO4 (กระแส/แรงดันที่จุด feeder และ rack สเกลเป็น 0–`ao_fs_V` V), SYNC (พัลส์ตอนเกิด fault), สถานะเบรกเกอร์ 2, และสัญญาณสำหรับ ControlDesk 28 ค่า (รวมเวลาตัดวงจรเป็น µs). **พารามิเตอร์ปรับได้ใน ControlDesk (38 ตัว):** ชนิด fault และค่า R/L, โหมดเกิด fault (ทันที / ขอบโหลดถัดไป), ปุ่มสั่ง fault, ตัวสร้างโหลด GPU (คาบ แอมพลิจูด seed — ทุกขอบเป็น ramp ไม่มีก้าวกระโดด), ขั้นเวลา (1.5–5 µs), เวลาเปิดเบรกเกอร์ 20 µs, โหมด smoothing ของคอนเวอร์เตอร์, สเกล AO. **ข้อกำหนดหลัก:** ขั้นเวลา ≤ 5 µs (10 µs ใช้ได้, 20 µs ไม่ได้), AO 4 ช่อง, DI 2–4, DO 1; การ์ด 12-bit 0–4.5 V ใช้ได้เมื่อมีตัวแบ่งแรงดัน 0.729. **การทดสอบครั้งแรกกับบริษัท:** วัด turnaround time พร้อม I/O, รัน 8 กรณีอ้างอิงบนกล่องแล้วเทียบด้วยสคริปต์ของเรา, idle soak 60 s, แล้วทดสอบวงปิดกับโหนดจริง (คาดเวลาตัด ≈ 370 µs). **แก้ไข 16 ต.ค.:** ตามรีวิว 23 ข้อ — ขอบโหลดไม่กระโดด, เบรกเกอร์ feeder เปิดแล้วบัสคายประจุจริง (เดิมค้างที่ 0.6–0.8 p.u.), re-arm รอช่วง idle, ฯลฯ ต้องรัน `rt_hil_check` ใหม่ให้ได้ 8/8 ก่อนส่งมอบ.
