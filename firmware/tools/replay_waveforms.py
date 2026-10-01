"""replay_waveforms.py — fixture records -> bench_control DAC replay tables (FIRMWARE_SPEC.md §10, M4).

  python firmware/tools/replay_waveforms.py --fixtures firmware/host/tests/fixtures \\
         [--events 00013,00051,...] [--labels bolted_48,high_z,...] [--n 100] [--node rack] \\
         [--out firmware/bench_control/replay_tables] [--dac-fs-i <A>] [--dac-fs-v <V>] [--c-header]

Each 500 kSa/s record (2 600 samples per channel) becomes a 1 MSa/s DAC table (5 200 samples per
channel, linear interpolation between the record samples: the node's 150 kHz anti-alias filter
removes the interpolation steps) of 12-bit codes, 0..4095, matching the node front end's full
scale: code = round(x / FS * 4095 * k_scale) clipped, where FS is the full scale of the node
input (default: the record's own node base FS, i.e. the bench values when the records are bench
records, else the dataset's fs_i / fs_v scaled to the --dac-fs values). Output: one .bin per
record (uint16 i[5200] then v[5200]), a manifest.csv (event, label, node, scale factors, expected
onset index at 500 kSa/s and Python decision from reference_features.csv), and optionally a C
header with the tables for the bench_control flash (--c-header)."""
import argparse
import csv
import glob
import json
import os
import struct
import sys
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HDR = "<4sHHIIffffHHdddddddBBH12s20s"
F_REC = 500e3
F_DAC = 1e6
DAC_BITS = 12


def read_record(path):
    with open(path, "rb") as f:
        hb = f.read(128)
        magic, ver, hbytes, n_fast, n_slow, fs_fast, fs_slow, gain_i, gain_v, off_i, off_v, I_rated, V_ref, fs_i, fs_v, \
            t0f, t0s, t_event, node, bits, slow_fmt, event, label = struct.unpack(HDR, hb)
        assert magic == b"FXR1" and ver == 1
        ci = np.frombuffer(f.read(2 * n_fast), dtype="<u2").astype(np.float64)
        cv = np.frombuffer(f.read(2 * n_fast), dtype="<u2").astype(np.float64)
    i = (ci - off_i) * gain_i
    v = (cv - off_v) * gain_v
    return dict(event=event.rstrip(b"\0").decode(), label=label.rstrip(b"\0").decode(), node="rack" if node else "feeder",
                I_rated=I_rated, V_ref=V_ref, fs_i=fs_i, fs_v=fs_v, i=i, v=v, n=n_fast, fs=fs_fast)


def to_dac(x, fs_phys, n_rec):
    """resample 500 kSa/s -> 1 MSa/s (linear) and quantise to unipolar 12-bit codes on [0, fs_phys]"""
    t_rec = np.arange(n_rec) / F_REC
    t_dac = np.arange(int(n_rec * F_DAC / F_REC)) / F_DAC
    y = np.interp(t_dac, t_rec, x)
    codes = np.rint(y / fs_phys * (2 ** DAC_BITS - 1))
    clipped = int(((codes < 0) | (codes > 2 ** DAC_BITS - 1)).sum())
    return np.clip(codes, 0, 2 ** DAC_BITS - 1).astype(np.uint16), clipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures", default=os.path.join(ROOT, "firmware", "host", "tests", "fixtures"))
    ap.add_argument("--events", help="comma-separated event ids (default: --n per label)")
    ap.add_argument("--labels", help="comma-separated labels to include")
    ap.add_argument("--n", type=int, default=100, help="records to export when --events is not given")
    ap.add_argument("--node", default="rack", choices=["rack", "feeder", "both"])
    ap.add_argument("--out", default=os.path.join(ROOT, "firmware", "bench_control", "replay_tables"))
    ap.add_argument("--dac-fs-i", type=float, help="DAC full scale in record units of I_rated (default 13 rack / 2 feeder)")
    ap.add_argument("--dac-fs-v", type=float, help="DAC full scale in record units of V_ref (default 1.25)")
    ap.add_argument("--c-header", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ref = pd.read_csv(os.path.join(a.fixtures, "reference_features.csv"), dtype={"event": str}, float_precision="round_trip")
    ref = ref[ref.W_ms == 0.25].set_index(["event", "node"])
    files = sorted(glob.glob(os.path.join(a.fixtures, "*.bin")))
    wanted_events = set(a.events.split(",")) if a.events else None
    wanted_labels = set(a.labels.split(",")) if a.labels else None
    rows, per_label = [], {}
    for path in files:
        r = read_record(path)
        if a.node != "both" and r["node"] != a.node:
            continue
        if wanted_events and r["event"] not in wanted_events:
            continue
        if wanted_labels and r["label"] not in wanted_labels:
            continue
        if not wanted_events and per_label.get(r["label"], 0) >= a.n:
            continue
        per_label[r["label"]] = per_label.get(r["label"], 0) + 1
        fs_i = (a.dac_fs_i or (13.0 if r["node"] == "rack" else 2.0)) * r["I_rated"]    # SCHEMATIC_DESIGN §2 full scales
        fs_v = (a.dac_fs_v or 1.25) * r["V_ref"]
        ci, clip_i = to_dac(r["i"], fs_i, r["n"])
        cv, clip_v = to_dac(r["v"], fs_v, r["n"])
        name = f"{r['event']}_{r['node']}"
        with open(os.path.join(a.out, name + ".dac"), "wb") as f:
            f.write(ci.astype("<u2").tobytes() + cv.astype("<u2").tobytes())
        k = (r["event"], r["node"])
        rows.append(dict(table=name + ".dac", event=r["event"], label=r["label"], node=r["node"], n_dac=ci.size, fs_dac=F_DAC,
                         dac_fs_i=fs_i, dac_fs_v=fs_v, clipped_i=clip_i, clipped_v=clip_v,
                         k_on_ref=int(ref.loc[k, "k_on"]) if k in ref.index else -1,
                         onset_found_ref=int(ref.loc[k, "onset_found"]) if k in ref.index else -1,
                         decision_ref=ref.loc[k, "decision"] if k in ref.index else ""))
    man = pd.DataFrame(rows)
    man.to_csv(os.path.join(a.out, "manifest.csv"), index=False)
    if a.c_header:
        with open(os.path.join(a.out, "replay_tables.h"), "w", newline="\n") as f:
            f.write("/* replay_tables.h — generated by firmware/tools/replay_waveforms.py; 12-bit DAC codes at 1 MSa/s,\n"
                    " * i[] then v[] per table (FIRMWARE_SPEC.md §10). */\n#include <stdint.h>\n")
            f.write(f"#define REPLAY_N_TABLES {len(rows)}\n#define REPLAY_N_SAMPLES {rows[0]['n_dac'] if rows else 0}\n")
            for row in rows:
                d = np.fromfile(os.path.join(a.out, row["table"]), dtype="<u2")
                f.write(f"static const uint16_t replay_{row['event']}_{row['node']}[2 * REPLAY_N_SAMPLES] = {{\n")
                for i in range(0, d.size, 32):
                    f.write("  " + ",".join(str(int(x)) for x in d[i:i + 32]) + ",\n")
                f.write("};\n")
            f.write("static const struct { const char *name; const char *label; const uint16_t *codes; int k_on_ref; } REPLAY_TABLES[] = {\n")
            for row in rows:
                f.write(f"  {{ \"{row['event']}_{row['node']}\", \"{row['label']}\", replay_{row['event']}_{row['node']}, {row['k_on_ref']} }},\n")
            f.write("};\n")
    with open(os.path.join(a.out, "manifest.json"), "w") as f:
        json.dump(dict(n_tables=len(rows), per_label=per_label, fs_dac=F_DAC, bits=DAC_BITS, command=" ".join(sys.argv)), f, indent=1)
    print(f"wrote {len(rows)} tables to {a.out}: {per_label}; clipped samples: i {man.clipped_i.sum() if len(man) else 0}, "
          f"v {man.clipped_v.sum() if len(man) else 0}")


if __name__ == "__main__":
    main()
