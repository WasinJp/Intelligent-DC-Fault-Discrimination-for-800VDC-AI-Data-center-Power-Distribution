"""MODEL.md §8 validation checks. All must pass before any dataset is generated.
Runs the v0.3 set (a)-(d) or the v0.4 set (a)-(d) + (e)-(h) depending on events.CORE_VERSION."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dcsim.events import CORE_VERSION
if CORE_VERSION == "v0.4":
    from dcsim.model_v04 import (PARAMS_BASELINE, check_converter_steady_state, check_voltage_loop_step,
                                 check_ramp_energy_balance, check_fault48_limit, check_history_tier)
    from dcsim.model import check_droop_steady_state, check_rlc_discharge, check_segmented_vs_uniform
    from dcsim.model import PARAMS_BASELINE as P03
    checks = [("(b) droop steady state [v0.3 core]", check_droop_steady_state, P03),
              ("(a) RLC discharge vs analytic [v0.3 core]", check_rlc_discharge, P03),
              ("(c) segmented vs uniform 50 ns [v0.3 core]", check_segmented_vs_uniform, P03),
              ("(e) converter steady state", check_converter_steady_state, PARAMS_BASELINE),
              ("(f) voltage loop vs linear model", check_voltage_loop_step, PARAMS_BASELINE),
              ("(g) ramp-limit balance / slew / tracking", check_ramp_energy_balance, PARAMS_BASELINE),
              ("(h) 48 V fault current limit", check_fault48_limit, PARAMS_BASELINE),
              ("(d) history tier 10 us vs 2 us [v0.4]", check_history_tier, PARAMS_BASELINE)]
else:
    from dcsim.model import (PARAMS_BASELINE, check_droop_steady_state, check_rlc_discharge,
                             check_segmented_vs_uniform, check_history_tier)
    checks = [("(b) droop steady state", check_droop_steady_state, PARAMS_BASELINE),
              ("(a) RLC discharge vs analytic", check_rlc_discharge, PARAMS_BASELINE),
              ("(c) segmented vs uniform 50 ns", check_segmented_vs_uniform, PARAMS_BASELINE),
              ("(d) history tier 10 us vs 2 us", check_history_tier, PARAMS_BASELINE)]
print(f"core {CORE_VERSION}")
ok_all = True
for name, fn, p in checks:
    err, ok = fn(p)
    ok_all &= ok
    print(f"{name:44s} err = {err:.2e}  {'PASS' if ok else 'FAIL'}")
print("ALL PASS" if ok_all else "*** FAILURES ***")
