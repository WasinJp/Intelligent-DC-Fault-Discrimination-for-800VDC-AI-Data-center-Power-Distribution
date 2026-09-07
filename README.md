# Intelligent DC Fault Discrimination for 800 VDC AI Data Center Power Distribution

Physics-based digital twin, Monte Carlo event dataset and discrimination pipeline for the "nuisance trip" problem in 800 VDC AI data center power distribution.
**Built for Delta Cup 2026 (Energy Track).**

As rack power densities approach 1 MW, synchronized GPU workloads produce current transients that conventional threshold protection cannot reliably tell apart from genuine DC faults. Tripping on a workload step interrupts a multi-million-baht training run; holding through a fault burns a busbar. This repository quantifies where that ambiguity actually lives and shows a discriminator that resolves most of it from the same two sensors.

## Headline results (dataset v0.2, 1 400 synthetic events — see RESULTS.md)

- **The gray zone is high-impedance faults.** With thresholds set for zero false trips, the best conventional detector (magnitude OR di/dt OR voltage collapse) catches 100 % of bolted and 96.5 % of resistive faults but misses **72.5 % of high-Z faults**. No threshold setting reaches < 0.1 % false trips and < 1 % missed. (Figure 1)
- **The discriminator cuts high-Z misses from 72.5 % to 30 % at the same zero-false-trip budget**, and to 11.5 % at a 3 % false-trip operating point, from features computed on the observable line current and bus voltage only, within 1 ms of onset. (Figure 2)
- **Workload-awareness halves nuisance trips on scheduled workloads** (3.9 % → 2.0 %) and improves generalisation to larger segments. (Figure 2b, Figure 4)
- **Feeder-level sensing has a floor:** high-Z misses rise to 45 % below 0.15 p.u. fault current, and the bus capacitor hides half of load-side arcs. This resolves the sensing-architecture question in favour of a hybrid feeder + per-rack design. (Figure 3)

## Repository layout

```
MODEL.md             versioned model specification — single source of truth (v0.2)
RESULTS.md           gate 2 / gate 3 numbers with limitations
dcsim/
  model.py           Numba-JIT RK4 physics core (segmented time base, series arc)
  events.py          §5 taxonomy, §6 parameter draws, gate-1 sanity gate, schedule
  synth.py           §7 sensor synthesis: fast 2 MSa/s + slow 50 kSa/s streams
  features.py        discrimination features from observables only
  dataset.py         Monte Carlo generation to HDF5 (§10 schema)
  studies.py         gate 2 threshold study, gate 3 classifier / latency / ablation
scripts/
  validate_model.py  the three closed-form validation checks (§8)
  generate_dataset.py
  run_studies.py
  make_figures.py    regenerates every figure in /figures
figures/
  architecture.png   three-layer protection architecture
  benign_vs_fault.png, grayzone_highz.png   single-pair waveform illustrations
  fig1_grayzone_montecarlo.png   gate 2
  fig2_discriminator.png         gate 3
  fig3_sensing_architecture.png  feeder vs per-rack evidence
  fig4_latency_ablation.png
```

## Reproduce

```bash
pip install -r requirements.txt
python scripts/validate_model.py            # 3 checks, ~5 s
python scripts/generate_dataset.py          # 1 400 events -> data/events_v0.2.h5, ~2.5 min
python scripts/run_studies.py               # features + gates 2 and 3
python scripts/make_figures.py
```

A dataset is fully reproducible from (MODEL.md version, master seed). The classifier never sees hidden states or ground truth; onset detection is done on the observables.

## Status

- v0.1 (Aug 2026): model spec, core, single-pair figures.
- **v0.2 (Sep 2026): Stage 2 — full taxonomy, sensor synthesis, dataset, gates 2–3, four result figures.**
- Next: v0.3 multi-segment model with per-rack nodes; 48 V testbed design for the final round; dataset v1 with ≥ 5 000 benign events to resolve the 0.1 % false-trip target (OPEN-8).
