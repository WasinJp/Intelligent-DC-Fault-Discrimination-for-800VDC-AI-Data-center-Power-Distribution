/* fx_config.h — numeric contract of the sensing-node firmware (FIRMWARE_SPEC.md §3).
 *
 * Every sample count below is the value the Python reference computes at
 * fs = 500 kSa/s (int() truncation of a float product); tools/export_filters.py
 * re-derives them from the Python expressions and host/tests/test_units.c
 * asserts them at run time, so a silent drift is impossible.
 */
#ifndef FX_CONFIG_H
#define FX_CONFIG_H

#define FX_FS_FAST        500000.0   /* Sa/s, fast stream (product design; OPEN-12) */
#define FX_FS_SLOW        5000.0     /* Sa/s, slow stream (features.F_SLOW) */
#define FX_DECIM_SLOW     100        /* fast -> slow decimation ratio */

#define FX_N_PRE          75         /* max(int(0.15e-3*fs), 4): pre-window, 150 us */
#define FX_N_SM5          2          /* max(int(5e-6*fs), 1): onset detector / early-window smoothing */
#define FX_N_SM10         5          /* max(int(10e-6*fs), 1): decision-window smoothing */
#define FX_N_50US         25         /* max(int(50e-6*fs), 1): early window half-length */
#define FX_N_SKIP         30         /* min(int(60e-6*fs), N_PRE-3): spectral pre-window start */

#define FX_W_025          0.25e-3    /* decision windows, seconds (features.extract W) */
#define FX_W_050          0.5e-3
#define FX_W_100          1.0e-3
#define FX_N_W_025        125        /* max(int(W*fs), 4) for the three windows */
#define FX_N_W_050        250
#define FX_N_W_100        500
#define FX_W_DEFAULT      FX_W_025
#define FX_N_W_MAX        FX_N_W_100

#define FX_N_REC_PRE      100        /* record: 0.2 ms before onset ... */
#define FX_N_REC_POST     2500       /* ... to 5 ms after onset */
#define FX_N_REC          (FX_N_REC_PRE + FX_N_REC_POST)   /* 2600 samples per channel */
#define FX_N_REC_MAX      FX_N_REC   /* largest record the extractor accepts */

#define FX_N_FEATURES     15         /* studies.ALL, in that order */
#define FX_N_FEATURES_TWO 30         /* feeder + rack model (§7.3) */
#define FX_N_CLASSES      3          /* sklearn classes_ (sorted): ALERT, HOLD, TRIP */
#define FX_CLASS_ALERT    0
#define FX_CLASS_HOLD     1
#define FX_CLASS_TRIP     2

#define FX_N_SOS_BP       4          /* Butterworth 4, 1-100 kHz band-pass -> 4 biquads */
#define FX_N_SOS_AA       2          /* Butterworth 4, 2 kHz low-pass -> 2 biquads */

/* tail-mean length and spectral post-window offset as functions of the window (Python:
 * n_tail = max(int(0.1*nW), min(10, nW)); kh = k_on + int(0.3*nW)) */
static inline int fx_n_tail(int n_w)
{
    int a = (int)(0.1 * (double)n_w);
    int b = n_w < 10 ? n_w : 10;
    return a > b ? a : b;
}
static inline int fx_k_half(int n_w) { return (int)(0.3 * (double)n_w); }

#endif /* FX_CONFIG_H */
