"""MODEL.md §8 validation checks. All three must pass before any dataset is generated."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dcsim.model import (PARAMS_BASELINE, check_droop_steady_state, check_rlc_discharge,
                         check_segmented_vs_uniform)
p = PARAMS_BASELINE
for name, fn in [("(b) droop steady state", check_droop_steady_state),
                 ("(a) RLC discharge vs analytic", check_rlc_discharge),
                 ("(c) segmented vs uniform 50 ns", check_segmented_vs_uniform)]:
    err, ok = fn(p)
    print(f"{name:32s} err = {err:.2e}  {'PASS' if ok else 'FAIL'}")
