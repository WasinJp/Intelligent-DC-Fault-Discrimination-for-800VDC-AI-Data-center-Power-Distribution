# CLAUDE.md — house rules for Claude Code sessions (IDCFC, Delta Cup 2026)

## The project in one paragraph
Machine-learning fault discrimination for an 800 VDC AI-data-centre power segment (800 V source → feeder → bus → rack converter → 48 V bus → GPU load, 132 kW). Two sensing nodes (STM32H7) detect an event onset, take 0.25 ms of data, compute 15 features, run a gradient-boosted tree model and raise TRIP. The Python simulator (`dcsim/`) and the relay result are final; the firmware (`firmware/`) is a bit-for-bit port of the Python features and model. The demo is closed-loop hardware-in-the-loop on a dSPACE box running `simscape/dcsim_rt_hil`.

## How you are used
- **One milestone per session, from a written spec** (e.g. `firmware/SETTINGS_PROFILE_SPEC.md` = milestone S1). Do what the spec says, in its order. If the spec is ambiguous or seems wrong, stop and say so in the PR description — do not guess and do not widen the scope.
- Wasin (the owner) reviews every PR, runs MATLAB, the h5 datasets and all hardware. You cannot run any of those.
- Design and review happen in separate chat sessions; your job is implementation and host tests.

## Rules — do not break these
1. `MODEL.md` is the single source of truth for physics and parameters. Do not edit `MODEL.md`, `dcsim/` (generator / physics core) or `simscape/` unless the spec explicitly says so.
2. `firmware/common/` **feature code is the contract** (`fx_features`, `fx_filters`, `fx_onset`, `fx_cadence*`): it matches `dcsim/features.py` bit for bit. Do not change it unless the spec explicitly says so. Decision code (`fx_relay`) may change only when the spec says so.
3. **Every change is host-tested.** Build and run the host tests before opening the PR (commands below); all tests must pass. Add a test for every new behaviour the spec names.
4. **Deviations are recorded, never silent.** Any place the firmware differs from the Python reference or from the spec goes into `firmware/docs/DEVIATIONS.md` with the reason and the test that bounds it.
5. **Acceptance criteria are written before the run and not changed after it.** If a check in the spec fails, report the numbers in the PR and `firmware/docs/MILESTONES.md` — do not tune thresholds, tolerances or expectations to make it pass.
6. Never commit anything under `data/` (large, gitignored, produced on Wasin's machine), build directories, or binary fixtures (`firmware/host/tests/fixtures/*.bin`).
7. Do not touch `clock.c`, the CAN protocol, the dashboard or the N6 display unless the spec says so.
8. The PR description lists every file touched, every test added, every deviation, and any numbers the spec asks for.

## Build and test (host, from the repo root)
```bash
cmake -S firmware/host -B firmware/host/build -G Ninja
cmake --build firmware/host/build
ctest --test-dir firmware/host/build --output-on-failure
```
Target images (`firmware/node`, `firmware/bench_control`): `bash firmware/tools/fetch_stm32.sh`, then CMake with `-DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake` (see the CMakeLists.txt headers). Build them to check they compile; they cannot be run here.
`fx_cli` usage is in the header of `firmware/host/fx_cli.c`. Fixture records (`.bin`) are gitignored: tests that need them are skipped or fail in a fresh clone — say which ones in the PR rather than working around it.

## Read first
`firmware/FIRMWARE_SPEC.md`, `firmware/docs/MILESTONES.md`, `firmware/docs/DEVIATIONS.md`, `firmware/host/README.md`, then the spec for this session.

## Style
Plain C11, no dynamic allocation on the target, no new dependencies. Comments say *why*, and cite the spec section (e.g. `/* FIRMWARE_SPEC §7.1 */`). Match the existing code style.
