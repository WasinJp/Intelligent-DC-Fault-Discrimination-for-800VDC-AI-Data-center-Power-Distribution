# firmware/host — build and test on a PC (no hardware)

Everything under `firmware/common/` is compiled here with gcc and exercised by the milestone
tests of `FIRMWARE_SPEC.md` §6. The same sources go into the STM32H7 images unchanged.

## Prerequisites

- gcc (Linux: distro package; Windows: WinLibs/MinGW-w64, e.g. `winget install BrechtSanders.WinLibs.POSIX.UCRT`,
  then put its `mingw64\bin` on `PATH`).
- CMake ≥ 3.20 and Ninja. The repo venv has them: `python -m pip install cmake ninja` inside `.venv`,
  which puts `cmake.exe` / `ninja.exe` / `ctest.exe` in `.venv\Scripts`.
- The repo's Python venv (numpy, scipy, scikit-learn, h5py, pandas) for the tools and the compare step.

## Build and run the tests

```bash
# from the repo root
cmake -S firmware/host -B firmware/host/build -G Ninja
cmake --build firmware/host/build
ctest --test-dir firmware/host/build --output-on-failure
```

On Windows with the venv tools: `.venv\Scripts\cmake.exe`, `.venv\Scripts\ninja.exe`
(`-DCMAKE_MAKE_PROGRAM=<repo>\.venv\Scripts\ninja.exe`) and `.venv\Scripts\ctest.exe`.

Tests: `unit_common` (filters, onset, features smoke, tree walk, record header),
`m1_extract` + `m1_feature_agreement` (§6.2), `m2_score` + `m2_model_agreement` + `m2_bench` (§6.3),
`m3_stream_vs_record[_prefix]` (§4.2 stream-mode vs record-mode onset and decisions on the replayed
fixtures, with and without a random quiet prefix), `m5_work_agreement` (§6.2 WORK features on the
records that carry a slow stream, double learner), `m5_f32_*` and `m5_cmsis_*` (the target learner
`fx_cadence32` with the generic and the CMSIS-DSP FFT backends; `fx_cli_cmsis` is built when
`third_party/cmsis_dsp` is present). `unit_common` also round-trips the CAN frames and the upload framing.

Other images: `firmware/node` (sensing node) and `firmware/bench_control` (bench control), both with
`-DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake` (see their CMakeLists.txt headers) after
`bash firmware/tools/fetch_stm32.sh`.

Alternative model tables: `-DFX_MODEL_DATA_H=<path to an exported fx_model_data.h>` (the §7.4 budget
study builds `host/build-it100/150/300` against `host/models/v1xl6k_it*/`). Models trained on
v1large044 are kept in `host/models/v1large044/` (header + reference scores + provenance).

## Regenerating the inputs

| what | command (repo root, venv python) |
|---|---|
| filter tables + unit-test vectors | `python firmware/tools/export_filters.py` |
| fixtures (needs the dataset h5 shards) | `python firmware/tools/make_fixtures.py --h5 "data/events_v1large044_s*.h5"` |
| models + `fx_model_data.h` + reference scores | `python firmware/tools/train_model.py --cache data/nodes_v1xl6k --features firmware/host/tests/fixtures/reference_features.csv --scores firmware/host/tests/fixtures/reference_scores.csv` |
| §7.4 budget study (hours) | `python firmware/tools/budget_study.py --cache data/nodes_v1xl6k --relay both --iters auto,100,150,300` |
| compare by hand | `python firmware/tools/compare.py features <c.csv> <ref.csv> [--work]` |
| DAC replay tables (M4) | `python firmware/tools/replay_waveforms.py --node rack --n 100` |
| node parity over serial (M3) | `python firmware/tools/node_parity.py --port COMx` |
| USB record stream decoder (M6) | `python firmware/tools/record_decoder.py --port COMx --out data/bench_records/run1` |
| bench test plan runner (M7) | `python firmware/tools/bench_run.py --bench COMa --feeder COMb --rack COMc --out data/bench_runs/run1 [--dry-run]` |
| TIMING.md from the study JSONs | `python firmware/tools/make_timing_md.py` |
| STM32 CMSIS/HAL sources (node build) | `bash firmware/tools/fetch_stm32.sh` |

`fx_cli` usage is in the header of `fx_cli.c`.
