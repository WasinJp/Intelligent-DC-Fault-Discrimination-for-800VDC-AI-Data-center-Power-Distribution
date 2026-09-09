"""dcsim.synth — sensor synthesis layer (MODEL.md §7).

Applied to pristine physics output, in order: anti-alias filter, decimation,
additive sensor noise, ADC quantization. Two observable streams are produced,
mirroring a protection relay's architecture:

  fast   2 MSa/s capture buffer over the fine window (event neighbourhood)
  slow   5 kSa/s supervisory log over the whole record (workload history; v1)

The classifier sees these two streams only — never hidden states or truth.
"""

import numpy as np
from scipy import signal
from .events import DT_FINE, DT_COARSE, WORKLOAD_VERSION

F_FAST = 2e6
F_SLOW = 5e3            # v1: 5 kSa/s supervisory log (was 50 kSa/s); 2 kHz anti-alias
DECIM_FAST = int(round(1.0 / (F_FAST * DT_FINE)))     # 10
SLOW_SRC_DT = 1.0 / (F_SLOW * 10)                      # 20 us grid feeding slow


def _aa_decimate(x, fs_in, decim, rng_state=None):
    """4th-order Butterworth at 0.4*fs_out (causal), then decimate."""
    fs_out = fs_in / decim
    sos = signal.butter(4, 0.4 * fs_out, fs=fs_in, output="sos")
    zi = signal.sosfilt_zi(sos) * x[0]
    y, _ = signal.sosfilt(sos, x, zi=zi)
    return y[::decim]


def _quantize(x, fs_range, bits):
    lsb = fs_range / (2 ** bits)
    return np.round(x / lsb) * lsb


def synthesize(ev, t, out, seed, f_fast=F_FAST, bits=None):
    """Produce observable streams from a simulate() result.

    f_fast, bits: acquisition front end for the fast stream (OPEN-12 sweep).
    Defaults reproduce the dataset stream exactly: 2 MSa/s, the event's drawn
    ADC bits, noise_frac at full rms. For other rates the anti-alias corner
    is 0.4*f_fast and the sensor noise rms scales with sqrt(f_fast / 2 MSa/s)
    -- same sensor, narrower front end (the rule §7 applies to the slow
    stream). Non-default configurations draw an independent noise stream.

    Returns dict:
      fast_t, fast_i, fast_v   (f_fast, fine window)
      slow_t, slow_i, slow_v   (5 kSa/s, whole record)
      fs_i, fs_v               full-scale ranges used for noise & quantization
      fs_fast, adc_bits        the front end actually used
    """
    p = ev["params"]
    sched = ev["sched"]
    i0, i1 = sched["idx_fine_start"], sched["idx_fine_end"]
    fs_i = 2.0 * p["I_lim"]
    fs_v = 1.25 * p["V_ref"]
    nf = p["noise_frac"]
    bits_f = p["adc_bits"] if bits is None else int(bits)
    default = (abs(f_fast - F_FAST) < 1.0) and (bits is None)
    rng = np.random.default_rng(seed + 7919 if default
                                else seed + 7919 + int(f_fast) // 1000 + 97 * bits_f)

    # ---- fast stream: fine window at 20 MSa/s -> f_fast
    decim = int(round(1.0 / (f_fast * DT_FINE)))
    nf_f = nf * np.sqrt(f_fast / F_FAST)
    i_f = _aa_decimate(out[1, i0:i1], 1.0 / DT_FINE, decim)
    v_f = _aa_decimate(out[2, i0:i1], 1.0 / DT_FINE, decim)
    t_f = t[i0:i1:decim][: i_f.shape[0]]
    i_f = _quantize(i_f + rng.standard_normal(i_f.shape[0]) * nf_f * fs_i, fs_i, bits_f)
    v_f = _quantize(v_f + rng.standard_normal(v_f.shape[0]) * nf_f * fs_v, fs_v, bits_f)
    if not default:
        # the slow stream must be identical across front-end configurations:
        # reproduce the default generator state by discarding the number of
        # normals the default fast path draws (i and v at 2 MSa/s).
        rng = np.random.default_rng(seed + 7919)
        n_def = _aa_decimate(out[1, i0:i1], 1.0 / DT_FINE, DECIM_FAST).shape[0]
        rng.standard_normal(2 * n_def)

    # ---- slow stream: resample whole record onto 2 us grid, then 50 kSa/s
    t_u = np.arange(0.0, t[-1], SLOW_SRC_DT)
    i_u = np.interp(t_u, t, out[1])
    v_u = np.interp(t_u, t, out[2])
    i_s = _aa_decimate(i_u, 1.0 / SLOW_SRC_DT, 10)
    v_s = _aa_decimate(v_u, 1.0 / SLOW_SRC_DT, 10)
    t_s = t_u[::10][: i_s.shape[0]]
    # v1: noise_frac is the sensor rms at the fast-stream bandwidth. The slow
    # stream is the same sensor averaged down, so its rms scales with
    # sqrt(F_SLOW / F_FAST). (v0.2 added full rms at 50 kSa/s -- kept for
    # exact reproduction of that dataset.)
    nf_s = nf if WORKLOAD_VERSION == "v0.2" else nf * np.sqrt(F_SLOW / F_FAST)
    i_s = _quantize(i_s + rng.standard_normal(i_s.shape[0]) * nf_s * fs_i, fs_i, p["adc_bits"])
    v_s = _quantize(v_s + rng.standard_normal(v_s.shape[0]) * nf_s * fs_v, fs_v, p["adc_bits"])

    return dict(fast_t=t_f.astype(np.float64), fast_i=i_f.astype(np.float32),
                fast_v=v_f.astype(np.float32),
                slow_t=t_s.astype(np.float64), slow_i=i_s.astype(np.float32),
                slow_v=v_s.astype(np.float32),
                fs_i=fs_i, fs_v=fs_v, t_event=ev["t_event"],
                fs_fast=float(f_fast), adc_bits=bits_f)
