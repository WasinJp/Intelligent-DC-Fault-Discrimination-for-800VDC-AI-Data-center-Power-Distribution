"""node_parity.py — §6.4 target parity: push fixture records to the node over the ST-Link VCP, collect
its record-mode features + scores, compare with the host (fx_cli extract) at the §6.2 tolerances.

  python firmware/tools/node_parity.py --port COM5 [--fixtures firmware/host/tests/fixtures] [--n 200]
         [--host-csv firmware/host/build/features_c.csv] [--out firmware/docs/timing_study/node_parity.csv]

Needs pyserial (pip install pyserial). Protocol (node cli.c): "replay <event> <nbytes>\\n" -> node answers
"send\\n" -> the FXR1 record bytes with the slow streams stripped (header rewritten: n_slow 0, slow_format 0)
-> the node prints one CSV line per decision window (fx_cli extract format + extract/infer DWT cycles)
and "end\\n". The comparison reuses tools/compare.py (features mode); DWT cycle statistics are printed."""
import argparse
import glob
import os
import struct
import subprocess
import sys
import time
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HDR = "<4sHHIIffffHHdddddddBBH12s20s"
COLS = ("event,node,label,W_ms,k_on,onset_found,i_pre,v_pre,sig_i,sig_v,di_end,di_max,didt_max,t_rise,dv_early,di_early,"
        "r_dyn,v_sag_end,v_min,collapse,spec_i,spec_v,has_period,period_strength,phase_err,raw_ALERT,raw_HOLD,raw_TRIP,"
        "p_TRIP,decision,cyc_extract,cyc_infer").split(",")


def strip_slow(blob):
    h = list(struct.unpack(HDR, blob[:128]))
    n_fast = h[3]
    h[4] = 0; h[20] = 0                                   # n_slow, slow_format
    return struct.pack(HDR, *h) + blob[128:128 + 4 * n_fast]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--fixtures", default=os.path.join(ROOT, "firmware", "host", "tests", "fixtures"))
    ap.add_argument("--n", type=int, default=200, help="records to replay (0 = all)")
    ap.add_argument("--host-csv", default=os.path.join(ROOT, "firmware", "host", "build", "features_c.csv"))
    ap.add_argument("--out", default=os.path.join(ROOT, "firmware", "docs", "timing_study", "node_parity.csv"))
    a = ap.parse_args()
    import serial  # pyserial
    ser = serial.Serial(a.port, a.baud, timeout=5)
    time.sleep(0.2)
    ser.reset_input_buffer()
    files = sorted(glob.glob(os.path.join(a.fixtures, "*.bin")))
    if a.n:
        files = files[:a.n]
    rows = []
    t_start = time.time()
    for i, path in enumerate(files):
        with open(path, "rb") as f:
            blob = strip_slow(f.read())
        event = os.path.basename(path).split("_")[0]
        ser.write(f"replay {event} {len(blob)}\n".encode())
        ack = ser.readline().decode(errors="replace").strip()
        if ack != "send":
            print(f"{path}: unexpected '{ack}'"); continue
        ser.write(blob)
        while True:
            line = ser.readline().decode(errors="replace").strip()
            if not line or line == "end" or line.startswith("replay error"):
                if line.startswith("replay error"):
                    print(f"{path}: {line}")
                break
            parts = line.split(",")
            if len(parts) == len(COLS):
                rows.append(dict(zip(COLS, parts)))
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(files)} records, {time.time() - t_start:.0f} s", flush=True)
    d = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    d.to_csv(a.out, index=False)
    print(f"wrote {a.out}: {len(d)} rows from {len(files)} records")
    for c in ("cyc_extract", "cyc_infer"):
        v = d[c].astype(float).values / 480.0
        print(f"  {c}: mean {v.mean():.1f} us, p99 {np.percentile(v, 99):.1f} us, max {v.max():.1f} us (480 MHz)")
    py = sys.executable
    rc = subprocess.call([py, os.path.join(ROOT, "firmware", "tools", "compare.py"), "features", a.out, a.host_csv])
    print("node vs host:", "PASS" if rc == 0 else "FAIL")
    return rc


if __name__ == "__main__":
    sys.exit(main())
