"""Generate a Monte Carlo event dataset (MODEL.md §5, §10).
Usage: python scripts/generate_dataset.py [out.h5] [n_per_class] [master_seed] [--rates]
--large  v1-large: >= 5 000 benign events (1 667 per benign class), n faults per class
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
n_spec = n
if "--large" in sys.argv:
    # v1-large: >= 5 000 benign (OPEN-8), faults at n per class; benign split evenly over 3 classes
    from dcsim.events import BENIGN, LABELS
    n_ben = max(n, 1667)
    n_spec = {l: (n_ben if l in BENIGN else n) for l in LABELS}
    print("v1-large:", n_spec)
generate(out, master_seed=seed, n_per_class=n_spec, rate_configs=rates)
