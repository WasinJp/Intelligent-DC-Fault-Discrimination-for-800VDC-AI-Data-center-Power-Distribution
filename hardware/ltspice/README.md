# LTspice checks for the 120 W bench

Four netlists, one per risk. Each has a `FIX` switch: `FIX=0` is the circuit as drawn on Sheets 1–2, `FIX=1` has the fixes. Every file was run in ngspice 42 before delivery; the numbers below are those runs, so your LTspice results should land close to them.

## How to run

1. LTspice: **File → Open**, set the file type to *Netlists (*.cir)*, open the file.
2. **Run** (the running-man button). A plot window opens; click on it and use **Add Traces** (or Ctrl+A) to pick signals. The header of each file lists the useful ones.
3. **View → SPICE Error Log** (Ctrl+L) shows the `.meas` results (peak currents, energies, voltages).
4. To compare before/after in one run, un-comment the `.step` lines at the bottom of the file. In the plot, right-click → *Select Steps* switches between runs.

The MOSFET and diode models are **generic approximations** written for these files (Rds, Vth, capacitances, breakdown). For the final sign-off, download the vendor models (Infineon IRFP7430 / IRFB4110, TI OPA2350), swap them in, and compare peak Vds and switch energy against each datasheet's limits.

## Reference results (ngspice)

### A — rack fault loop (`A_rack_fault_loop.cir`), R_f48 = 63 mΩ

| | as drawn (FIX=0) | fixed (FIX=1) |
|---|---|---|
| bus before the fault | 8.7 V, **23 W in Q_brk** (ground-referenced driver can't turn it on) | 11.9 V, 0.17 W |
| relay trips at 250 µs | Q_brk avalanches at 42 V; 12 V node swings to −7.6 … −11.5 V | TVS clamps Q_brk at 22–26 V (0.4–3.7 mJ); node dips to about −2 V |
| relay misses, one-shot ends at 5 ms: energy into Q_f48 | **21 / 62 / 202 mJ** (10 / 30 / 100 µH) | 0.35 mJ (stray wiring only) |
| fault current peak (relay misses) | — | 108 / 93 / 74 A (10 / 30 / 100 µH) |

The remaining 0.35 mJ comes from the 50 nH between D_fw and Q_f48's drain, so mount the diode right at the drain.

### B — feeder breaker (`B_feeder_breaker.cir`), feeder fault at 1 ms, trip at 1.25 ms

| variant | what happens |
|---|---|
| ground-referenced driver (DRV=0) | **Breaker never opens.** As supply(−) falls, Q_fb turns itself back on (Vgs settles at 2.25 V); the supply keeps feeding 4.9 A, Q_fb dissipates 11 W, and the bus stays at 37 V. |
| isolated driver, 40 V part (DRV=1, BVQ=42) | Opens, but once the bus decays, 48 V exceeds the FET's breakdown: continuous avalanche, 0.26 A into the fault, **11 W** in Q_fb. |
| isolated driver, 100 V part (DRV=1, BVQ=110) | Opens cleanly: 0 A, bus to 0.16 V. Turn-off spike from the line inductance reaches 110 V (0.25 mJ avalanche); a 58 V TVS (TVS=1) clamps it at 66 V. |

### C — K1 inrush (`C_k1_inrush.cir`)

| | peak through K1/F1 | fuse I²t | C_in after |
|---|---|---|---|
| hot plug, supply 1000 µF / 50 mΩ | 102 A | 1.7 A²s | **58 V trapped** behind the ORing diode |
| hot plug, stiff supply 4700 µF / 10 mΩ | 116 A | 2.9 A²s | **73 V trapped: over the 63 V rating**, and on the converter input |
| K1 first, then supply on (FIX=1) | 1.6 A | 0.02 A²s | 47.9 V |
| 10 Ω precharge (PRE=1) | 4.8 A | 0.04 A²s | 47.9 V |

### D — anti-alias filter (`D_antialias_filter.cir`)

| | −3 dB | at 100 kHz | at 400 kHz | step |
|---|---|---|---|---|
| as drawn | 52.7 kHz | −9.4 dB | −45.1 dB | no overshoot, t90 = 8.9 µs |
| corrected caps | 100.6 kHz | −2.9 dB | −48.1 dB | 12 % overshoot, t90 = 6.3 µs |

The step response of the filter you build is what the bench dataset's synthesis layer should use.
