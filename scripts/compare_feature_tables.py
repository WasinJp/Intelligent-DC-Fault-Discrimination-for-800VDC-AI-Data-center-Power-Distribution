"""Regression test between two node caches: are the Layer-2 feature tables the same?
Usage: python scripts/compare_feature_tables.py data/nodes data/nodes_v1large_044
v0.4.4 must reproduce the v0.4.3 tables exactly (the event window is untouched by the held-fault rule)."""
import sys, os
import numpy as np, pandas as pd
a_dir, b_dir = sys.argv[1], sys.argv[2]
ok = True
for node in ("feeder", "rack"):
    a = pd.read_csv(os.path.join(a_dir, f"features_{node}.csv")); b = pd.read_csv(os.path.join(b_dir, f"features_{node}.csv"))
    if a.shape != b.shape or list(a.columns) != list(b.columns):
        print(f"{node}: shapes/columns differ {a.shape} vs {b.shape}"); ok = False; continue
    num = a.select_dtypes("number").columns
    same_txt = a.drop(columns=num).astype(str).equals(b.drop(columns=num).astype(str))
    diff = ~np.isclose(a[num].values, b[num].values, rtol=0, atol=0, equal_nan=True)
    print(f"{node}: {len(a)} rows | labels/text identical: {same_txt} | numeric cells differing: {int(diff.sum())}")
    if diff.any():
        cols = num[diff.any(axis=0)]; print("   columns:", list(cols)[:12], "| rows:", int(diff.any(axis=1).sum()))
    ok &= same_txt and not diff.any()
print("REGRESSION PASS: feature tables bit-identical" if ok else "REGRESSION FAIL: send me this printout")
