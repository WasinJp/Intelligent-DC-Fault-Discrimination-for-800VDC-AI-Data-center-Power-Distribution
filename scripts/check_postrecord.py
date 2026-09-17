"""Integrity check of the stored streams: NaN / inf per label and per stream.
Usage: python scripts/check_postrecord.py data/events_v1large.h5      (a glob of shard files also works)

Why (2026-09-18): with FAULT_MODE = "held" the fault branch stays on through the 2 us and 10 us tiers
after the fine window. Its time constant L_f/(R_f+R_esr) goes down to ~0.05 us, RK4 is unstable for
dt/tau > 2.785, the branch current diverges and the causal anti-alias filter carries the NaN to the
end of the record. The <= 1 ms Layer-2 features are NOT affected (fine window, 50 ns); the post-event
record that Layer 3 needs is. Expected from the sweep ranges: ~92 % of high_z, ~17 % of resistive_pp,
~9 % of high_z_48, none of the bolted classes, no benign event."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from collections import defaultdict
from dcsim.dataset import iter_events
STREAMS = ("fast_i", "fast_v", "slow_i", "slow_v", "rack_fast_i", "rack_fast_v", "rack_slow_i", "rack_slow_v")
n = defaultdict(int); bad = defaultdict(lambda: defaultdict(int)); first = defaultdict(list)
for k, e in iter_events(sys.argv[1]):
    lab = e.attrs["label"]; n[lab] += 1; w = e["waveforms"]
    for s in STREAMS:
        if s in w:
            x = w[s][...]; m = ~np.isfinite(x)
            if m.any():
                bad[lab][s] += 1
                if s == "slow_i":
                    first[lab].append((w.attrs["slow_t0"] + np.argmax(m) / 5e3 - e.attrs["t_event"]) * 1e3)
print(f"{'label':18s} {'events':>7s}   non-finite streams (events affected)")
for lab in n:
    txt = ", ".join(f"{s}: {c} ({c/n[lab]*100:.0f} %)" for s, c in bad[lab].items()) or "clean"
    if first[lab]:
        txt += f"   | first bad slow_i sample at +{np.min(first[lab]):.1f} .. +{np.max(first[lab]):.1f} ms after the event"
    print(f"{lab:18s} {n[lab]:7d}   {txt}")
