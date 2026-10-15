# DASHBOARD_SPEC.md — demo dashboard v1 (replay, event view, fault button) + firmware text fixes

**Written:** 2026-10-13. Owner of the spec: Wasin (design sessions). Implementer: Claude Code, working in this repository under `firmware/dashboard/` and `firmware/docs/`. Status: DRAFT for Wasin's review — nothing starts until he approves §2.
**Read first, in this order:** this file; `FIRMWARE_SPEC.md` §1 (working rules — they apply here unchanged), §8 (records, commands), §10 (bench control); `tools/record_decoder.py` (the record stream decoder — reuse it, do not rewrite it); `common/fx_upload.h` and `common/fx_record.h` (trailer and FXR1 layouts); `tools/make_fixtures.py` §HDR; `bench_control/cli_bc.c` (the bench-control console); `node/cli.c` `print_status` (the node console); `hardware/HIL_TESTBED_PLAN.md` §4.4 (the dashboard as proposed) and §3.2 F7/F8.
**Decision already taken (HANDOFF 13 Oct §4, do not re-litigate):** dashboard v1 = fault button + event view + replay. Nothing else is in v1.

## 0. Purpose

Two jobs, in this order of importance:

1. **Venue insurance.** On 2026-11-14 the demo must run even if the HIL box, the bench or a board fails on the day. Replay mode plays recorded events (bench or HIL records when we have them; dataset fixtures until then) through exactly the same event view the live hardware feeds. The audience sees the same screen either way.
2. **Make the timing claim visible.** The judges doubt the 0.25 ms decision on real hardware. The event view shows, per event: both nodes' measured waveforms, the onset the node found, the window close, the decision with P(TRIP), the TRIP edge, and the latency in µs as the node's own DWT counter measured it (`cyc_close_to_trip`, `cyc_onset_to_trip` at 480 MHz). No estimates, no numbers the hardware did not produce.

The dashboard **displays what the node reported**. It does not detect onsets, compute features or decide anything; it never re-derives a number the trailer already carries. (Replay of dataset fixtures, which have no trailer, takes the Python reference values — labelled as such on screen, §5.1.)

## 1. Working rules (in addition to FIRMWARE_SPEC §1)

1. **No changes under `dcsim/`, `common/`, `node/`.** v1 needs no new node firmware: state comes from the console `status` command, waveforms and decisions from the USB record upload that already exists. The telemetry stream (HIL plan F7) is v2, after the boards.
2. **No change to `bench_control/` behaviour** in this milestone (the text fixes of §8 are comments and strings only).
3. **Offline.** The venue may have no internet. No CDN, no package that downloads at run time. The UI is one HTML file with inline CSS/JS/SVG served by the Python process; it must also open as a plain file for the replay-only case.
4. **Dependencies:** Python 3.11+ (the repo `.venv`), `numpy`, `pyserial`. Nothing else without asking. Standard-library `http.server` + server-sent events (SSE) for the live link; no web framework.
5. **Windows first.** Serial ports are `COMx`; paths use `os.path`; the venue laptop runs Windows. Must also run on Linux for the host tests.
6. **Every source behaves the same.** Live nodes, live bench, decoded bench records and dataset fixtures all produce the same `Event` object (§5.1); the UI cannot tell them apart except by the "source" label it shows.
7. **Determinism in tests.** The host tests (§6) run with no hardware and no timing dependence; serial links are replaced by fakes that script the exact strings of §3.

## 2. Scope

| | v1 (this spec) | v2 (after the boards / the HIL meeting) |
|---|---|---|
| Replay | play a directory of records as a sequence; single-step and auto-advance | play synchronised with a bench DAC replay (`replay load/start`) |
| Event view | two-node waveforms aligned on SYNC; onset, window close, decision, P(TRIP), TRIP; DWT latencies | add the scope- / HIL-measured inception→breaker latency alongside the DWT numbers |
| Fault button | sends `fault rack <r_sel> <l_sel> now` / `fault feeder <r_sel> now` to the bench-control console; arm-key check first; shows the bench reply | fault command also raised to the HIL fault-scenario block (F8: bench-control GPIO → HIL DI) |
| Status strip | per node, from `status` polled at 2 Hz: samples, armed, overruns, last decision; bench `status` line | node telemetry stream at 20–50 Hz (F7) |
| Single-line diagram | **not in v1** | source → feeder → 800 V bus → converter → 48 V bus → racks, coloured by state, measured-vs-model labels, HIL internal signals |
| Records | the record_decoder output directory is the dashboard's store; nothing new on disk except `events.jsonl` (§5.1) | — |

## 3. Interfaces that already exist (reuse; exact strings)

**3.1 Record stream (node USB CDC → host).** `tools/record_decoder.py`: `Decoder(out).feed(bytes)` parses `"FXRU" | version u16 | payload_len u32 | payload | crc32` frames, writes `<out>/<event>_<node>.bin` (FXR1: 128-byte header + `fast_i u16[n]` + `fast_v u16[n]`) and appends one row to `<out>/node_trailers.csv` with columns
`event,node,label,W_ms,k_on,onset_found,i_pre,v_pre,sig_i,sig_v,<15 features>,raw_ALERT,raw_HOLD,raw_TRIP,p_TRIP,decision,layer,used_two_node,sample_count,sync_sample,cyc_extract,cyc_infer,cyc_close_to_trip,cyc_onset_to_trip`.
`k_on` in that CSV is **record-relative** (the decoder subtracts the record start); `sync_sample` and `sample_count` are in the node's sample counter. The dashboard imports `Decoder` and subclasses or wraps `handle()` to be notified per record; it does not reimplement the frame parser.

**3.2 FXR1 header** (`make_fixtures.py` `HDR = "<4sHHIIffffHHdddddddBBH12s20s"`, 128 bytes): magic, version, header_len, n_fast, n_slow, fs_fast, fs_slow, gain_i, gain_v, offset_i, offset_v, I_rated, V_ref, fs_i, fs_v, t0_fast, t0_slow, t_event, node_id (1 = rack), adc_bits, flags, event[12], label[20]. Physical value = `(code − offset) × gain` (see `make_fixtures.reconstruct`). The record's first sample is node sample `rec_start = round(t0_fast × fs_fast)`; its span is whatever the header's `n_fast` says (DEVIATIONS #15: an upload after a decision starts at the frozen baseline start, a `capture` record at `k_on − 100`) — never assume a fixed offset to `k_on`.

**3.3 Node console** (ST-Link VCP, **921600** 8N1 — `CONSOLE_BAUD` in `node/board.h`; lines end `\r\n`). `status` prints
`samples <n> armed <0|1> overruns <n> sysclk <hz>` then either `last: none` or
`last: layer <n> k_on <n> decision <HOLD|TRIP|ALERT> p_trip <f> sync_sample <n>` + `  cycles: extract <n> (<f> us) infer <n> (<f> us) close->trip <n> (<f> us) onset->trip <n> (<f> us)` + the 15 features (4 per line, `name=value`). Other commands used: `arm`, `capture` (replies `capture queued (USB CDC)`), `timing`, `timing_reset`. Parse `status` with a tolerant regex per line; never depend on the feature lines.

**3.4 Bench-control console** (ST-Link VCP, **921600** 8N1 — `CONSOLE_BAUD` in `bench_control/board_bc.h`; `bench_run.py` uses the same). `status` → one line `t <us> us running <0|1> gates 0x<hh> armed <0|1> faults <n> last_trigger <n> uvlo <..> trips <n> v_out <f> replays <n> busy <0|1>`. `fault rack <r_sel 0-2> <l_sel 0-2> [now|at <t_us>|edge <offset_us>]`, `fault feeder <r_sel 0-1> [...]`, `fault cancel`, `sync` (replies `sync`), `replay load <n>` / `replay start`. The firmware refuses a fault when the arm key is off; the dashboard checks `armed 1` in `status` before sending and shows the refusal text verbatim if it comes anyway.

**3.5 Dataset fixtures** (`host/tests/fixtures/`): `manifest.json` (events per label), `<event>_<node>.bin` (FXR1, **gitignored** — see §7), `reference_features.csv` (Python reference at W = 0.25/0.5/1.0: `event,node,label,decision,W_ms,...,k_on,onset_found,...,<features>,...`; `k_on` is record-relative), `reference_scores.csv` (`event,node,W_ms,model,raw_*,p_ALERT,p_HOLD,p_TRIP,argmax`). For replay before the boards exist, a fixture event's "decision" is `argmax` of the `model == node` row at W = 0.25 ms and its P(TRIP) is `p_TRIP` — shown with the source label "Python reference (fixture)", never as a node measurement.

**3.6 Clocks.** Node SYSCLK 480 MHz: `µs = cycles / 480`. Sample period 2 µs (500 kSa/s). Window W = 0.25 ms = 125 samples (`fx_config.h` N_W).

## 4. Layout

```
firmware/dashboard/
  README.md             how to run: replay-only, live bench, live HIL; the venue checklist (§5.6)
  server.py             entry point: argument parsing, HTTP + SSE, wires sources to the UI
  sources.py            Event dataclass; ReplaySource, NodeLink, BenchLink, FakeSerial (tests)
  records.py            thin wrapper over tools/record_decoder.Decoder + FXR1 reader + fixture reader
  static/index.html     the whole UI: inline CSS/JS/SVG; no external references
  tests/                pytest, host only (§6)
```
`tools/record_decoder.py` stays where it is and is imported (`sys.path` from the repo root, as the other tools do).

## 5. Functions

### 5.1 Sources and the `Event` object
```
Event:
  source        "node" | "bench_records" | "fixture"
  event, label  from the header
  node_records  {"feeder": Rec, "rack": Rec}   one or both
  Rec:
    i, v        float64 arrays, physical units (A, V), from codes via gain/offset
    t_us        float64 array; see alignment below
    k_on        int, record-relative (from the trailer CSV or reference CSV)
    onset_found bool
    decision    "HOLD" | "TRIP" | "ALERT" | None (no onset)
    p_trip      float or None
    layer, used_two_node, sample_count, sync_sample   (None for fixtures)
    cyc         {"extract","infer","close_to_trip","onset_to_trip"} cycles, or None for fixtures
    features    dict of the 15 names → float (trailer or reference)
    ref_kind    "node trailer" | "Python reference (fixture)"
```
**Alignment.** When both records carry `sync_sample > 0`: `t_us[k] = (rec_start + k − sync_sample) × 2` per node, so SYNC is t = 0 on both. Otherwise align on the feeder's `k_on` (t = 0 at the feeder onset) and show "aligned on onset (no SYNC)". Window close is `k_on + 125` samples. **TRIP marker (DEVIATIONS #11):** `cyc_close_to_trip` is stamped in the DMA block interrupt that completes the window (`stream_on_block`, after its 8-sample loop), so it counts from the end of that block, not from `k_on + 125`. In the node's sample counter the blocks are 8 samples and aligned to sample 0 (`g_count` only ever advances by whole blocks of `ADC_BLOCK = 8`), so: `k_close_blk = ceil((rec_start + k_on + 125) / 8) × 8` (absolute), and the TRIP marker is at absolute sample `k_close_blk + cyc_close_to_trip / 960` (960 cycles per 2 µs sample at 480 MHz), converted to `t_us` like any other sample. The marker is drawn as a vertical line labelled with the printed `close→trip` µs; the two must agree by construction. Residual bias: the stamp sits after the block's own processing (`T_DETECT_BLOCK` in `timing`, expected ≤ 2–3 µs), so the marker may lead the physical pin edge by that much; say so in the README, do not correct for it.

**Sources.**
- `ReplaySource(dir)`: reads a record_decoder output directory (`*.bin` + `node_trailers.csv`) or a fixtures directory (`*.bin` + `reference_features.csv` + `reference_scores.csv`; auto-detected by which CSV exists); groups records by event id; yields `Event`s in event-id order or in the order of an optional `--sequence` file (one event id per line, `#` comments). Methods: `next()`, `prev()`, `goto(event)`, `list()`.
- `NodeLink(port_console, port_cdc, role)`: a thread reading the CDC port into the `Decoder`; a second thread polling `status` at 2 Hz on the console port; `arm()`, `capture()`. On a new record it emits a partial `Event` for its node; `server.py` merges the two nodes' records by event id (or, live, by the nearest `sync_sample` within ±50 000 samples = 100 ms) into one `Event` and appends it to `<out>/events.jsonl` (everything in the `Event` except the arrays).
- `BenchLink(port)`: `status()` parsed to a dict; `fault(where, r_sel, l_sel=None, when="now")` returns the bench reply string; `sync()`.
- `FakeSerial(script)`: for tests; answers the exact strings of §3.3/§3.4 and streams a prepared FXRU byte string on the "CDC" side.

### 5.2 Event view (the screen)
Top: source label, event id, label (hidden in "judge mode", `--hide-labels`, so the audience sees the decision before the ground truth). Two stacked panels (feeder, rack), each with `i` and `v` on twin axes, t in µs with t = 0 at SYNC (or onset, §5.1), x-range default `[−200, +600]` µs and a button for the full record. Markers per node: onset (vertical line), window close (vertical line, +250 µs), TRIP (vertical line + a label with `close→trip <f> µs` and `onset→trip <f> µs`), decision badge with P(TRIP). Below: a table of the 15 features per node (values as reported). Keyboard: `←`/`→` previous/next event, `space` auto-advance (1 event / 3 s), `c` = `capture` on both nodes (live only).

The two numbers the judges are here for are rendered largest: **close→trip µs** and **onset→trip µs**, with the words "measured by the node's cycle counter" (or "no measurement — Python reference" on fixtures).

### 5.3 Fault button
Three buttons: **rack bolted** (`r_sel`, `l_sel` from a small selector, default 0/0), **rack high‑Z** (default 2/1), **feeder** (`r_sel` default 1). Flow: `BenchLink.status()` → if `armed 0`, show "arm key off — turn the key" and do nothing; else send the fault line, show the reply verbatim, and start a 2 s watch for the next record from each node. If no record arrives in 2 s, show "no record received" (do not retry on your own — a repeated fault is a safety matter, the operator decides). Every fault sent is logged with the timestamp and the reply to `<out>/faults.log`. Selector values are the firmware's (§3.4): under option B the physical R/L are a manual terminal block and the relay selectors do nothing on the bench — the UI still sends them because the firmware accepts them; the README says so (see also §8.2).

### 5.4 Status strip
Per node: `samples`, `armed`, `overruns`, last decision + P(TRIP), last `close→trip` µs; red if `overruns` grows or the console stops answering for 3 s. Bench: `running`, `armed`, `faults`, `uvlo`, `v_out`. Buttons: `arm` (both nodes), `sync`.

### 5.5 Replay mode
`python firmware/dashboard/server.py --replay <dir> [--sequence seq.txt] [--hide-labels] [--port 8765]` → opens `http://127.0.0.1:8765`. With `--export <file.html>` it also writes a **standalone** HTML with the sequence's events embedded as JSON (arrays as base64 float32, ≤ 20 events ≈ 1 MB) — the file that goes on a USB stick for the worst case (no Python at all). The standalone file is the same `index.html` with the data inlined; one code path, one UI.

### 5.6 Venue checklist (README)
Ordered list: ports (`python -m serial.tools.list_ports`), start order (bench → nodes → dashboard), `arm`, `sync` test, one fault with the key off (must refuse), one with it on, check the record arrives and the view updates, then switch the browser to full screen. The last line is the fallback: `--replay <today's records>` and the exported standalone file.

## 6. Acceptance (milestone D1, host only, `pytest firmware/dashboard/tests`)

1. **Decoder reuse:** a prepared FXRU byte string of 4 records (2 events × 2 nodes, built by the test from fixture `.bin` files + a synthetic trailer) fed through `records.py` yields 2 `Event`s with the trailer's `k_on`, `decision`, `p_trip`, `cyc_*` and `sync_sample` **unchanged** (equality, not tolerance) and `i`/`v` equal to `make_fixtures.reconstruct` of the codes (bit-identical).
2. **Alignment and TRIP marker:** with `sync_sample` set so the feeder onset is 37 samples and the rack onset 41 samples after SYNC, `t_us` at `k_on` is 74.0 and 82.0. TRIP marker per §5.1: with `rec_start = 1 000`, `k_on = 37` (record-relative), `cyc_close_to_trip = 28 800` → `k_close_blk = ceil(1 162 / 8) × 8 = 1 168`, marker at absolute sample 1 198.0, i.e. 36 samples (72 µs) after the close sample 1 162 — 12 µs of block rounding + 60.00 µs; and with `k_on = 35` (`1 160`, already a multiple of 8) the rounding term is 0. Latency labels `cyc/480` to 0.01 µs (`28 800` → `60.00 µs`).
3. **Fixture replay:** `ReplaySource(fixtures_sample)` over the committed sample (§7) lists every event in `manifest`-order, every `Event` carries `ref_kind == "Python reference (fixture)"`, `decision == argmax` and `p_trip == p_TRIP` of `reference_scores.csv` (`model == node`, `W_ms == 0.25`), `k_on` and `onset_found` of `reference_features.csv`; events with `onset_found == 0` show `decision is None`.
4. **Fault button:** against `FakeSerial`: with `armed 0` no `fault` line is written to the port; with `armed 1` the exact line `fault rack 2 1 now\r\n` is written, the scripted reply is returned, and `faults.log` has one line. A reply containing `refused` is surfaced unchanged.
5. **Status parsing:** the `status` texts of §3.3/§3.4 (incl. `last: none`, and a feature block) parse to the documented dicts; an unknown extra line is ignored, not fatal.
6. **Export:** `--export` on a 5-event sequence produces one HTML file < 2 MB with no `http://`, `https://` or `<link ` references, which when opened by a headless browser (Playwright is available in Claude Code's environment; if not, assert on the embedded JSON instead) shows event 1's id and its `close→trip` value.
7. **Numbers in MILESTONES.md:** a `D1` row with the test count, the export file size and the time to load a 20-event replay directory.

## 7. Inputs Claude Code needs from Wasin (before starting)

1. **A committed sample of fixture records.** `firmware/host/tests/fixtures/*.bin` is gitignored (41 MB). Commit a subset under `firmware/host/tests/fixtures_sample/` — 3 events per label × 9 labels × 2 nodes = 54 files ≈ 0.6 MB — plus a `manifest.json` listing them and copies of the matching `reference_features.csv` / `reference_scores.csv` rows (a 20-line script in `tools/` is fine; keep the event ids that `manifest.json` already lists first). Without this, Claude Code can only test against synthetic records.
2. **Approval of §2** (scope) and §5.3 (default selector values; whether the feeder button exists at all under option B — it does not, if the feeder injector is dropped; then hide it behind `--scope C`).
3. Nothing hardware-related: COM ports, SYNC wiring and HIL routing come later and are settings, not code.

## 8. Warm-up task: firmware-side stale text (HANDOFF 13 Oct §6)

Do this first, as one small PR, before the dashboard. Text only; no behaviour change. Confirm each one against the referenced source before editing.

| # | file | from | to | source |
|---|---|---|---|---|
| 8.1 | `FIRMWARE_SPEC.md` §9 | "the 150 kHz anti-alias" | "the 100 kHz anti-alias" | SCHEMATIC_DESIGN rev 2 §2 (item 16) |
| 8.2 | `bench_control/board_bc.h` (comment, l. 17–18), `bench_control/fault.h` (l. 2) | "74HC123" | "74HC221 (non-retriggerable)" | SCHEMATIC_DESIGN rev 2 item 5 |
| 8.3 | `bench_control/board_bc.h` selector block comment; `tools/bench_run.py` docstring | relay selectors PG0–PG7 select R/L | "under scope option B the fault R/L is a manual terminal block; the selector outputs are kept for option C and do nothing on the option-B bench" | HANDOFF §4, SCHEMATIC rev 2 §3 |
| 8.4 | `bench_control/board_bc.h` header comment | "NUCLEO-H743ZI2" | "NUCLEO-H753ZI (H743ZI2 pin-compatible)" | HANDOFF §1.1 |
| 8.5 | `node/CMakeLists.txt`, `bench_control/CMakeLists.txt` | `add_compile_definitions(STM32H743xx ...)` | a CMake option `FX_MCU` (`H753` default, `H743` allowed) that selects exactly **one** device define — the device header admits one — `STM32H753xx` or `STM32H743xx`; the linker script `STM32H743ZITX_FLASH.ld` stays (same flash/RAM map for ZI/ZI2 and H753ZI); README line on how to build for each | HANDOFF §1.1 |

Not in this task (chat-session decisions): `hardware/SCHEMATIC_DESIGN.md` §3 "ADC3" → ADC1/PA3, `MODEL.md` `i_co` → `i_rack`, Sheet 2 OPA2350 labels.

## 9. Out of scope for v1

The single-line diagram, HIL host signals, the F7 telemetry stream, any node or bench-control firmware change, retraining, anything that computes a feature or a decision on the host for display, authentication, multi-client, and a database. A second laptop mirroring the screen is a browser tab on the same URL — nothing to build.
