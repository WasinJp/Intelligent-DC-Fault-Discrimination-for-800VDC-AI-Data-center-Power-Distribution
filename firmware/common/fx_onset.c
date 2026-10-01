#include "fx_onset.h"
#include "fx_filters.h"
#include <math.h>

void fx_onset_record(const double *fi, const double *fv, const double *si, const double *sv,
                     int n, int n_pre, double fs_i, double fs_v, fx_onset_t *o)
{
    o->i_pre = fx_mean(fi, n_pre);
    o->v_pre = fx_mean(fv, n_pre);
    o->sig_i = fx_std(si, n_pre) + 1e-9;
    o->sig_v = fx_std(sv, n_pre) + 1e-9;
    double thr_i = 5.0 * o->sig_i, alt_i = 0.004 * fs_i;
    double thr_v = 5.0 * o->sig_v, alt_v = 0.004 * fs_v;
    o->thr_i = alt_i > thr_i ? alt_i : thr_i;    /* max(5*sig, 0.004*fs) */
    o->thr_v = alt_v > thr_v ? alt_v : thr_v;
    o->k_on = n_pre;
    o->found = 0;
    for (int k = n_pre; k < n; ++k) {
        if (fabs(si[k] - o->i_pre) > o->thr_i || fabs(sv[k] - o->v_pre) > o->thr_v) {
            o->k_on = k;
            o->found = 1;
            return;
        }
    }
}

/* ---------------------------------------------------------------- stream mode */
void fx_onset_stream_init(fx_onset_stream_t *s, double fs_i, double fs_v)
{
    for (int k = 0; k < FX_STREAM_HIST; ++k) { s->fi[k] = s->fv[k] = s->si[k] = s->sv[k] = 0.0; }
    s->fs_i = fs_i; s->fs_v = fs_v;
    s->sum_i = s->sum_v = s->ss_i = s->ss_v = s->qq_i = s->qq_v = 0.0;
    s->k = 0; s->holdoff = 0; s->quiet = 0; s->armed = 1;
    s->freeze_factor = FX_STREAM_FREEZE_DEFAULT; s->frozen = 0; s->fz_quiet = 0;
    s->fz_k = 0; s->freeze_max = FX_STREAM_FREEZE_MAX; s->rec_start = 0;
    s->last.k_on = -1; s->last.found = 0;
}

int fx_onset_stream_push(fx_onset_stream_t *s, double fi, double fv)
{
    const int H = FX_STREAM_HIST;
    const long k = s->k;
    const int idx = (int)(k % H);
    /* 5 us smoothing (n = 2): mean of this and the previous raw sample; Python's _movavg pads
     * the first sample with the first window mean, which the warm-up below never evaluates */
    const int prev = (idx + H - 1) % H;
    double si = (k > 0) ? (fi + s->fi[prev]) / 2.0 : fi;
    double sv = (k > 0) ? (fv + s->fv[prev]) / 2.0 : fv;
    s->fi[idx] = fi; s->fv[idx] = fv; s->si[idx] = si; s->sv[idx] = sv;

    /* On entry the sums hold P(k) = [k-100, k-25) = samples k-100 .. k-26 (75 samples); the first
     * evaluation, k = 100, therefore uses [0, 75), the record-mode pre-window of a record that
     * starts at the first pushed sample. */
    int fired = 0;
    if (k >= FX_N_PRE + FX_STREAM_PRE_END) {
        /* sums currently hold [k-100, k-25) (maintained at the end of the previous call) */
        double n = (double)FX_N_PRE;
        double i_pre = s->sum_i / n, v_pre = s->sum_v / n;
        double var_i = s->qq_i / n - (s->ss_i / n) * (s->ss_i / n);
        double var_v = s->qq_v / n - (s->ss_v / n) * (s->ss_v / n);
        double sig_i = sqrt(var_i > 0.0 ? var_i : 0.0) + 1e-9;
        double sig_v = sqrt(var_v > 0.0 ? var_v : 0.0) + 1e-9;
        double thr_i = 5.0 * sig_i, alt_i = 0.004 * s->fs_i; if (alt_i > thr_i) thr_i = alt_i;
        double thr_v = 5.0 * sig_v, alt_v = 0.004 * s->fs_v; if (alt_v > thr_v) thr_v = alt_v;
        if (s->freeze_factor > 0.0) {
            if (!s->frozen) {
                /* pre-trigger: the signal starts to leave the sliding baseline -> hold that baseline */
                if (fabs(si - i_pre) > s->freeze_factor * thr_i || fabs(sv - v_pre) > s->freeze_factor * thr_v) {
                    s->frozen = 1; s->fz_quiet = 0; s->fz_k = k;
                    s->fz_i_pre = i_pre; s->fz_v_pre = v_pre; s->fz_sig_i = sig_i; s->fz_sig_v = sig_v;
                    s->fz_thr_i = thr_i; s->fz_thr_v = thr_v;
                }
            }
            if (s->frozen) {
                i_pre = s->fz_i_pre; v_pre = s->fz_v_pre; sig_i = s->fz_sig_i; sig_v = s->fz_sig_v;
                thr_i = s->fz_thr_i; thr_v = s->fz_thr_v;
                int inside = fabs(si - i_pre) <= s->freeze_factor * thr_i && fabs(sv - v_pre) <= s->freeze_factor * thr_v;
                if (inside) { if (++s->fz_quiet >= FX_N_PRE) s->frozen = 0; }
                else s->fz_quiet = 0;
                if (k - s->fz_k > s->freeze_max) s->frozen = 0;    /* stale baseline: refresh */
            }
        }
        int hit = fabs(si - i_pre) > thr_i || fabs(sv - v_pre) > thr_v;
        if (s->holdoff > 0) {
            s->holdoff--;
        } else if (!s->armed) {
            if (hit) s->quiet = 0;
            else if (++s->quiet >= FX_N_PRE) s->armed = 1;
        } else if (hit) {
            s->last.k_on = (int)k; s->last.found = 1;
            s->last.i_pre = i_pre; s->last.v_pre = v_pre; s->last.sig_i = sig_i; s->last.sig_v = sig_v;
            s->last.thr_i = thr_i; s->last.thr_v = thr_v;
            s->holdoff = FX_STREAM_HOLDOFF; s->armed = 0; s->quiet = 0;
            /* the record starts where the baseline window starts, so record mode sees Python's layout:
             * a quiet 150 us, then the departure */
            s->rec_start = (s->frozen ? s->fz_k : k) - (FX_N_PRE + FX_STREAM_PRE_END);
            if (s->rec_start < 0) s->rec_start = 0;
            s->frozen = 0;
            fired = 1;
        }
    }
    /* slide to P(k+1) = [k-99, k-24) = samples k-99 .. k-25: add sample k-25, remove sample k-100 */
    long add = k - FX_STREAM_PRE_END, rem = add - FX_N_PRE;
    if (add >= 0) {
        int a = (int)(add % H);
        s->sum_i += s->fi[a]; s->sum_v += s->fv[a];
        s->ss_i += s->si[a]; s->ss_v += s->sv[a]; s->qq_i += s->si[a] * s->si[a]; s->qq_v += s->sv[a] * s->sv[a];
    }
    if (rem >= 0) {
        int r = (int)(rem % H);
        s->sum_i -= s->fi[r]; s->sum_v -= s->fv[r];
        s->ss_i -= s->si[r]; s->ss_v -= s->sv[r]; s->qq_i -= s->si[r] * s->si[r]; s->qq_v -= s->sv[r] * s->sv[r];
    }
    s->k = k + 1;
    return fired;
}
