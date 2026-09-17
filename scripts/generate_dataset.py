"""Generate a Monte Carlo event dataset (MODEL.md §5, §10).
Usage: python scripts/generate_dataset.py [out.h5] [n_per_class] [master_seed] [--rates]
--large  v1-large: >= 5 000 benign events (1 667 per benign class), n faults per class
--benign N   with --large: N events per benign class instead of 1 667 (v1-xl: 10000 -> 30 000 benign)
--shard i/n  write only events with idx % n == i (run n processes in parallel; same events as one run).
             Use an output name with the shard in it, e.g. data/events_v1xl_s0.h5, and read the set
             back with the glob "data/events_v1xl_s*.h5".
--rates  also store the OPEN-12 front-end sweep: {100k,250k,500k,1M} Sa/s x {12,14,16} bit
         plus 2 MSa/s at fixed 12/14/16 bit (the default stream keeps the drawn bits)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dcsim.dataset import generate
_skip = {i + 1 for i, a in enumerate(sys.argv) if a in ("--benign", "--shard")}
args = [a for i, a in enumerate(sys.argv) if i >= 1 and not a.startswith("--") and i not in _skip]
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
    if "--benign" in sys.argv:
        n_ben = int(sys.argv[sys.argv.index("--benign") + 1])
    n_spec = {l: (n_ben if l in BENIGN else n) for l in LABELS}
    print("v1-large:", n_spec)
shard = None
if "--shard" in sys.argv:
    i, m = sys.argv[sys.argv.index("--shard") + 1].split("/")
    shard = (int(i), int(m))
generate(out, master_seed=seed, n_per_class=n_spec, rate_configs=rates, shard=shard)
