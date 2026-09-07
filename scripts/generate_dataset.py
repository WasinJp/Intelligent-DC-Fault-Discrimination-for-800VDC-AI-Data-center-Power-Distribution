"""Generate the v0.2 Monte Carlo event dataset (MODEL.md §5, §10).
Usage: python scripts/generate_dataset.py [out.h5] [n_per_class] [master_seed]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dcsim.dataset import generate
out = sys.argv[1] if len(sys.argv) > 1 else "data/events_v0.2.h5"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20260907
generate(out, master_seed=seed, n_per_class=n)
