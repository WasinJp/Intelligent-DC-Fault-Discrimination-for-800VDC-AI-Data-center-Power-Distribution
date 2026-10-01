"""record_decoder.py — decode the node's USB record stream (FIRMWARE_SPEC.md §8, fx_upload.h) into
FXR1 record files (the layout make_fixtures.py writes) plus a CSV of the node's own decision trailers,
so bench records feed fx_cli extract / compare.py unchanged.

  python firmware/tools/record_decoder.py --port COM7 --out data/bench_records/run1 [--seconds 600]
  python firmware/tools/record_decoder.py --file capture.bin --out data/bench_records/run1

Frame: "FXRU" | version u16 | payload_len u32 | payload | crc32 (IEEE, over the payload)
payload = FXR1 header (128) | fast_i u16[n] | fast_v u16[n] | trailer (156 bytes, see fx_upload.h).
Output: <out>/<event>_<node>.bin, <out>/node_trailers.csv (fx_cli extract columns + DWT cycles), <out>/decode.log.
Then: fx_cli extract --dir <out> --out host.csv ; compare.py features <out>/node_trailers.csv host.csv
(the node's features vs the host's on the same record = the §6.4 parity on real bench data)."""
import argparse
import os
import struct
import sys
import time
import zlib

HDR = "<4sHHIIffffHHdddddddBBH12s20s"
TRAILER = "<IIIBBBBf" + "d" * 15 + "IIII"
FEATURES = ["di_end", "di_max", "didt_max", "t_rise", "dv_early", "di_early", "r_dyn", "v_sag_end", "v_min", "collapse",
            "spec_i", "spec_v", "has_period", "period_strength", "phase_err"]
DEC = {0: "HOLD", 1: "TRIP", 2: "ALERT"}


class Decoder:
    def __init__(self, out):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.buf = bytearray()
        self.n_ok = self.n_bad = 0
        self.csv = open(os.path.join(out, "node_trailers.csv"), "a")
        if self.csv.tell() == 0:
            self.csv.write("event,node,label,W_ms,k_on,onset_found,i_pre,v_pre,sig_i,sig_v," + ",".join(FEATURES)
                           + ",raw_ALERT,raw_HOLD,raw_TRIP,p_TRIP,decision,layer,used_two_node,sample_count,sync_sample,"
                           "cyc_extract,cyc_infer,cyc_close_to_trip,cyc_onset_to_trip\n")
        self.log = open(os.path.join(out, "decode.log"), "a")

    def feed(self, data):
        self.buf += data
        while True:
            i = self.buf.find(b"FXRU")
            if i < 0:
                if len(self.buf) > 3:
                    self.buf = self.buf[-3:]
                return
            if i > 0:
                self.buf = self.buf[i:]
            if len(self.buf) < 10:
                return
            ver, plen = struct.unpack_from("<HI", self.buf, 4)
            if ver != 1 or plen > 4 * 1024 * 1024:
                self.buf = self.buf[4:]; self.n_bad += 1; continue
            if len(self.buf) < 10 + plen + 4:
                return
            payload = bytes(self.buf[10:10 + plen])
            crc = struct.unpack_from("<I", self.buf, 10 + plen)[0]
            self.buf = self.buf[10 + plen + 4:]
            if zlib.crc32(payload) & 0xFFFFFFFF != crc:
                self.n_bad += 1; self.log.write("crc error\n"); continue
            self.handle(payload)

    def handle(self, p):
        h = struct.unpack_from(HDR, p, 0)
        n_fast = h[3]
        event = h[21].rstrip(b"\0").decode(errors="replace")
        label = h[22].rstrip(b"\0").decode(errors="replace")
        node = "rack" if h[18] == 1 else "feeder"
        t0_fast, fs_fast = h[14], h[5]
        rec_start = int(round(t0_fast * fs_fast))      # first sample of the record (node sample counter)
        rec_len = 128 + 4 * n_fast
        if len(p) != rec_len + struct.calcsize(TRAILER):
            self.n_bad += 1; self.log.write(f"length mismatch {len(p)}\n"); return
        with open(os.path.join(self.out, f"{event}_{node}.bin"), "wb") as f:
            f.write(p[:rec_len])
        t = struct.unpack_from(TRAILER, p, rec_len)
        k_on, sample_count, sync_sample, decision, layer, has_period, used_two, p_trip = t[:8]
        x = t[8:23]
        cyc = t[23:27]
        # k_on in record coordinates: the host's record-mode detector should find the same index
        vals = [event, node, label, "0.25", str(k_on - rec_start), "1", "nan", "nan", "nan", "nan"]
        vals += [repr(float(v)) for v in x]
        vals += ["nan", "nan", "nan", repr(float(p_trip)), DEC.get(decision, "?"), str(layer), str(used_two), str(sample_count),
                 str(sync_sample)] + [str(c) for c in cyc]
        self.csv.write(",".join(vals) + "\n")
        self.csv.flush()
        self.n_ok += 1
        self.log.write(f"{time.strftime('%H:%M:%S')} {event} {node} {label} k_on {k_on} {DEC.get(decision)} p_trip {p_trip:.4f} "
                       f"infer {cyc[1]} cyc close->trip {cyc[2]} cyc\n")
        self.log.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=0, help="stop after this long (0 = until Ctrl-C)")
    a = ap.parse_args()
    d = Decoder(a.out)
    if a.file:
        with open(a.file, "rb") as f:
            d.feed(f.read())
    else:
        import serial
        ser = serial.Serial(a.port, 115200, timeout=0.2)     # CDC: the baud rate is irrelevant
        t0 = time.time()
        try:
            while not a.seconds or time.time() - t0 < a.seconds:
                data = ser.read(65536)
                if data:
                    d.feed(data)
        except KeyboardInterrupt:
            pass
    print(f"decoded {d.n_ok} records ({d.n_bad} bad frames) into {a.out}")


if __name__ == "__main__":
    main()
