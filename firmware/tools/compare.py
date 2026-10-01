"""compare.py — C output vs Python reference with the FIRMWARE_SPEC.md tolerances.

  python firmware/tools/compare.py features <c.csv> <ref.csv> [--work]     §6.2
  python firmware/tools/compare.py scores   <c.csv> <ref.csv>              §6.3

Prints the worst case per feature / score and exits 0 only if every criterion passes.
--work also checks has_period / period_strength / phase_err (milestone M5)."""
import sys
import numpy as np
import pandas as pd

KEY = ["event", "node", "W_ms"]
FEAT_REL = ["di_end", "di_max", "didt_max", "t_rise", "dv_early", "di_early", "v_sag_end", "v_min", "r_dyn", "collapse"]
FEAT_SPEC = ["spec_i", "spec_v"]
WORK = {"has_period": ("rel", 1e-6), "period_strength": ("abs", 1e-4), "phase_err": ("rel", 1e-6)}
REL_TOL, ABS_FLOOR, SPEC_TOL = 1e-6, 1e-9, 1e-4
SCORE_TOL = 1e-5


def load(path):
    d = pd.read_csv(path, dtype={"event": str, "node": str, "model": str, "argmax": str, "decision": str},
                    float_precision="round_trip")      # exact parse of the %.17g values
    d["event"] = d["event"].str.strip()
    d["W_ms"] = d["W_ms"].astype(float).round(6)
    return d


def merge(c, r, key):
    m = c.merge(r, on=key, suffixes=("_c", "_r"), how="outer", indicator=True)
    bad = m[m["_merge"] != "both"]
    if len(bad):
        print(f"ROW MISMATCH: {len(bad)} rows present on one side only, e.g.\n{bad[key + ['_merge']].head()}")
    return m[m["_merge"] == "both"].copy(), len(bad)


def row_id(m, i):
    return f"{m.event.iloc[i]}/{m.node.iloc[i]}/W={m.W_ms.iloc[i]:g}" + (f"/{m.model.iloc[i]}" if "model" in m else "")


def check_col(m, col, kind, tol, floor=ABS_FLOOR):
    """returns (n_fail, line) for one column"""
    a, b = m[col + "_c"].values.astype(float), m[col + "_r"].values.astype(float)
    nan_a, nan_b = np.isnan(a), np.isnan(b)
    nan_mismatch = nan_a != nan_b
    ok_both = ~nan_a & ~nan_b
    d = np.abs(a - b)
    if kind == "rel":
        rel = d / np.maximum(np.abs(b), 1e-300)
        passed = ok_both & ((d <= tol * np.abs(b)) | (d <= floor))
    else:
        rel = d / np.maximum(np.abs(b), 1e-300)
        passed = ok_both & (d <= tol)
    passed[nan_a & nan_b] = True
    n_fail = int((~passed).sum())
    i_abs = int(np.nanargmax(np.where(ok_both, d, -1))) if ok_both.any() else 0
    i_rel = int(np.nanargmax(np.where(ok_both & (np.abs(b) > floor), rel, -1))) if ok_both.any() else 0
    line = (f"  {col:16s} n={len(m):5d}  worst abs {d[i_abs]:.3e} ({row_id(m, i_abs)})  "
            f"worst rel {rel[i_rel]:.3e} ({row_id(m, i_rel)})  nan-mismatch {int(nan_mismatch.sum())}  "
            f"{'PASS' if n_fail == 0 else f'FAIL x{n_fail}'}")
    return n_fail, line


def compare_features(c_path, r_path, work):
    c, r = load(c_path), load(r_path)
    m, n_bad = merge(c, r, KEY)
    fails = n_bad
    print(f"features: {len(m)} matched rows ({c.event.nunique()} events)")
    k_ok = (m.k_on_c.values == m.k_on_r.values) & (m.onset_found_c.values == m.onset_found_r.values)
    print(f"  onset index identical: {int(k_ok.sum())}/{len(m)}" + ("" if k_ok.all() else "  FAIL"))
    if not k_ok.all():
        fails += int((~k_ok).sum())
        bad = m[~k_ok]
        print(bad[KEY + ["k_on_c", "k_on_r", "onset_found_c", "onset_found_r"]].head(10).to_string())
    for col in FEAT_REL:
        n, line = check_col(m, col, "rel", REL_TOL); fails += n; print(line)
    for col in FEAT_SPEC:
        n, line = check_col(m, col, "abs", SPEC_TOL); fails += n; print(line)
    if work:
        mw = m[m.has_slow == 1].reset_index(drop=True) if "has_slow" in m else m   # records that carry a slow stream
        print(f"  WORK features on the {len(mw)} rows whose record holds the slow stream:")
        for col, (kind, tol) in WORK.items():
            n, line = check_col(mw, col, kind, tol); fails += n; print(line)
    else:
        print("  (WORK features not checked: milestone M5; pass --work)")
    print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


def compare_scores(c_path, r_path):
    c, r = load(c_path), load(r_path)
    m, n_bad = merge(c, r, KEY + ["model"])
    fails = n_bad
    print(f"scores: {len(m)} matched rows; models: {sorted(m.model.unique())}")
    for model in sorted(m.model.unique()):
        mm = m[m.model == model].reset_index(drop=True)
        print(f" model {model}: {len(mm)} rows")
        for col in ["raw_ALERT", "raw_HOLD", "raw_TRIP", "p_ALERT", "p_HOLD", "p_TRIP"]:
            n, line = check_col(mm, col, "abs", SCORE_TOL); fails += n; print(line)
        am = (mm.argmax_c.values == mm.argmax_r.values)
        print(f"  argmax identical: {int(am.sum())}/{len(mm)}" + ("" if am.all() else "  FAIL"))
        fails += int((~am).sum())
    print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


def main(argv):
    if len(argv) < 3 or argv[0] not in ("features", "scores"):
        print(__doc__); return 2
    if argv[0] == "features":
        ok = compare_features(argv[1], argv[2], "--work" in argv[3:])
    else:
        ok = compare_scores(argv[1], argv[2])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
