# M3_TEST_PROCEDURE.md — bringing the node image up the day the boards arrive

Image: `firmware/node` (NUCLEO-H743ZI2). Build: `firmware/node/CMakeLists.txt` header. Status before
the first board: **built, untested** (MILESTONES.md M3). Work through the steps in order; each has a
pass criterion and the file to paste the number into.

## 0. Bench

- NUCLEO-H743ZI2 on USB (ST-Link: power, programmer, VCP). Jumper JP1/JP3 default; SB on HSE bypass is
  the factory default for the Nucleo-144 (8 MHz MCO from the ST-Link).
- Pins: `firmware/node/board.h` (PA3 = current input, PC0 = voltage input, PF13 TRIP, PF14 ONSET,
  PF15 ALERT, PF12 SYNC in, PE9 role jumper, PD8/PD9 VCP). Change `board.h` if the front-end board uses
  other header pins; nothing else depends on the pin choice.
- Terminal at 921600 8N1 on the ST-Link COM port (or `python -m serial.tools.miniterm COMx 921600`).
- Scope: ch1 signal-generator output, ch2 ONSET, ch3 TRIP.

## 1. Flash and clock (10 min)

1. `cmake --build firmware/node/build`, flash `fx_node.hex` with STM32CubeProgrammer (or `st-flash`).
2. Expect `fx node ready` on the terminal and LD1 blinking at 1 Hz.
3. `status` → `sysclk 480000000`. If the board is a revision Y silicon (no VOS0), drop `clock.c` to
   PLLN 100 / VOS1 (400 MHz) and change `cycles_to_us` in `timing.h` and the DWT scale in the tools.
4. `selftest` → `selftest PASS ... extract <cycles>`. Paste the extract cycles into MILESTONES M3.

## 2. ADC sanity (20 min, resistor divider or signal generator)

1. Tie PA3 and PC0 to 3.3 V · k through a divider (e.g. 1.65 V). `status` → `samples` increasing by
   500 000 per second (compare two readings 10 s apart), `overruns 0`.
2. `settings set gain_i 1 ; settings set offset_i 0` (codes as units) and feed a 1 kHz sine of 1 Vpp
   on PA3: no trip; `status` must keep `overruns 0` for ≥ 1 min. This is the DMA/cache check.
3. Interrupt load: `timing` → `detect_block` mean must be < 7 680 cycles (16 µs). Target < 15 % of a
   core (< 2 300 cycles including the HAL DMA handler). Paste mean / p99 into docs/TIMING.md.

## 3. Record-mode parity (§6.4, 30 min, no analog signal)

1. On the host: `cmake --build firmware/host/build && firmware/host/build/fx_cli extract --dir
   firmware/host/tests/fixtures --out firmware/host/build/features_c.csv`.
2. `pip install pyserial` (venv), then
   `python firmware/tools/node_parity.py --port COMx --n 200` (all 2 160 records: `--n 0`, ~25 min).
3. Pass: `compare.py features` PASS (onset identical, features ≤ 1e-6 relative, spec ≤ 1e-4) — with
   `-ffp-contract=off` on both builds the numbers should be bit-identical except the libm functions
   (`log10`, `sqrt`): expect ≤ 1e-15 relative. Paste the compare table and the
   `cyc_extract` / `cyc_infer` statistics into MILESTONES M3 and TIMING.md.
4. If `cyc_infer` p99 > 80 µs · 480 = 38 400 cycles, the §7.4 budget needs the TIMING.md decision
   table (fewer iterations) before M4.

## 4. Stream mode on a replayed record (§4.2, 1 h, signal generator or the bench_control DACs)

1. Export DAC tables: `python firmware/tools/replay_waveforms.py --node rack --n 20` (12-bit codes at
   1 MSa/s in `firmware/bench_control/replay_tables/`, manifest with the Python onset and decision).
2. Replay a table through the front end (or an arbitrary-waveform generator loaded with the `.dac`
   file, 1 MSa/s, 0–3.3 V) into PA3/PC0 with the node `arm`ed. Scope: ONSET rises at the detected
   sample, TRIP at the decision (for TRIP-class records).
3. `status` after each replay → `k_on`, `decision`, `p_trip`, and the DWT cycles `extract`, `infer`,
   `close->trip`, `onset->trip`. Compare `decision` with `decision_ref` of the manifest; the host
   prediction for this agreement is `fx_cli stream` (MILESTONES §M3: onset within ±2 samples and
   identical decisions on the fixtures, record-start-at-baseline variant).
4. Pass (§7.4): `close->trip` p99 ≤ 80 µs; `onset->trip` ≤ 250 + 16 + 80 µs. Fill docs/TIMING.md
   (`timing` command gives mean / p99 / max over the last 1 024 decisions).

## 5. Settings persistence (5 min)

`settings set theta 0.3`, `settings save`, `reset`, `settings show` → theta 0.3. Then
`settings defaults`, `settings save`.

## Known gaps (not in the M3 image)

CAN link, two-node decision, USB record upload (`capture` prints a placeholder), cadence relearn on
the target (host-validated in `common/fx_cadence.c`; target port needs the float32 history and a
CMSIS-DSP FFT), bench_control image. Layer-1 thresholds default off.
