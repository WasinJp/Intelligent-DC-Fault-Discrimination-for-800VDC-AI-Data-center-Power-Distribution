"""Bench scaling: map MODEL.md (PARAMS_BASELINE and the sweep ranges) to a low-voltage testbed.
Usage: python hardware/bench_scaling.py [P_bench_W] [V_feeder] [V_rack]      default 120 48 12

Rule (SCALING_SHEET.md §1): TIME IS NOT SCALED. Every time constant, delay, period, ramp and the
sampling stay physical. Voltages and currents scale by V_b/V_m and I_b/I_m; impedances by
Z_b/Z_m = (V_b/I_b)/(V_m/I_m); capacitances so that stored energy / rated power is preserved."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dcsim.model_v04 import PARAMS_BASELINE as m
Pb = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
Vf = float(sys.argv[2]) if len(sys.argv) > 2 else 48.0
Vr = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0
Pm, Vm, Vm48 = m["P_rated"], m["V_ref"], m["V_ref48"]
Im, Im48 = Pm / Vm, Pm / Vm48
If_, Ir = Pb / Vf, Pb / Vr
zf = (Vf / If_) / (Vm / Im); zr = (Vr / Ir) / (Vm48 / Im48)          # impedance scale, feeder side / rack side
cf = (Pb / Pm) * (Vm / Vf) ** 2; cr = (Pb / Pm) * (Vm48 / Vr) ** 2   # capacitance scale
vf, vr = Vf / Vm, Vr / Vm48
print(f"bench: P_rated {Pb:g} W | feeder {Vf:g} V, {If_:.2f} A rated | rack bus {Vr:g} V, {Ir:.2f} A rated")
print(f"scales: feeder Z x{zf:.3f}, C x{cf:.4f} | rack Z x{zr:.2f}, C x{cr:.5f}\n")
rows = [
 ("FEEDER SIDE ('800 V' bus at %g V)" % Vf, None, None, None, None),
 ("source droop R_droop", m["R_droop"], m["R_droop"] * zf, "ohm", "lab supply output impedance; measure, then set in simulator"),
 ("source tau_c", m["tau_c"], m["tau_c"], "s", "supply loop; measure step response"),
 ("source current limit I_lim", m["I_lim"], m["I_lim"] / Im * If_, "A", "supply limit set to this (1.75 x rated)"),
 ("L_line", m["L_line"], m["L_line"] * zf, "H", "sweep 1-50 uH -> %.0f-%.0f uH" % (1e-6 * zf * 1e6, 50e-6 * zf * 1e6)),
 ("R_line", m["R_line"], m["R_line"] * zf, "ohm", "sweep 1-20 mohm -> %.0f-%.0f mohm" % (1e-3 * zf * 1e3, 20e-3 * zf * 1e3)),
 ("C_bus", m["C_bus"], m["C_bus"] * cf, "F", "sweep 0.1-2 mF -> %.0f-%.0f uF" % (0.1e-3 * cf * 1e6, 2e-3 * cf * 1e6)),
 ("R_esr (bus cap)", m["R_esr"], m["R_esr"] * zf, "ohm", ""),
 ("800 V fault R_f (high-Z, 5 ohm)", m["R_f"] if False else 5.0, 5.0 * zf, "ohm", "sweep 1-10 ohm -> %.1f-%.1f ohm; extra %.1f A from the supply at the low end" % (1 * zf, 10 * zf, Vf / (1 * zf))),
 ("800 V fault L_f", m["L_f"], m["L_f"] * zf, "H", "sweep 0.5-10 uH -> %.1f-%.0f uH" % (0.5e-6 * zf * 1e6, 10e-6 * zf * 1e6)),
 ("RACK INPUT FILTER", None, None, None, None),
 ("L_in", m["L_in"], m["L_in"] * zf, "H", "sweep 1-20 uH -> %.0f-%.0f uH" % (1e-6 * zf * 1e6, 20e-6 * zf * 1e6)),
 ("R_in", m["R_in"], m["R_in"] * zf, "ohm", ""),
 ("C_in", m["C_in"], m["C_in"] * cf, "F", "sweep 0.1-5 mF -> %.0f-%.0f uF" % (0.1e-3 * cf * 1e6, 5e-3 * cf * 1e6)),
 ("R_in_esr", m["R_in_esr"], m["R_in_esr"] * zf, "ohm", ""),
 ("CONVERTER (time constants unchanged)", None, None, None, None),
 ("V_ref48 -> V_rack", Vm48, Vr, "V", ""),
 ("I_lim_out", m["I_lim_out"], m["I_lim_out"] / Im48 * Ir, "A", "1.4 x rated; sweep 1.2-1.6 x"),
 ("tau_i (inner current loop)", m["tau_i"], m["tau_i"], "s", "sweep 10-50 us; measure on the built converter"),
 ("f_v (voltage loop)", m["f_v"], m["f_v"], "Hz", "sweep 20-2000 Hz; a fast commercial loop is allowed, measure it"),
 ("tau_r, S_max (ramp limiter)", "%g, %.0e" % (m["tau_r"], m["S_max"]), "off", "", "smoothing OFF on the bench (not implementable in a plain buck); dataset flag smooth_on = 0"),
 ("efficiency model p_fix, k2", "%.4f, %.4f" % (m["p_fix"], m["k2"]), "measure", "", "fit from efficiency at 20 / 50 / 100 % load"),
 ("RACK SIDE ('48 V' bus at %g V)" % Vr, None, None, None, None),
 ("C_out (storage bank)", m["C_out"], m["C_out"] * cr, "F", "sweep 0.2-5 F -> %.0f-%.0f mF; energy/P = %.0f ms" % (0.2 * cr * 1e3, 5 * cr * 1e3, 0.5 * m["C_out"] * Vm48**2 / Pm * 1e3)),
 ("R_out_esr", m["R_out_esr"], m["R_out_esr"] * zr, "ohm", "sweep 0.2-2 mohm -> %.0f-%.0f mohm (the v_out ESR step is a feature)" % (0.2e-3 * zr * 1e3, 2e-3 * zr * 1e3)),
 ("48 V fault R_f48 bolted (1 mohm)", 1e-3, 1e-3 * zr, "ohm", "sweep 0.5-5 mohm -> %.0f-%.0f mohm" % (0.5e-3 * zr * 1e3, 5e-3 * zr * 1e3)),
 ("48 V fault R_f48 high-Z (20 mohm)", 20e-3, 20e-3 * zr, "ohm", "sweep 5-100 mohm -> %.2f-%.1f ohm" % (5e-3 * zr, 100e-3 * zr)),
 ("48 V fault L_f48", m["L_f48"], m["L_f48"] * zr, "H", "sweep 0.1-2 uH -> %.1f-%.0f uH: ADD a coil, bench wiring (~0.5 uH) is BELOW this range" % (0.1e-6 * zr * 1e6, 2e-6 * zr * 1e6)),
 ("POL UVLO V_uvlo48 / hysteresis", "%g / %g" % (m["V_uvlo48"], m["V_hyst48"]), "%.2f / %.2f" % (m["V_uvlo48"] * vr, m["V_hyst48"] * vr), "V", "load-control MCU: trip after t_uvlo48 = %g us below" % (m["t_uvlo48"] * 1e6)),
 ("rated rack current", Im48, Ir, "A", ""),
]
print(f"{'quantity':40s} {'model':>14s} {'bench':>14s} {'unit':5s} note")
for name, a, b, u, note in rows:
    if a is None: print(f"\n-- {name}"); continue
    fa = a if isinstance(a, str) else (f"{a:.4g}"); fb = b if isinstance(b, str) else (f"{b:.4g}")
    print(f"{name:40s} {fa:>14s} {fb:>14s} {u:5s} {note}")
# derived: currents the bench must survive, and the sensing chain
Resr = m["R_out_esr"] * zr; Rb = 1e-3 * zr
Ipk = Vr / (Rb + Resr + 0.010)      # + 10 mohm wiring + switch, model L ignored (worst case)
print(f"\nDERIVED\nbolted 48 V fault on the bench: R_f48 {Rb*1e3:.0f} mohm + ESR {Resr*1e3:.0f} mohm + 10 mohm wiring -> peak about {Ipk:.0f} A = {Ipk/Ir:.1f} x rated (model bolted_48 peaks at 12.5 x)")
print(f"  energy in the fault resistor for a 5 ms pulse: <= {Ipk**2*Rb*5e-3:.0f} J; I2t <= {Ipk**2*5e-3:.0f} A2s -> hardware one-shot limits the pulse to 5 ms")
print(f"storage bank energy: {0.5*m['C_out']*cr*Vr**2:.1f} J (model {0.5*m['C_out']*Vm48**2/1e3:.1f} kJ)")
print(f"feeder current: benign up to {If_:.2f} A; an 800 V-side fault is CAPPED by the source limit at {m['I_lim']/Im*If_:.2f} A (model: limit reached in high_z). Supply in constant-current mode at that value; it must hold CC, not shut down; its CC transition time replaces tau_c in the simulator")
print(f"\nSENSING (16-bit ADC, 3.3 V full scale, 500 kSa/s)")
for node, I, fs_pu, shunt in (("rack", Ir, 13.0, None), ("feeder", If_, 2.0, None)):
    for R in (0.5e-3, 1e-3, 2e-3, 5e-3, 10e-3):
        for G in (20, 50, 100):
            vfs = R * I * fs_pu * G
            if 2.4 <= vfs <= 3.2:
                print(f"  {node:6s} shunt {R*1e3:4.1f} mohm, gain {G:3d}: rated {R*I*G*1e3:6.1f} mV = {R*I*G/3.3*65536:5.0f} LSB, full scale {fs_pu:.0f} x rated at {vfs:.2f} V, shunt dissipation at rated {R*I*I*1e3:.0f} mW")
