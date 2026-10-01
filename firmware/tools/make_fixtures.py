"""make_fixtures.py — dataset h5 events -> 500 kSa/s record files + Python reference features
(FIRMWARE_SPEC.md §6.1).

  python firmware/tools/make_fixtures.py --h5 "data/events_v1large044_s*.h5" \\
         [--out firmware/host/tests/fixtures] [--per-label 120] [--slow-per-label 15] \\
         [--seed 0] [--windows 0.25,0.5,1.0]

For every selected event and both nodes (feeder: i_L / v_bus; rack: i_co / v_out):
  1. the stored 2 MSa/s fast streams are brought to 500 kSa/s with synth._aa_decimate(x, 2e6, 4)
     (the OPEN-12 rate-study call), giving 2 600 samples = 0.2 ms before + 5 ms after the anchor;
  2. they are quantised to uint16 ADC codes (offset 32768) with a per-node base calibration,
     gain_i = 16*I_rated/65536 A/code (+-8 x rated), gain_v = 8*V_ref/65536 V/code
     (+-4 x V_ref), doubled per record only as far as needed so nothing clips (the header
     carries the gain used) — the record the node would hold;
  3. the Python reference features are computed by features.extract on the RECONSTRUCTED
     float32 values (code - offset) * gain, i.e. exactly the values the C code sees, at
     W = 0.25 / 0.5 / 1.0 ms with fs_fast = 500e3, plus detect_onset for k_on;
  4. the slow streams (as stored, float32, truncated to the fast window end) are included in
     the record of the first --slow-per-label events of each label for milestone M5.
The distance between the features of the requantised record and of the unquantised decimated
stream is reported in manifest.json (a diagnostic of step 2, not an acceptance criterion).
Record format: firmware/common/fx_record.h (FXR1)."""
import argparse
import glob
import json
import os
import struct
import subprocess
import sys
import time

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from dcsim.dataset import iter_events, load_obs, h5_files      # noqa: E402
from dcsim.synth import _aa_decimate                          # noqa: E402
from dcsim.features import extract, detect_onset, ALL         # noqa: E402
from dcsim.studies import DECISION                            # noqa: E402

FS = 500e3
F_SLOW = 5e3
DECIM = 4
HDR = "<4sHHIIffffHHdddddddBBH12s20s"
assert struct.calcsize(HDR) == 128
OFFSET = 32768
DIAG = ["n_tiers", "T1_est", "T2_est", "phase_err_t1", "phase_err_t2", "resid_period", "t_on_rel"]


def git_hash():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def quantize(x, base_gain):
    """Codes with the finest gain base_gain * 2**m (m >= 0) at which the record does not clip.
    Returns (codes, gain float32, m)."""
    for m in range(8):
        gain = np.float32(base_gain * 2 ** m)
        codes = np.rint(x / gain) + OFFSET
        if codes.min() >= 0 and codes.max() <= 65535:
            return codes.astype(np.uint16), gain, m
    raise ValueError(f"record does not fit even at 128 x base gain: {x.min()}..{x.max()}")


def reconstruct(codes, gain):
    return (codes.astype(np.float32) - np.float32(OFFSET)) * np.float32(gain)


def select_events(h5, per_label, seed):
    labels = {}
    for k, e in iter_events(h5):
        labels.setdefault(e.attrs["label"], []).append(k)
    rng = np.random.default_rng(seed)
    chosen = {}
    for lab in sorted(labels):
        keys = sorted(labels[lab])
        n = min(per_label, len(keys))
        chosen[lab] = sorted(rng.choice(keys, n, replace=False).tolist())
    return chosen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--h5", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "firmware", "host", "tests", "fixtures"))
    ap.add_argument("--per-label", type=int, default=120)
    ap.add_argument("--slow-per-label", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--windows", default="0.25,0.5,1.0")
    a = ap.parse_args()
    windows = [float(w) * 1e-3 for w in a.windows.split(",")]
    os.makedirs(a.out, exist_ok=True)
    for old in glob.glob(os.path.join(a.out, "*.bin")):
        os.remove(old)
    t_start = time.time()
    chosen = select_events(a.h5, a.per_label, a.seed)
    with_slow = {k for lab, keys in chosen.items() for k in keys[:a.slow_per_label]}
    wanted = {k: lab for lab, keys in chosen.items() for k in keys}
    print(f"selected {len(wanted)} events: " + ", ".join(f"{l} {len(k)}" for l, k in chosen.items())
          + f"; slow streams in {len(with_slow)}", flush=True)

    rows, n_rec, total_bytes = [], 0, 0
    requant = {f: 0.0 for f in ALL}
    gain_steps = {}
    for k, e in iter_events(a.h5):
        if k not in wanted:
            continue
        label = wanted[k]
        pr = e["params"].attrs
        for node_id, node in ((0, "feeder"), (1, "rack")):
            obs = load_obs(e, node=node)
            I_n, V_n = (pr["I_out_rated"], pr["V_ref48"]) if node == "rack" else (pr["I_rated"], pr["V_ref"])
            I_n, V_n = float(I_n), float(V_n)
            fi = _aa_decimate(obs["fast_i"].astype(np.float64), 2e6, DECIM)
            fv = _aa_decimate(obs["fast_v"].astype(np.float64), 2e6, DECIM)
            n = fi.size
            ci, gain_i, m_i = quantize(fi, 16.0 * I_n / 65536.0)     # base: +-8 x I_rated
            cv, gain_v, m_v = quantize(fv, 8.0 * V_n / 65536.0)       # base: +-4 x V_ref
            gain_steps[f"i_x{2 ** m_i}"] = gain_steps.get(f"i_x{2 ** m_i}", 0) + 1
            gain_steps[f"v_x{2 ** m_v}"] = gain_steps.get(f"v_x{2 ** m_v}", 0) + 1
            fi_r, fv_r = reconstruct(ci, gain_i), reconstruct(cv, gain_v)
            t0 = float(obs["fast_t"][0])
            fast_t = t0 + np.arange(n) / FS
            m_slow = obs["slow_t"] < t0 + n / FS
            si, sv, st = obs["slow_i"][m_slow], obs["slow_v"][m_slow], obs["slow_t"][m_slow]
            base = dict(fast_t=fast_t, slow_i=si, slow_v=sv, slow_t=st, fs_i=float(obs["fs_i"]), fs_v=float(obs["fs_v"]),
                        t_event=float(obs["t_event"]), fs_fast=FS, adc_bits=int(obs["adc_bits"]))
            o_q = dict(base, fast_i=fi_r, fast_v=fv_r)
            o_u = dict(base, fast_i=fi, fast_v=fv)
            k_on, i_pre, v_pre, sig_i, sig_v, found = detect_onset(fi_r.astype(np.float64), fv_r.astype(np.float64),
                                                                  75, base["fs_i"], base["fs_v"], n_sm=2)
            for W in windows:
                f = extract(o_q, I_n, V_n, W=W)
                fu = extract(o_u, I_n, V_n, W=W)
                for c in ALL:
                    d = abs(f[c] - fu[c])
                    if np.isfinite(d):
                        requant[c] = max(requant[c], float(d))
                rows.append(dict(event=k, node=node, label=label, decision=DECISION[label], W_ms=W * 1e3,
                                 I_rated=I_n, V_ref=V_n, fs_i=base["fs_i"], fs_v=base["fs_v"], has_slow=int(k in with_slow),
                                 k_on=int(k_on), onset_found=int(found), i_pre=i_pre, v_pre=v_pre, sig_i=sig_i, sig_v=sig_v,
                                 **{c: f[c] for c in ALL}, **{c: f[c] for c in DIAG}))
            slow = k in with_slow
            hdr = struct.pack(HDR, b"FXR1", 1, 128, n, si.size if slow else 0, FS, F_SLOW, float(gain_i), float(gain_v),
                              OFFSET, OFFSET, I_n, V_n, base["fs_i"], base["fs_v"], t0, float(st[0]) if slow else 0.0,
                              base["t_event"], node_id, base["adc_bits"], 2 if slow else 0, k.encode(), label.encode())
            data = hdr + ci.astype("<u2").tobytes() + cv.astype("<u2").tobytes()
            if slow:
                data += si.astype("<f4").tobytes() + sv.astype("<f4").tobytes()
            with open(os.path.join(a.out, f"{k}_{node}.bin"), "wb") as fh:
                fh.write(data)
            n_rec += 1
            total_bytes += len(data)
        if n_rec % 200 == 0:
            print(f"  {n_rec} records, {time.time() - t_start:.0f} s", flush=True)

    df = pd.DataFrame(rows)
    csv = os.path.join(a.out, "reference_features.csv")
    df.to_csv(csv, index=False, float_format="%.17g")
    manifest = dict(generated=time.strftime("%Y-%m-%dT%H:%M:%S"), repo_git=git_hash(), h5=a.h5, h5_files=h5_files(a.h5),
                    seed=a.seed, per_label=a.per_label, slow_per_label=a.slow_per_label, windows_ms=[W * 1e3 for W in windows],
                    n_events=len(wanted), n_records=n_rec, record_bytes=total_bytes, csv_rows=len(df),
                    onset_found_fraction=float(df.onset_found.mean()), events=chosen,
                    calibration="gain_i = 16*I_rated/65536 * 2^m, gain_v = 8*V_ref/65536 * 2^m (smallest m without "
                                "clipping, per record), offset 32768, gains float32",
                    gain_multiplier_counts=gain_steps,
                    requantization_max_abs_feature_change=requant,
                    command=" ".join(sys.argv))
    with open(os.path.join(a.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(f"wrote {n_rec} records ({total_bytes / 1e6:.1f} MB) and {csv} ({len(df)} rows) in {time.time() - t_start:.0f} s")
    print("requantisation effect (max |delta feature|):", {k: f"{v:.2e}" for k, v in requant.items()})


if __name__ == "__main__":
    main()
