# MILESTONES.md — firmware progress (filled by the implementer; numbers, not adjectives)

| M | date done | acceptance result (paste the compare / timing output) | notes / deviations (link DEVIATIONS.md) |
|---|---|---|---|
| M1 | 2026-10-01 | `ctest` 13/13 pass (2026-10-02). `m1_feature_agreement` on 1 080 events × 2 nodes × 3 windows = 6 480 rows: onset index identical 6 480/6 480; every CONV/PHYS feature within 1.5e-10 relative (worst: `v_sag_end`, `r_dyn` 1.479e-10; `di_end` 9.5e-11; `spec_i` 7.9e-12; eight features bit-identical). Full table in §M1 below. | Deviations #2–#7. IIR filters run in double (float32 missed the `spec_i` tolerance by 4×, §M1.3). Fixtures: 43 MB records + 4.8 MB CSV, under the 50 MB cap. |
| M2 | 2026-10-01 (retrained on v1xl6k 2026-10-01 17:09) | `m2_model_agreement` on the whole fixture table, 9 720 score rows (feeder / rack / feeder+rack 3 240 each): raw class scores and `predict_proba` **bit-identical** to sklearn (worst abs 0.000e+00 on all six columns of all three models), argmax identical 9 720/9 720. Models: `data/nodes_v1xl6k` at W = 0.25 ms, `studies._fit` → feeder 72 iterations / 216 trees / 6 264 nodes / 76 036 B, rack 82 / 246 / 7 134 / 86 596 B, both 102 / 306 / 8 874 / 107 716 B. Host inference mean 4.2 / 5.3 / 7.5 µs (idle machine), §M2.3. | Deviations #6, #8, **#9: sklearn early stopping is ON above 10 000 rows, so `_fit` stops at 72–102 iterations on the v1xl6k tables.** Training-set SHA-256 in §M2.1. The v1large044 models (300 iterations each, 316 860 B) are kept in `host/models/v1large044/`. Budget study: `docs/TIMING.md`. |
| M3 | **built, untested** 2026-10-01 | `firmware/node` builds with arm-none-eabi-gcc 14.2 (`-O2 -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -ffp-contract=off -Wall -Wextra -Werror`): flash 339 168 B (16 %), DTCM 53 240 B (41 %), AXI SRAM 313 056 B (60 %). Host preview of the §4.2 acceptance on the replayed fixtures (`m3_stream_vs_record`): onset within ±2 samples **99.65 %** (1 972 / 1 979 detected by both modes), identical decisions **100.00 %** (2 160 / 2 160); with a random 0–4.75 ms quiet prefix (seeds 1–3): 99.65 / 99.85 / 99.80 % and 99.91 / 99.77 / 99.72 %. Detector cost on the host 17.5 ns per sample. DWT numbers: none yet. | Deviation **#1 rewritten**: the literal §4.2 sliding detector reaches only 78.4 % / 95.9 % (§M3.2); the shipped detector freezes the baseline at 0.05 × threshold and starts the record at the frozen baseline. Deviation #11 (decision in PendSV). Procedure for the boards: `docs/M3_TEST_PROCEDURE.md`; parity tool `tools/node_parity.py`; DAC tables `tools/replay_waveforms.py`. |
| M4 | | | `tools/replay_waveforms.py` (12-bit tables at 1 MSa/s + manifest with the Python onset and decision) and the bench_control `replay load/start` path exist (M7 row); the scope measurement needs the boards. |
| M5 | host side 2026-10-01; **target learner built, untested** 2026-10-02 | Double learner, `m5_work_agreement` (810 rows = 135 events × 2 nodes × 3 windows): `has_period` identical, `period_strength` ≤ 4.6e-13, `phase_err` ≤ 2.8e-14, relearn 5.8 ms mean on the host. **Target learner** (`fx_cadence32`, float32 history, block FFT autocorrelation, exact peak refinement): `m5_f32_agreement` (generic 8 192-pt FFT) and `m5_cmsis_agreement` (CMSIS-DSP 4 096-pt, the backend compiled into the node) both PASS with the same numbers as the double learner (has_period exact, period_strength ≤ 2.6e-13, phase_err ≤ 2.8e-14). Host cost, CMSIS backend: 7.2 ms mean / 62 ms max, **23.0 M x86 cycles mean / 196 M max**, 63.5 FFTs per relearn; generic: 10.7 ms / 71 ms, 34.2 M / 228 M cycles. §M5.2. | Deviations #10, #12, **#14: the projected M7 cost (70–150 ms mean) exceeds the 40 ms budget of one relearn per 200 ms; measure, then set the period to 1 s if confirmed.** On the node: `cadence_task.c` (100:1 decimation of the fast stream into the 152 kB history in AXI SRAM, relearn in the main loop, double-buffered publication, `phase_err` from the published tiers in the decision path). |
| M6 | **built, untested** 2026-10-02 | `common/fx_can.c` (16-byte summary + 3 × 64-byte float64 feature frames, combined decision) and `common/fx_upload.c` (framed FXR1 record + trailer, CRC-32) pass their round-trip unit tests (`unit_common`: encode/decode, any part order, routing on onset tolerance, CRC detects corruption). Node: FDCAN1 at 1 / 5 Mbit/s (`can_link.c`), summary + features sent after every decision, feeder waits `can_wait_us` for the rack set and logs `used_two_node`; USB CDC on OTG_FS (`usb_upload.c`, ST USB device library) uploads the record at k_on + 2 500 and on `capture`. Host decoder `tools/record_decoder.py` writes FXR1 records + `node_trailers.csv` for `compare.py`. | Deviations #13 (features cannot fit the 16-byte frame; 3 FD frames ≈ 150–250 µs > the 50 µs window), #15 (upload record starts at the baseline start). Procedure: `docs/M6_M7_TEST_PROCEDURE.md` §B–C. |
| M7 | **built, untested** 2026-10-02 | `firmware/bench_control` builds with the node toolchain: flash 55 772 B, DTCM 44 184 B, D2 45 760 B. Profile generator (two-tier cadence with jitter, staircase steps over the five gates, bursts, idle drops, xorshift seed), fault selectors + one-shot triggers (scheduled on the next cadence edge, `at`, or `now`; refused when the arm key is off), UVLO (ADC 1 MSa/s, 9.6 V / 100 µs off, 10.1 V on), SYNC, DAC replay (dual DAC 1 MSa/s from a RAM table loaded over the console), console. `tools/bench_run.py` scripts the SCALING_SHEET §6 plan (200 benign, 60 rack + 20 feeder faults), checks the arm key before every fault (dry run passes). | Deviation #16. Procedure: `docs/M6_M7_TEST_PROCEDURE.md` §D. Pins in `bench_control/board_bc.h` are candidates. |

## Build used

Host: gcc 16.2.0 (WinLibs MinGW-w64 x86_64-ucrt), CMake 4.4.3, Ninja 1.13, `-O2 -Wall -Wextra -Werror -ffp-contract=off`, C11 (`C_EXTENSIONS OFF` for `common/`). Target: Arm GNU Toolchain 14.2.Rel1, flags above, CMSIS/HAL from `tools/fetch_stm32.sh` (cmsis_core afc5ca6, cmsis_device_h7 81db1ec, stm32h7xx_hal_driver 7e541d9). Python: repo `.venv`, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.0, h5py 3.16.0, pandas 3.0.5. Commands: `firmware/host/README.md`, `firmware/node/CMakeLists.txt`.

```
Test project .../firmware/host/build
    Start 1: unit_common ................   Passed
    Start 2: m1_extract .................   Passed
    Start 3: m1_feature_agreement .......   Passed
    Start 4: m2_score ...................   Passed
    Start 5: m2_model_agreement .........   Passed
    Start 6: m2_bench ...................   Passed
    Start 7: m3_stream_vs_record ........   Passed
    Start 8: m3_stream_vs_record_prefix .   Passed
    Start 9: m5_work_agreement ..........   Passed
    Start 10: m5_f32_extract ............   Passed
    Start 11: m5_f32_agreement ..........   Passed
    Start 12: m5_cmsis_extract ..........   Passed
    Start 13: m5_cmsis_agreement ........   Passed
100% tests passed, 0 tests failed out of 13
```

## M1 — feature extractor (record mode), host CLI, fixtures

### M1.1 Fixtures (`tools/make_fixtures.py`, §6.1)

Dataset `data/events_v1large044_s*.h5` (v1-large, MODEL.md 0.4.4, git 2087f83), seed 0, 120 events per label × 9 labels = 1 080 events, both nodes → 2 160 record files `<event>_<node>.bin` (format FXR1, `fx_record.h`), 40.9 MB. 500 kSa/s streams from the stored 2 MSa/s streams by `synth._aa_decimate(x, 2e6, 4)`: 2 600 samples per channel (100 before + 2 500 after the anchor). Records hold uint16 codes at a per-node base calibration (±8 × I_rated, ±4 × V_ref, offset 32 768); 20 of the 2 160 records needed a 2× or 4× coarser current gain to avoid clipping (header carries the gain). Slow streams (float32, up to the fast-window end) are stored for 15 events per label (135 events) for M5. `onset_found` is 1 in 91.6 % of rows (the rest are the undetected events the Python pipeline also carries). Reference: `reference_features.csv`, 6 480 rows = `features.extract` at W = 0.25 / 0.5 / 1.0 ms on the reconstructed float32 values, plus `detect_onset`.

Requantisation diagnostic (features of the 16-bit record vs the unquantised decimated stream, max over rows; not an acceptance criterion): di_end 1.4e-2, di_max 1.2e-2, didt_max 3.7e-4, t_rise 0.50 ms, dv_early 3.5e-2, di_early 7.2e-3, r_dyn 1.56, v_sag_end 6.4e-3, v_min 5.3e-3, spec_i 0.105, spec_v 0.231. The large values are a handful of records whose onset index moves by one sample at the requantised noise floor; this is the same discreteness a real ADC produces and is why the acceptance compares against the reference computed on the record itself.

### M1.2 Feature agreement (`compare.py features`, §6.2)

```
features: 6480 matched rows (1080 events)
  onset index identical: 6480/6480
  di_end      n= 6480  worst abs 3.553e-15  worst rel 9.473e-11 (05173/rack/W=1)   PASS
  di_max      n= 6480  worst abs 0.000e+00  worst rel 0.000e+00                    PASS
  didt_max    n= 6480  worst abs 0.000e+00  worst rel 0.000e+00                    PASS
  t_rise      n= 6480  worst abs 0.000e+00  worst rel 0.000e+00                    PASS
  dv_early    n= 6480  worst abs 0.000e+00  worst rel 0.000e+00                    PASS
  di_early    n= 6480  worst abs 0.000e+00  worst rel 0.000e+00                    PASS
  v_sag_end   n= 6480  worst abs 7.379e-16  worst rel 1.479e-10 (05508/rack/W=1)   PASS
  v_min       n= 6480  worst abs 0.000e+00  worst rel 0.000e+00                    PASS
  r_dyn       n= 6480  worst abs 5.784e-12  worst rel 1.479e-10 (05508/rack/W=1)   PASS
  collapse    n= 6480  worst abs 0.000e+00  worst rel 0.000e+00                    PASS
  spec_i      n= 6480  worst abs 5.551e-16  worst rel 7.946e-12 (02929/feeder/W=0.25)  PASS
  spec_v      n= 6480  worst abs 6.661e-16  worst rel 2.832e-11 (05618/rack/W=0.5)    PASS
RESULT: PASS
```

Criteria: onset index identical; the ten features within 1e-6 relative or 1e-9 absolute; `spec_i`, `spec_v` within 1e-4 absolute. The residual 1e-10 is the summation order of `mean`/`std` (numpy pairwise vs sequential); `_movavg` is reproduced bit-for-bit (unit test, max error 0).

Host cost: `fx_cli extract` 2 160 records × 3 windows, extract + inference per row mean 100.7 µs, max 457 µs on x86 (includes the two 2 600-sample band-pass runs from record start; on the node the record is ≤ 2 600 samples and the band-pass runs only over it).

### M1.3 IIR precision (why double, DEVIATIONS #2)

Same fixtures, `-DFX_IIR_FLOAT=ON` (float32 state and coefficients, everything else identical):

```
  spec_i  worst abs 4.038e-04 (06090/feeder/W=1)  worst rel 2.796e-01  FAIL x126
  spec_v  worst abs 1.929e-04 (00588/rack/W=1)    worst rel 8.811e-02  FAIL x14
```

Unit test on the synthetic vector: float32 band-pass max error 6.2e-5 of full scale, log10 std-ratio error 3.7e-6; double: 0 (bit-identical to `scipy.signal.sosfilt`). 140 of 6 480 rows exceed the 1e-4 tolerance in float32, so the IIR type is double (`fx_iir_t`), which the M7's fpv5-d16 FPU supports in hardware. The M3 DWT numbers will say what it costs per DMA block.

### M1.4 Unit tests (`unit_common`)

Constants of `fx_config.h` re-derived from the Python expressions at run time (N_PRE 75, N_SM5 2, N_SM10 5, N_50US 25, N_SKIP 30, N_W 125/250/500, n_tail 12/25/50, k_half 37/75/150); `_movavg` max error 0; mean 0, std 3.3e-16; band-pass 0; 100:1 anti-alias decimator 0 (vs `synth._aa_decimate`); tree walk incl. NaN routing and `x == threshold → left`; record header round trip; synthetic-step feature smoke test; cadence `phase_err` fold.

## M2 — model export and inference

### M2.1 Training (`tools/train_model.py`, committed models)

`data/nodes_v1xl6k/features_{feeder,rack}.csv`, rows with `W_ms == 0.25` and `onset_found > 0.5`, `studies._fit` (HistGradientBoostingClassifier max_iter 300, learning_rate 0.06, max_leaf_nodes 15, l2 0.5, random_state 0, sklearn `early_stopping='auto'` → active on these 36 000-row tables, DEVIATIONS #9). Provenance: `host/models/models.json`.

| model | rows (ALERT / HOLD / TRIP) | iterations reached | trees | nodes | bytes (12-byte nodes + tree table) | train accuracy |
|---|---|---|---|---|---|---|
| feeder | 35 946 (969 / 29 979 / 4 998) | 72 | 216 | 6 264 | 76 036 | 0.9557 |
| rack | 34 660 (332 / 29 998 / 4 330) | 82 | 246 | 7 134 | 86 596 | 0.9848 |
| both (30 features) | 35 971 (971 / 30 000 / 5 000) | 102 | 306 | 8 874 | 107 716 | 0.9988 |

Training-set hashes (SHA-256): `features_feeder.csv` c902e4c5742823487d649c48d9815f3c171bff72a8c6e3a6f2a0797858c74726, `features_rack.csv` 8c362ef3fcaa80ced3fc63a430ccd7bc6e78bc5cf36aea9d8579cf3c595c2be0. Per node image: feeder + both = 184 kB, rack = 87 kB of flash. Training time 0.7–1.2 s per model.

Alternative (kept, `host/models/v1large044/`): trained on `data/nodes_v1large044` (6 187 / 5 926 / 6 192 rows, all 300 iterations because early stopping is off below 10 000 rows): 26 100 / 26 100 / 26 098 nodes, 316 860 B each; also bit-identical scores on the fixtures (its `reference_scores.csv` is stored next to it).

Budget variants (`host/models/v1xl6k_it{100,150,300}/`, `--early-stopping off`): 100 / 150 / 300 iterations = 300 / 450 / 900 trees, 8 700 / 13 050 / 26 100 nodes, 105 660 / 158 460 / 316 860 B per model; their accuracy and inference cost are the decision table of `docs/TIMING.md`.

### M2.2 Score agreement (`compare.py scores`, §6.3), committed models

```
scores: 9720 matched rows; models: ['both', 'feeder', 'rack']
 model both:   3240 rows  raw_ALERT/raw_HOLD/raw_TRIP/p_ALERT/p_HOLD/p_TRIP worst abs 0.000e+00  PASS; argmax identical 3240/3240
 model feeder: 3240 rows  raw_ALERT/raw_HOLD/raw_TRIP/p_ALERT/p_HOLD/p_TRIP worst abs 0.000e+00  PASS; argmax identical 3240/3240
 model rack:   3240 rows  raw_ALERT/raw_HOLD/raw_TRIP/p_ALERT/p_HOLD/p_TRIP worst abs 0.000e+00  PASS; argmax identical 3240/3240
RESULT: PASS
```

Criteria: 1e-5 absolute on `decision_function` and `predict_proba`, identical argmax. The result is bit-identical (the C code adds the leaves in sklearn's order and applies the same softmax). The `both` rows pair each feeder row with the rack row of the same event and window, as `studies.two_node_table` does. The same test passed on the v1large044 models before the retrain.

### M2.3 Host inference time (`fx_cli bench`, 3 240 rows × 50 repeats, x86 mobile CPU, `timespec_get` timer, idle machine)

```
model feeder trees 216 nodes 6264 bytes 76092  features 15 | mean 4.19 us  p50 4.35 us  p99 8.45 us
model rack   trees 246 nodes 7134 bytes 86652  features 15 | mean 5.28 us  p50 5.38 us  p99 9.73 us
model both   trees 306 nodes 8874 bytes 107772 features 30 | mean 7.54 us  p50 7.42 us  p99 13.06 us
```

For the fixed-iteration variants (idle machine, `docs/TIMING.md` §1): 100 iterations 5.9 / 6.5 / 7.0 µs mean, 150 iterations 9.1 / 10.5 / 11.9 µs, 300 iterations (900 trees) 19.3 / 23.2 / 27.1 µs mean and 29 / 33 / 40 µs p99 (feeder / rack / both). The M7 numbers come from the `timing` command of the node (M3 procedure §3–4).

## M3 — node image (built, untested)

### M3.1 What is in `firmware/node`

`clock.c` 480 MHz (VOS0, PLL1 from the 8 MHz HSE bypass; PLL2 50 MHz for the ADC); `adc_dma.c` TIM3 TRGO at 500 kHz → ADC1+ADC2 dual regular simultaneous, 16-bit, 8.5-cycle sampling at 25 MHz, DMA1 stream 0 circular into 2 × 8 words in AXI SRAM, half/complete callbacks every 8 samples (16 µs), D-cache invalidate per block; `stream.c` ring buffer 2 × 8 192 uint16, calibration (`(float)(code − offset) · gain`, the fx_record conversion), Layer 1 against the running baseline, `fx_onset_stream_push` per sample, ONSET pin at the fire, PendSV at the window close, `fx_features_extract` on `[baseline start, k_on + 125)`, `fx_relay_layer2`, TRIP/ALERT pins, DWT stamps (extract, infer, close→trip, onset→trip); `timing.c` DWT and per-stage statistics (mean / p99 / max over the last 1 024); `settings.c` flash sector 7 of bank 2 with CRC-32 (role, ratings, full scales, gain/offset, theta, Layer-1 thresholds, model id, CAN id); `cli.c` USART3 (ST-Link VCP) at 921 600 with DMA receive: `status`, `timing`, `arm`, `selftest`, `settings show|set|save|defaults`, `replay <event> <nbytes>` (an FXR1 record pushed by `tools/node_parity.py`, answered with the `fx_cli extract` CSV line per window plus DWT cycles), `reset`; `trip.c` pins and LEDs; `board.h` the pin map (candidate pins on CN9/CN10, to be confirmed). Linker script: stack/.data/.bss in DTCM, `.ram_d1` for DMA, ring, record and work buffers.

### M3.2 §4.2 host preview (`fx_cli stream`, 2 160 fixture records, W = 0.25 ms)

| detector | both detected | onset within ±2 samples | record only | identical decisions |
|---|---|---|---|---|
| literal §4.2 (sliding pre-window, freeze 0) | 1 441 | 1 129 = 78.35 % | 538 | 2 071 / 2 160 = 95.88 % |
| freeze 0.5, record from k_on − 100 | 1 947 | 1 508 = 77.45 % | 32 | 97.22 % |
| freeze 0.1, record from k_on − 100 | 1 979 | 1 907 = 96.36 % | 0 | 97.22 % |
| freeze 0.5, record from the frozen baseline | 1 947 | 1 513 = 77.71 % | 32 | 98.33 % |
| freeze 0.2, record from the frozen baseline | 1 978 | 1 839 = 92.97 % | 1 | 99.72 % |
| freeze 0.1, record from the frozen baseline | 1 979 | 1 952 = 98.64 % | 0 | 99.95 % |
| **freeze 0.05, record from the frozen baseline (shipped)** | 1 979 | **1 972 = 99.65 %** | 0 | **2 160 / 2 160 = 100.00 %** |
| shipped, random quiet prefix 0–2 375 samples, seeds 1 / 2 / 3 | 1 975 / 1 971 / 1 972 | 99.65 / 99.85 / 99.80 % | 4 / 8 / 7 | 99.91 / 99.77 / 99.72 % |

The 181 "neither" records are events no detector finds within the record (undetected in Python too). In the literal §4.2 detector half of the benign records (slow 0.5–20 ms ramps) and 21 series-arc / 13 high-Z records never fire; the sliding baseline follows the drift. The shipped detector meets the §4.2 numbers on the host; the target repeats the measurement with replayed waveforms (M3 procedure §4).

### M3.3 Still to measure on the board (M3 procedure)

Interrupt load per 8-sample block (budget < 2 300 cycles), `extract` and `infer` cycles via `replay` on ≥ 200 fixtures (§6.4 parity, expected bit-identical to the host except libm rounding), `close→trip` p99 ≤ 38 400 cycles (80 µs), `onset→trip`, flash settings persistence. Known gaps: CAN, two-node decision, USB record upload, cadence on the target, bench_control image.

## M5 — cadence learner (host side)

`common/fx_cadence.c`: `_cadence_candidates` (FFT autocorrelation, `find_peaks` with height and prominence, harmonic rejection with Python `round`), `_edges_two_level` (numpy `percentile` linear method, median/MAD noise, hysteresis walk-back), `_tier2_from_segments`, `_learn_cadence` (envelope search, tier-1 fallback over candidates, tier-2 edges per compute phase, `phase_start` / `off2`), the `phase_err` fold. `fx_cli extract` runs it on every record that carries a slow stream (`t_end = t_on − 0.5 ms`, `W` per window).

```
  WORK features on the 810 rows whose record holds the slow stream:
  has_period       n=  810  worst abs 0.000e+00  worst rel 0.000e+00                       PASS
  period_strength  n=  810  worst abs 4.566e-13 (05816/feeder/W=0.25)  worst rel 7.634e-13 PASS
  phase_err        n=  810  worst abs 2.842e-14 (05404/rack/W=0.25)  worst rel 1.090e-12   PASS
```

Criteria: has_period 1e-6, period_strength 1e-4, phase_err 1e-6, NaN matching NaN. CPU time per relearn on the host (x86, double, FFT length up to 131 072): mean 5.77 ms, max 37.6 ms over 810 runs (the max is the longest histories, 7.6 s × 5 kSa/s). Target budget: < 20 % of a core at one relearn per 200 ms → 40 ms per relearn in float32 with CMSIS-DSP, to be measured.

### M5.2 Target learner on the host (`fx_cli extract --cadence f32`, `fx_cli_cmsis`)

`common/fx_cadence32.c` + `fx_fft32_{generic,cmsis}.c`, bound to the same buffer sizes as the node (`cadence_task.c`): history 38 000 float32, shadow 38 000 float32, ac/acc 17 100 float32, cnt 17 100 bytes, state 4 750 bytes, FFT work 3 × N floats, edges 3 × 1 024 doubles.

| backend | FFT N | FFTs / relearn | host wall mean / max | x86 cycles mean / max | agreement (810 rows) |
|---|---|---|---|---|---|
| generic radix-2 (host) | 8 192 | 24.8 | 10.7 ms / 71 ms | 34.2 M / 228 M | has_period exact; period_strength 2.6e-13; phase_err 2.8e-14 — PASS |
| CMSIS-DSP `arm_rfft_fast_f32` (node) | 4 096 | 63.5 | 7.2 ms / 62 ms | 23.0 M / 196 M | identical numbers — PASS |

Two fixes were needed to reach the double learner's precision: exact tie resolution in the float32-shadow order statistics (quantised slow streams: one event's edges shifted), and exact double re-evaluation of each autocorrelation peak over ±4 lags (three events had a tier period one 0.2 ms bin off). The max rows are the longest histories (7.6 s). Node image with everything: flash 457 756 B, DTCM 86 368 B, AXI SRAM 496 896 B (95 %), D2 250 528 B, D3 48 kB.

## Node image contents after M5/M6 (all untested on hardware)

Acquisition and decision as in §M3.1, plus: per-sample 100:1 decimation into the cadence history; 200 ms relearn in the main loop with double-buffered tiers consumed by the decision (`phase_err`); FDCAN1 summary + feature frames after every decision and the feeder's two-node path; USB CDC record upload at k_on + 2 500 and on `capture`; `cadence` and `can` console commands; settings v2 (`can_wait_us`, `onset_tol`).

## Not yet measured (hardware)

Everything in `docs/M3_TEST_PROCEDURE.md` and `docs/M6_M7_TEST_PROCEDURE.md`: DWT costs (block, extract, infer, close→trip, relearn), §4.2 on replayed waveforms, CAN arrival delay vs the 50 µs window, USB upload parity on bench records, bench control bring-up and the §6 plan.
