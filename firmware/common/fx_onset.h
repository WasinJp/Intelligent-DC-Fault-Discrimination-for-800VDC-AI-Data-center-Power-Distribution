/* fx_onset.h — onset detector. Record mode (§4.1) is an exact port of features.detect_onset.
 * Stream mode (§4.2) runs on the live stream: the pre-window of candidate sample k is the 150 us
 * ending 50 us before k, [k-100, k-25), kept as running sums (DEVIATIONS.md #1). */
#ifndef FX_ONSET_H
#define FX_ONSET_H

#include "fx_config.h"

typedef struct {
    int k_on;            /* first sample after the pre-window that leaves the noise band (n_pre if none) */
    int found;
    double i_pre, v_pre; /* pre-window means of the raw streams */
    double sig_i, sig_v; /* std of the n_sm-smoothed pre-window + 1e-9 */
    double thr_i, thr_v; /* max(5*sig, 0.004*full scale) */
} fx_onset_t;

/* fi, fv: raw streams (physical units); si, sv: their n_sm-smoothed versions (fx_movavg);
 * n samples; n_pre pre-window; fs_i, fs_v: full scales of the record (physical units). */
void fx_onset_record(const double *fi, const double *fv, const double *si, const double *sv,
                     int n, int n_pre, double fs_i, double fs_v, fx_onset_t *o);

/* ---- stream mode (§4.2). Per sample k (k counted from the first pushed sample):
 *   si[k] = 5 us moving average of fi (n = FX_N_SM5), same for v;
 *   pre-window P(k) = [k - FX_STREAM_PRE_END - FX_N_PRE, k - FX_STREAM_PRE_END) = [k-100, k-25);
 *   i_pre = mean of fi over P(k); sig_i = std of si over P(k) + 1e-9 (one-pass running sums in
 *   double); thr_i = max(5 sig_i, 0.004 fs_i); fire at the first k >= 100 with
 *   |si[k] - i_pre| > thr_i or |sv[k] - v_pre| > thr_v.
 * After a fire the detector is inhibited for FX_STREAM_HOLDOFF samples (the record length, 5 ms)
 * and re-arms after FX_N_PRE consecutive quiet samples. The record is [k_on-100, k_on+2500) and
 * the features are computed on it in record mode (fx_features_extract), so only k_on can differ
 * from Python. Acceptance (host, fixtures): fx_cli stream / ctest m3_stream_vs_record. */
#define FX_STREAM_PRE_END   25                      /* pre-window ends 50 us before the candidate */
#define FX_STREAM_HIST      (FX_N_PRE + FX_STREAM_PRE_END + 1)   /* 101 samples of history */
#define FX_STREAM_HOLDOFF   FX_N_REC_POST

typedef struct {
    double fs_i, fs_v;
    /* Baseline freeze (variant of §4.2, see DEVIATIONS.md #1): when the smoothed sample departs
     * from the sliding baseline by more than freeze_factor * threshold the baseline stops sliding
     * (it stays the last quiet 150 us, like the fixed pre-window of record mode) until the signal
     * has been back inside that band for FX_N_PRE samples. freeze_factor = 0 disables the freeze
     * (pure sliding pre-window, the literal §4.2 text). */
    double freeze_factor;
    int frozen;
    double fz_i_pre, fz_v_pre, fz_sig_i, fz_sig_v, fz_thr_i, fz_thr_v;
    int fz_quiet;
    long fz_k;                /* sample at which the baseline was frozen: its window is [fz_k-100, fz_k-25) */
    long freeze_max;          /* a baseline older than this is refreshed (keeps the record <= FX_N_REC) */
    long rec_start;           /* at a fire: first sample of the record = start of the baseline window */
    double fi[FX_STREAM_HIST], fv[FX_STREAM_HIST];  /* raw history ring */
    double si[FX_STREAM_HIST], sv[FX_STREAM_HIST];  /* smoothed history ring */
    double sum_i, sum_v;                            /* raw sums over the pre-window */
    double ss_i, ss_v, qq_i, qq_v;                  /* smoothed sums and sums of squares */
    long k;                                         /* samples pushed so far */
    long holdoff;                                   /* > 0: inhibited */
    int quiet;                                      /* consecutive quiet samples while re-arming */
    int armed;
    fx_onset_t last;                                /* filled at the fire sample */
} fx_onset_stream_t;

#define FX_STREAM_FREEZE_DEFAULT 0.05               /* chosen on the fixtures, fx_cli stream (MILESTONES §M3) */
#define FX_STREAM_FREEZE_MAX     (FX_N_REC - FX_N_REC_PRE - FX_N_W_025)   /* 2375: record start .. window end <= 2600 */
void fx_onset_stream_init(fx_onset_stream_t *s, double fs_i, double fs_v);   /* freeze_factor = default */
/* push one dual sample (physical units); returns 1 at the sample that fires (k_on = s->k - 1
 * after the call, also in s->last.k_on), else 0 */
int  fx_onset_stream_push(fx_onset_stream_t *s, double fi, double fv);

#endif /* FX_ONSET_H */
