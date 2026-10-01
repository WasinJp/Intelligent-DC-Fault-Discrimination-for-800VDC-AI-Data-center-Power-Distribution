"""bench_run.py — scripts the SCALING_SHEET.md §6 test plan on the bench (FIRMWARE_SPEC.md §10, M7):
200 benign workload events and 80 faults, every run recorded by both nodes and logged here.

  python firmware/tools/bench_run.py --bench COM5 --feeder COM6 --rack COM7 --out data/bench_runs/run1
         [--benign 200] [--faults 80] [--seed 1] [--dry-run]

Safety: the script never bypasses the hardware arm key switch. Before every fault command it asks the
bench control for `status`, reads `armed`, and refuses to send the fault if the key is off; the
bench_control firmware refuses as well (fault.c) and the 74HC123 one-shots bound every pulse in
hardware. Record upload: run tools/record_decoder.py on each node's USB CDC port in parallel.

Plan (pre-registered in SCALING_SHEET §6):
  benign: steps of 10-80 % of rating (ramps 0.5-20 ms), idle drops, two-tier cadence T1 0.3-3 s.
  faults: 60 rack-side = 20 each at 63 mOhm / 0.33 Ohm / 1.3 Ohm with L 10 / 30 / 100 uH rotated,
          20 feeder-side high-Z (22 Ohm, 39 Ohm), scheduled or unscheduled relative to the cadence."""
import argparse
import csv
import os
import random
import sys
import time


class Port:
    def __init__(self, name, dry):
        self.name, self.dry = name, dry
        self.ser = None
        if not dry:
            import serial
            self.ser = serial.Serial(name, 921600, timeout=2)
            time.sleep(0.2)
            self.ser.reset_input_buffer()

    def cmd(self, line, wait=0.1):
        if self.dry:
            print(f"[{self.name}] > {line}")
            return ["(dry)"]
        self.ser.write((line + "\n").encode())
        time.sleep(wait)
        out = []
        while True:
            l = self.ser.readline()
            if not l:
                break
            out.append(l.decode(errors="replace").strip())
        return out


def armed(bench):
    st = bench.cmd("status")
    for l in st:
        if "armed 1" in l:
            return True
        if "armed 0" in l:
            return False
    return bench.dry   # dry run: pretend armed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--feeder", required=True)
    ap.add_argument("--rack", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--benign", type=int, default=200)
    ap.add_argument("--faults", type=int, default=80)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = random.Random(a.seed)
    bench, feeder, rack = Port(a.bench, a.dry_run), Port(a.feeder, a.dry_run), Port(a.rack, a.dry_run)
    log = csv.writer(open(os.path.join(a.out, "run_log.csv"), "w", newline=""))
    log.writerow(["time", "run", "kind", "command", "bench_status", "feeder_status", "rack_status"])

    def record(run, kind, command):
        time.sleep(0.6)                      # the nodes decide within 0.35 ms and upload at +5 ms; give the USB a moment
        fs = " | ".join(feeder.cmd("status"))
        rs = " | ".join(rack.cmd("status"))
        bs = " | ".join(bench.cmd("status"))
        log.writerow([time.strftime("%H:%M:%S"), run, kind, command, bs, fs, rs])
        print(f"run {run:3d} {kind:8s} {command}")

    # ---- benign events: a profile with randomised cadence, plus explicit steps and idle drops
    bench.cmd("profile stop")
    feeder.cmd("arm"); rack.cmd("arm")
    for i in range(a.benign):
        kind = rng.choice(["step", "step", "idle", "cadence"])
        if kind == "step":
            frac = rng.uniform(0.1, 0.8); ramp = rng.uniform(0.5, 20.0)
            cmd = f"profile step {frac:.3f} {ramp:.2f}"
            bench.cmd(cmd); record(i, "benign", cmd)
        elif kind == "idle":
            cmd = "profile step 0 1.0"
            bench.cmd(cmd); record(i, "benign", cmd)
            bench.cmd(f"profile step {rng.uniform(0.2, 0.6):.3f} 1.0")
        else:
            T1 = rng.uniform(0.3, 3.0)
            bench.cmd(f"profile set T1 {T1:.3f}"); bench.cmd(f"profile set duty {rng.uniform(0.4, 0.7):.2f}")
            bench.cmd(f"profile set T2 {rng.uniform(0.02, 0.2):.3f}"); bench.cmd(f"profile set seed {rng.randrange(1, 2**31)}")
            bench.cmd("profile start")
            time.sleep(min(3 * T1, 8.0))      # let the nodes learn the cadence, then one scheduled edge
            record(i, "benign", f"cadence T1 {T1:.3f}")
            bench.cmd("profile stop")
        feeder.cmd("arm"); rack.cmd("arm")

    # ---- faults
    rack_plan = [(r, l) for r in range(3) for l in range(3)]
    n_rack = int(round(a.faults * 0.75)); n_feeder = a.faults - n_rack
    for i in range(n_rack):
        r_sel, l_sel = rack_plan[i % len(rack_plan)]
        scheduled = rng.random() < 0.5
        if not armed(bench):
            print("arm key switch is OFF: fault skipped (turn the key, then rerun from this index)"); log.writerow([time.strftime("%H:%M:%S"), i, "fault", "SKIPPED unarmed", "", "", ""]); continue
        if scheduled:
            bench.cmd(f"profile set T1 {rng.uniform(0.3, 3.0):.3f}"); bench.cmd("profile start"); time.sleep(2.0)
            cmd = f"fault rack {r_sel} {l_sel} edge {rng.randrange(-2000, 2000)}"
        else:
            cmd = f"fault rack {r_sel} {l_sel} now"
        bench.cmd(cmd, wait=0.3); record(a.benign + i, "fault_rack", cmd)
        bench.cmd("profile stop"); feeder.cmd("arm"); rack.cmd("arm")
        time.sleep(2.0)                        # resistor cooling between pulses
    for i in range(n_feeder):
        r_sel = i % 2
        if not armed(bench):
            print("arm key switch is OFF: fault skipped"); continue
        cmd = f"fault feeder {r_sel} now"
        bench.cmd(cmd, wait=0.3); record(a.benign + n_rack + i, "fault_feeder", cmd)
        feeder.cmd("arm"); rack.cmd("arm")
        time.sleep(2.0)
    print("done:", os.path.join(a.out, "run_log.csv"))


if __name__ == "__main__":
    sys.exit(main())
