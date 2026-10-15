# Deadline study - data/events_v1xl6k_s*.h5, 1000 fault events, W = 0.25 ms, processing 96 us, t_brk 20 us

Times in ms after inception. median / p5 / p95 over the events where the condition occurs within the record; n = how many of the class it occurs in. 'margin met' = fraction of events (condition occurring) where T_brk < deadline.


## high_z (500 events)

| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |
|---|---|---|---|---|---|
| T_on | 0.010 | 0.003 | 0.070 | 500 | - |
| T_trip | 0.356 | 0.349 | 0.416 | 500 | - |
| T_brk | 0.376 | 0.369 | 0.436 | 500 | - |
| D1_iL_gt_2x | 0.133 | 0.087 | 0.775 | 3 | 33.3 % |
| D2_irack_gt_2x | > record |  |  | 0 | - |
| D1_iL_gt_3x | > record |  |  | 0 | - |
| D2_irack_gt_3x | > record |  |  | 0 | - |
| D3_vbus_lt_uvlo | 2.874 | 0.160 | 44.045 | 177 | 89.3 % |
| D4_vout_lt_uvlo48_held | 5.936 | 1.605 | 170.745 | 23 | 100.0 % |

## high_z_48 (500 events)

| quantity | median | p5 | p95 | n (of class) | margin met (T_brk < deadline) |
|---|---|---|---|---|---|
| T_on | 0.003 | -0.002 | 0.008 | 500 | - |
| T_trip | 0.349 | 0.344 | 0.354 | 500 | - |
| T_brk | 0.369 | 0.364 | 0.374 | 500 | - |
| D1_iL_gt_2x | > record |  |  | 0 | - |
| D2_irack_gt_2x | 0.092 | 0.014 | 13.460 | 110 | 26.4 % |
| D1_iL_gt_3x | > record |  |  | 0 | - |
| D2_irack_gt_3x | 0.128 | 0.029 | 0.526 | 35 | 11.4 % |
| D3_vbus_lt_uvlo | 20.155 | 1.865 | 79.627 | 4 | 100.0 % |
| D4_vout_lt_uvlo48_held | 1.847 | 0.135 | 294.091 | 34 | 85.3 % |

Reading: a deadline much longer than T_brk means 0.25 ms is a choice (earliest discriminating point at the budget, with margin), not a necessity; a deadline shorter than T_brk in a class means that class needs Layer 1 (per-sample threshold) - say which. '> record' = the condition never occurs within the stored record (seconds): no deadline from that mechanism for that class.