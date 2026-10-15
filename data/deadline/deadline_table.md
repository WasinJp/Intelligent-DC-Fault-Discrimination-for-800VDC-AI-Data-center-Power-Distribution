# Deadline study - data/events_v1xl6k_s*.h5, 1500 fault events, W = 0.25 ms, processing 96 us, t_brk 20 us

Times in ms after inception. median / p5 / p95 over the events where the condition occurs within the record; n = how many of the class it occurs in. 'margin met' = fraction of events (condition occurring) where T_brk < deadline.


## bolted_pp (300 events)

| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |
|---|---|---|---|---|---|
| T_on | 0.005 | -0.001 | 0.011 | 300 | - |
| T_trip | 0.351 | 0.345 | 0.357 | 300 | - |
| T_brk | 0.371 | 0.365 | 0.377 | 300 | - |
| D1_iL_gt_2x | 0.064 | 0.014 | 1.388 | 16 | 18.8 % |
| D2_irack_gt_2x | 2.666 | 2.666 | 2.666 | 1 | 100.0 % |
| D1_iL_gt_3x | > record |  |  | 0 | - |
| D2_irack_gt_3x | > record |  |  | 0 | - |
| D3_vbus_lt_uvlo | 0.028 | 0.006 | 0.121 | 300 | 0.0 % |
| D4_vout_lt_uvlo48_held | 3.095 | 0.282 | 14.666 | 35 | 91.4 % |

## resistive_pp (300 events)

| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |
|---|---|---|---|---|---|
| T_on | 0.005 | 0.001 | 0.012 | 300 | - |
| T_trip | 0.351 | 0.347 | 0.358 | 300 | - |
| T_brk | 0.371 | 0.367 | 0.378 | 300 | - |
| D1_iL_gt_2x | 0.056 | 0.015 | 0.645 | 12 | 8.3 % |
| D2_irack_gt_2x | > record |  |  | 0 | - |
| D1_iL_gt_3x | > record |  |  | 0 | - |
| D2_irack_gt_3x | > record |  |  | 0 | - |
| D3_vbus_lt_uvlo | 0.068 | 0.011 | 2.083 | 295 | 23.1 % |
| D4_vout_lt_uvlo48_held | 2.816 | 1.267 | 26.561 | 36 | 100.0 % |

## high_z (300 events)

| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |
|---|---|---|---|---|---|
| T_on | 0.010 | 0.002 | 0.068 | 300 | - |
| T_trip | 0.356 | 0.348 | 0.414 | 300 | - |
| T_brk | 0.376 | 0.368 | 0.434 | 300 | - |
| D1_iL_gt_2x | 0.847 | 0.847 | 0.847 | 1 | 100.0 % |
| D2_irack_gt_2x | > record |  |  | 0 | - |
| D1_iL_gt_3x | > record |  |  | 0 | - |
| D2_irack_gt_3x | > record |  |  | 0 | - |
| D3_vbus_lt_uvlo | 3.055 | 0.167 | 46.483 | 111 | 91.9 % |
| D4_vout_lt_uvlo48_held | 4.768 | 1.559 | 112.099 | 15 | 100.0 % |

## bolted_48 (300 events)

| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |
|---|---|---|---|---|---|
| T_on | 0.003 | -0.002 | 0.008 | 300 | - |
| T_trip | 0.349 | 0.344 | 0.354 | 300 | - |
| T_brk | 0.369 | 0.364 | 0.374 | 300 | - |
| D1_iL_gt_2x | 0.239 | 0.239 | 0.239 | 1 | 0.0 % |
| D2_irack_gt_2x | 0.068 | 0.013 | 0.669 | 277 | 10.5 % |
| D1_iL_gt_3x | > record |  |  | 0 | - |
| D2_irack_gt_3x | 0.096 | 0.021 | 0.854 | 207 | 19.3 % |
| D3_vbus_lt_uvlo | 0.703 | 0.255 | 101.185 | 3 | 66.7 % |
| D4_vout_lt_uvlo48_held | 0.166 | 0.026 | 3.867 | 62 | 27.4 % |

## high_z_48 (300 events)

| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |
|---|---|---|---|---|---|
| T_on | 0.003 | -0.002 | 0.007 | 300 | - |
| T_trip | 0.349 | 0.344 | 0.353 | 300 | - |
| T_brk | 0.369 | 0.364 | 0.373 | 300 | - |
| D1_iL_gt_2x | > record |  |  | 0 | - |
| D2_irack_gt_2x | 0.092 | 0.015 | 5.626 | 66 | 28.8 % |
| D1_iL_gt_3x | > record |  |  | 0 | - |
| D2_irack_gt_3x | 0.053 | 0.031 | 0.306 | 19 | 5.3 % |
| D3_vbus_lt_uvlo | 20.155 | 6.270 | 34.040 | 2 | 100.0 % |
| D4_vout_lt_uvlo48_held | 2.319 | 0.567 | 21.451 | 14 | 100.0 % |

Reading: a deadline much longer than T_brk means 0.25 ms is a choice (earliest discriminating point at the budget, with margin), not a necessity; a deadline shorter than T_brk in a class means that class needs Layer 1 (per-sample threshold) - say which. '> record' = the condition never occurs within the stored record (seconds): no deadline from that mechanism for that class.