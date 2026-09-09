"""Generate a Monte Carlo event dataset (MODEL.md §5, §10).
Usage: python scripts/generate_dataset.py [out.h5] [n_per_class] [master_seed] [--rates]
--rates  also store the OPEN-12 front-end sweep: {100k,250k,500k,1M} Sa/s x {12,14,16} bit
         plus 2 MSa/s at fixed 12/14/16 bit (the default stream keeps the drawn bits)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dcsim.dataset import generate
args = [a for a in sys.argv[1:] if not a.startswith("--")]
out = args[0] if len(args) > 0 else "data/events_v1.h5"
n = int(args[1]) if len(args) > 1 else 200
seed = int(args[2]) if len(args) > 2 else 20260907
rates = None
if "--rates" in sys.argv:
    rates = [(f, b) for f in (100e3, 250e3, 500e3, 1e6, 2e6) for b in (12, 14, 16)]
generate(out, master_seed=seed, n_per_class=n, rate_configs=rates)
