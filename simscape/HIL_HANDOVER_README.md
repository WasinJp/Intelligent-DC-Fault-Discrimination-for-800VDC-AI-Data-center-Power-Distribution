# dcsim_rt_hil — handover to the dSPACE team

**Project:** IDCFC — intelligent DC fault discrimination for 800 VDC AI data-centre power distribution (Delta Cup 2026). **Contact:** Wasin (Prof. Supachai's group). **Model build:** 16 Oct 2026, MATLAB R2026a, validated (see §5). **Full interface tables:** `HIL_MODEL_INTERFACE.md` (same folder).

## 0. In 30 seconds

One Simulink model, `dcsim_rt_hil.slx`, that runs one 132 kW segment of an 800 VDC data-centre feeder in real time: source → feeder → 800 V bus → rack DC-DC converter → 48 V storage → GPU load, with fault branches and two breakers. It outputs **4 analog signals** (two currents, two voltages), takes **2 TRIP lines** back from our two STM32 relay nodes, opens its model breaker and logs **inception → breaker-open time** on its own clock.

- One MATLAB Function block, 11 states, explicit RK4, fixed step, doubles. No Simscape blocks, no continuous states, no algebraic loops, no `rand`, no From Workspace.
- **Step: 1.5–5 µs required** (5 µs is our baseline; 10 µs usable with caveats; 20 µs not acceptable).
- I/O: **4 AO, 2–4 DI, 1 DO.**
- **The first thing we'd like to know:** the turnaround time on your box with the I/O configured.

## 1. What is in this folder

| file | what |
|---|---|
| `dcsim_rt_hil.slx` | the model (exported to your release if you asked for one) |
| `dcsim_rt_hil_data.mat` | `pv` (36 physics parameters), `y0` (initial state), the 38 tunable `Simulink.Parameter` objects. **Must sit next to the `.slx`** — the model's PreLoadFcn loads it |
| `dcsim_rt_hil_pv_y0.mat` | numbers-only copy of `pv`, `y0` (fallback, §7) |
| `dcsim_rt_hil_plant.m`, `dcsim_rt_step.m`, `dcsim_rt_derivs.m` | the code the MATLAB Function block calls — **must be on the path** (same folder) |
| `dcsim_rt_hil_params.m` | recreates the 38 parameters at their defaults |
| `hil_param_sets.csv`, `apply_hil_param_set.m`, `read_hil_param_sets.m` | the parameter sets for validation (`check_i_*`) and the demo (`demo_*`); `apply_hil_param_set('demo_3_highz48')` applies one |
| `hil_quickstart.m` | everyday commands on a desktop MATLAB (§3) |
| `HIL_MODEL_INTERFACE.md` | full port / parameter / signal tables |

## 2. Requirements

- MATLAB + Simulink (the release we exported to). No toolbox is used by the model itself; code generation goes through your usual dSPACE toolchain (RTI / ConfigurationDesk).
- Keep **all files in one folder** and make it the current folder (or add it to the path).

## 3. On a desktop first (5 minutes)

```matlab
cd('<this folder>')
hil_quickstart('open')                          % loads + updates the model; prints solver, step, ports
hil_quickstart('scaling')                       % AO volts <-> amps / volts, and what each AO reads at idle
hil_quickstart('sets')                          % the parameter sets we brought
R = hil_quickstart('sim', 'demo_2_highz800_hard');   % desktop run: fault at 20 ms, scripted TRIP, plots AO1-4
R = hil_quickstart('sim', 'demo_3_highz48');
R = hil_quickstart('sim', 'demo_1_benign_step');     % no trip expected
hil_quickstart('params')                        % the 38 tunables with current values and descriptions
hil_quickstart('defaults')                      % everything back to the defaults in the data file
```
Expected from `sim`: `demo_2_highz800_hard` clears the feeder at ≈ 370 µs (scripted trip 350 µs + 20 µs breaker), `demo_3_highz48` the rack at ≈ 370 µs, `demo_1_benign_step` −1 / −1 (no breaker opened). `sim` fires the fault at a fixed time on a flat load and does not change the model.

## 4. Preparing the model for the box

**Ports → I/O**

| model port | type | connect to | notes |
|---|---|---|---|
| In 1 `TRIP_feeder` | 0/1 | DI1 | from our feeder node (3.3 V logic; we level-shift if needed). Held high ≥ `brk_delay` → feeder breaker opens, latched |
| In 2 `TRIP_rack` | 0/1 | DI2 | from our rack node |
| In 3 `FAULT_CMD` | 0/1 | DI3, optional | rising edge fires the fault; the ControlDesk parameter `fault_trigger` does the same |
| In 4 `RE_ARM` | 0/1 | DI4, optional | rising edge re-arms; `rearm_cmd` does the same |
| Out 1–4 `AO1..AO4` | V, 0…`ao_fs_V` | AO1–AO4 | i_L, v_bus, i_rack, v_out; saturated at full scale **by design** |
| Out 5 `SYNC` | 0/1 | DO1 | 20 µs pulse at fault inception → both nodes + our scope |
| Out 6–7 `BRK_F`, `BRK_R` | 0/1 | ControlDesk (DO optional) | breaker state, 1 = closed |
| Out 8 `SIG` | 28 × 1 | none | ControlDesk signals (below) |

**Solver:** FixedStepDiscrete, step = `hil_dt` (the parameter and the solver step are the same variable — keep them equal). Default 5 µs.

**AO range:** `ao_fs_V` = 10 for a 0–10 V or ±10 V card (we add a 0.328 divider on our side) · 3.28 for an output that goes straight to the node · for a 0–4.5 V 12-bit card, 4.5 **only with** a 0.729 divider on our side.

**ControlDesk layout we suggest**
- *Controls:* `fault_type`, `fault_Rf`, `fault_Rf48`, `fault_mode`, `step_dP`, buttons `fault_trigger` and `rearm_cmd`, `run_enable`.
- *Plots:* SIG 25–28 (`i_L`, `v_bus`, `i_rack`, `v_out` in A / V, unclipped), `BRK_F`, `BRK_R`, `SYNC`, SIG 22 `V_arc` for the arc demo.
- *Numbers:* SIG 7 `clear_f_us`, SIG 8 `clear_r_us` (inception → breaker open, µs; −1 = not opened), SIG 23 `rearm_count`, SIG 24 `n_faults`.

## 5. First joint session — what we'd like to run, in order

| # | test | how | pass |
|---|---|---|---|
| 1 | **Turnaround time** | build with 4 AO + 4 DI + 1 DO configured, `hil_dt` = 5 µs; if it overruns, 10 µs | ≤ 5 µs: as planned · 10 µs: acceptable · 20 µs: not |
| 2 | **Validation on the target** | for each `check_i_*` row of `hil_param_sets.csv`: apply the row, press `fault_trigger`, capture SIG 25–28 + SYNC at the task rate, export (.mat). We convert and score on our laptop (`ctrldesk_to_simmat.m` → `compare_simscape.py`) | the same 8/8 table as our desktop at that step |
| 3 | **AO check** | `run_enable` = 1, no fault, read AO1–AO4 with a meter / scope | ≈ the idle readings of `hil_quickstart('scaling')` (AO1 ≈ 1.95 V, AO2 ≈ 6.9 V, AO3 ≈ 0.3 V, AO4 ≈ 6.9 V at `ao_fs_V` 10) |
| 4 | **Idle soak** | workload on, no fault, 60 s, nodes connected | no TRIP, no onset outside the workload ramps |
| 5 | **Closed loop** | nodes connected, `demo_3_highz48` | `clear_r_us` ≈ 370–380 µs |

Desktop validation (our laptop, 16 Oct): 8/8 reference cases pass at 5 µs through the `.slx`, identical to the validated fixed-step core; the core is bit-identical to our Python reference at 1 µs and checked against an independent Simscape model (8/8 within 1 %).

## 6. The demo sequence (≈ 2 min) — rows `demo_*` of `hil_param_sets.csv`

Before the demo: workload on, nodes running ≥ 8 s (they learn the workload rhythm). Each fault waits for the next workload edge (`fault_mode` 1). After each event: `rearm_cmd` (it executes in the next idle phase of the workload, ≤ ~0.6 s).

| # | set | expected |
|---|---|---|
| 1 | `demo_1_benign_step` | load step, **no trip** |
| 2 | `demo_2_highz800_hard` | 8 Ω fault on the 800 V bus inside a load step → **feeder** trips, `clear_f_us` ≈ 380; v_bus then decays |
| 3 | `demo_3_highz48` | 20 mΩ fault on the 48 V bus → **rack** trips, `clear_r_us` ≈ 375; the feeder sees only a smooth rise |
| 4 | `demo_4_bolted48` | bolted 48 V fault; AO3 saturates; with the 0.25 ms relay alone `clear_r_us` ≈ 375 (the case for a per-sample threshold) |
| 5 | `demo_5_arc` (optional) | series arc → ALERT, no trip; watch SIG 22 `V_arc` |

## 7. If something goes wrong

| symptom | cause | do |
|---|---|---|
| "undefined variable pv / y0 / …" on open or build | data file not next to the `.slx`, or folder not on the path | put all files in one folder, `cd` there, reopen |
| warning "data file not loaded" on open (older release) | the `Simulink.Parameter` objects did not load | `load dcsim_rt_hil_pv_y0.mat`, then `dcsim_rt_hil_params(struct('P_rated', 132e3), 5e-6)`, then update / build |
| outputs go to NaN after a fault | step below 1.5 µs with a high-resistance 800 V fault | use 2–5 µs (below 1.5 µs is outside the validated range) |
| task overrun at 5 µs | CPU time per step | try 10 µs and tell us the turnaround — we have a relay model for 10 µs |
| re-arm "does nothing" for a moment | re-arm waits for the next idle phase of the workload | wait ≤ ~0.6 s; `rearm_count` increments when it runs |
| breaker stays closed although a node trips | TRIP was already high at re-arm (ignored until it goes low once), or DI threshold / level | check the DI level; the node clears TRIP on its own re-arm |
| AO3 flat at full scale | rack current above 16.5 × rated (bolted fault) | by design — the same clip as our node's input |
| feeder also trips after a rack trip | the converter recharges the 48 V storage after the rack breaker opens (≈ 1.4 p.u. on the feeder for ms) | not a model fault — log it; it is a selectivity question for our relay |

## 8. What we need to know from you

Box model and I/O variant; turnaround time with I/O; AO range / resolution / noise floor / update latency / load; DI levels, threshold, state when undriven, sampling; DO level and minimum pulse; ControlDesk capture rate and export format; your MATLAB release and whether we work on your PC; session dates, operator, and whether the box (or a live link) can be at the final on 14 Nov. We would like to credit you as equipment sponsor — please tell us how.

---

## สรุปภาษาไทย

**โมเดล:** `dcsim_rt_hil.slx` จำลองระบบจ่ายไฟ 800 VDC หนึ่งส่วน (132 kW) แบบ real-time — MATLAB Function block เดียว, 11 สถานะ, RK4 ขั้นเวลาคงที่, ไม่มี Simscape. **ขั้นเวลา 1.5–5 µs** (10 µs ใช้ได้, 20 µs ไม่ได้). **I/O:** AO 4 ช่อง (กระแส/แรงดัน 2 จุด), DI 2–4 (TRIP จากโหนด, สั่ง fault, re-arm), DO 1 (SYNC). **ไฟล์ทั้งหมดต้องอยู่โฟลเดอร์เดียวกัน** — โมเดลโหลด `dcsim_rt_hil_data.mat` เองตอนเปิด. **ลองบนคอมก่อน:** `hil_quickstart('open')`, `('scaling')`, `('sim','demo_2_highz800_hard')`. **ทดสอบครั้งแรกบนกล่อง:** (1) วัด turnaround time พร้อม I/O, (2) รัน 8 กรณีอ้างอิง (`check_i_*`) จับสัญญาณ SIG 25–28 + SYNC ส่งให้เราเทียบ, (3) วัดค่า AO ตอน idle, (4) idle soak 60 s, (5) วงปิดกับโหนดจริง (คาดเวลาตัด ≈ 370–380 µs). **ถ้ามีปัญหา:** ดูตาราง §7. **สิ่งที่อยากทราบ:** รุ่นกล่องและ I/O, turnaround time, สเปก AO/DI/DO, การจับสัญญาณใน ControlDesk, เวอร์ชัน MATLAB, วันและการขนย้ายไปงาน 14 พ.ย., และการให้เครดิตผู้สนับสนุน.
