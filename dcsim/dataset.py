"""dcsim.dataset — Monte Carlo event generation to HDF5 (MODEL.md §10).

A dataset is fully reproducible from (MODEL.md version, master seed).
Per-event seeds are derived from the master seed and the event index.
"""

import subprocess
import time
import h5py
import numpy as np
from .model import simulate, param_vector
from .events import draw_event, LABELS
from .synth import synthesize, F_FAST, F_SLOW, DECIM_FAST

MODEL_VERSION = "0.2"


def _git_hash():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def run_event(label, seed):
    ev = draw_event(label, seed)
    pv = param_vector(ev["params"])
    s = ev["sched"]
    t, out = simulate(pv, s["dt"], ev["P"], ev["Varc"], ev["fault_start"], ev["fault_end"])
    obs = synthesize(ev, t, out, seed)
    # truth on the fast grid (debug / figures only, never training)
    i0, i1 = s["idx_fine_start"], s["idx_fine_end"]
    nf = obs["fast_i"].shape[0]
    truth = dict(i_f=out[3, i0:i1:DECIM_FAST][:nf].astype(np.float32),
                 i_load=out[4, i0:i1:DECIM_FAST][:nf].astype(np.float32),
                 v_c=out[0, i0:i1:DECIM_FAST][:nf].astype(np.float32),
                 load_on=out[5, i0:i1:DECIM_FAST][:nf].astype(np.float32))
    return ev, obs, truth


def generate(path, master_seed=20260907, n_per_class=200, labels=LABELS, verbose=True):
    t_start = time.time()
    with h5py.File(path, "w") as h:
        g = h.create_group("session_meta")
        g.attrs["model_version"] = MODEL_VERSION
        g.attrs["master_seed"] = master_seed
        g.attrs["git_hash"] = _git_hash()
        g.attrs["generated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        g.attrs["f_fast"] = F_FAST
        g.attrs["f_slow"] = F_SLOW
        ge = h.create_group("events")
        idx = 0
        n_rej_total = 0
        for label in labels:
            for k in range(n_per_class):
                seed = master_seed * 1000 + idx
                ev, obs, truth = run_event(label, seed)
                n_rej_total += ev["n_rejected"]
                e = ge.create_group(f"{idx:05d}")
                e.attrs["label"] = label
                e.attrs["seed"] = seed
                e.attrs["background"] = ev["background"]
                e.attrs["composite"] = bool(ev["composite"])
                e.attrs["t_event"] = ev["t_event"]
                e.attrs["n_rejected"] = ev["n_rejected"]
                w = e.create_group("waveforms")
                w.create_dataset("fast_i", data=obs["fast_i"], compression="gzip")
                w.create_dataset("fast_v", data=obs["fast_v"], compression="gzip")
                w.create_dataset("slow_i", data=obs["slow_i"], compression="gzip")
                w.create_dataset("slow_v", data=obs["slow_v"], compression="gzip")
                w.attrs["fast_t0"] = obs["fast_t"][0]
                w.attrs["slow_t0"] = obs["slow_t"][0]
                w.attrs["fs_i"] = obs["fs_i"]
                w.attrs["fs_v"] = obs["fs_v"]
                tr = e.create_group("truth")
                for kk, vv in truth.items():
                    tr.create_dataset(kk, data=vv, compression="gzip")
                pr = e.create_group("params")
                for kk, vv in ev["params"].items():
                    pr.attrs[kk] = vv
                for kk in ("period", "dP_bg", "t_ramp_bg", "P0", "dP", "t_ramp",
                           "R_f", "L_f", "V_arc0", "m_arc", "f_arc_hi", "t_arc_on",
                           "arc_place"):
                    if kk in ev:
                        pr.attrs["ev_" + kk] = ev[kk]
                idx += 1
                if verbose and idx % 50 == 0:
                    print(f"  {idx:5d} events  {time.time() - t_start:6.0f} s", flush=True)
        g.attrs["n_events"] = idx
        g.attrs["n_rejected_draws"] = n_rej_total
    if verbose:
        print(f"wrote {idx} events to {path} in {time.time() - t_start:.0f} s "
              f"({n_rej_total} draws rejected by gate 1)")


def load_obs(e):
    """Rebuild the obs dict from an HDF5 event group."""
    w = e["waveforms"]
    fi = w["fast_i"][...]
    si = w["slow_i"][...]
    return dict(fast_i=fi, fast_v=w["fast_v"][...],
                fast_t=w.attrs["fast_t0"] + np.arange(fi.shape[0]) / F_FAST,
                slow_i=si, slow_v=w["slow_v"][...],
                slow_t=w.attrs["slow_t0"] + np.arange(si.shape[0]) / F_SLOW,
                fs_i=w.attrs["fs_i"], fs_v=w.attrs["fs_v"],
                t_event=e.attrs["t_event"])
