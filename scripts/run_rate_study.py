"""OPEN-12: acquisition front-end sensitivity. Sample rate x ADC bits.
Usage: python scripts/run_rate_study.py [events_rates.h5]
The dataset must have been generated with rate_configs (see generate_dataset.py --rates)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import h5py, numpy as np
from dcsim.studies import rate_study

h5 = sys.argv[1] if len(sys.argv) > 1 else "data/events_v1_rates.h5"
with h5py.File(h5, "r") as h:
    names = [n for n in h["session_meta"].attrs["rate_configs"].split(",") if n]
configs = [None] + names
cache = os.path.join(os.path.dirname(h5), "rates")
os.makedirs(cache, exist_ok=True)
print(f"{len(configs)} front-end configurations (default + {len(names)} stored)")
res = rate_study(h5, configs, cache_dir=cache)
with open(os.path.join(cache, "rate_study.json"), "w") as fh:
    json.dump(res, fh, indent=1, default=float)
print()
print("=== OPEN-12 summary: +workload-aware, 10-seed CV (mean %), 1 ms window ===")
print(f"{'config':14s} {'fs (kSa/s)':>10s} {'bits':>5s} {'false trip':>11s} {'missed':>8s} {'high-Z':>8s} {'gray-zone hz':>13s} {'0.25ms missed':>14s}")
for n, r in res.items():
    w = r["repeated"]["+workload-aware"]
    print(f"{n:14s} {r['fs_fast']/1e3:10.0f} {r['adc_bits']:5.0f} {w['false_trip']['mean']*100:11.2f} {w['missed']['mean']*100:8.2f} {w['high_z_missed']['mean']*100:8.2f} {r['gray_zone_high_z']*100:13.1f} {r['latency_025']['missed']*100:14.2f}")
