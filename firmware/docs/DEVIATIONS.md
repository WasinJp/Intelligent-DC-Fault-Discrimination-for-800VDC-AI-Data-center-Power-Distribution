# DEVIATIONS.md — where the firmware differs from the Python reference, and what bounds it

| # | where | difference | why | test that bounds it |
|---|---|---|---|---|
| 1 | fx_onset stream mode | pre-window = 150 µs ending 50 µs before the candidate sample, updated incrementally; Python uses the first 150 µs of a record | the node has no record start | §4.2: onset index within ±2 samples, decisions identical ≥ 99.5 % |
| 2 | float32 on the target vs float64 in Python | IIR and feature arithmetic | FPU | §6.2 tolerances |
