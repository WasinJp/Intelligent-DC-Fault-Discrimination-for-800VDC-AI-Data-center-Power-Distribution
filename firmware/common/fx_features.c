#include "fx_features.h"
#include <math.h>
#include <string.h>

const char *const fx_feature_names[FX_N_FEATURES] = {
    "di_end", "di_max", "didt_max",
    "t_rise", "dv_early", "di_early", "r_dyn", "v_sag_end", "v_min", "collapse", "spec_i", "spec_v",
    "has_period", "period_strength", "phase_err"
};

static int imin(int a, int b) { return a < b ? a : b; }
static int imax(int a, int b) { return a > b ? a : b; }

int fx_features_extract(const fx_stream_t *s, double W_s, double I_rated, double V_ref,
                        fx_work_t *w, fx_features_t *f)
{
    const double *fi = s->fi, *fv = s->fv;
    const int n = s->n;
    const double fs = s->fs;
    const int n_pre = FX_N_PRE, n5 = FX_N_SM5, n10 = FX_N_SM10;

    if (n < n_pre + 4 || n > FX_N_REC_MAX) return -1;
    memset(f, 0, sizeof *f);

    /* ---- onset (record mode): 5 us-smoothed streams over the whole record */
    fx_movavg(fi, n, n5, w->si);
    fx_movavg(fv, n, n5, w->sv);
    fx_onset_record(fi, fv, w->si, w->sv, n, n_pre, s->fs_i, s->fs_v, &f->onset);
    const int k_on = f->onset.k_on;
    const double i_pre = f->onset.i_pre, v_pre = f->onset.v_pre;

    /* ---- decision window [k_on, k1) with 10 us smoothing */
    int nW = (int)(W_s * fs);
    if (nW < 4) nW = 4;
    if (nW > FX_N_W_MAX) return -2;
    f->n_w = nW;
    const int k1 = imin(k_on + nW, n);
    const int nw = k1 - k_on;
    if (nw < n10) return -3;                    /* Python's _movavg would fail here too */
    fx_movavg(fi + k_on, nw, n10, w->smi);
    fx_movavg(fv + k_on, nw, n10, w->smv);
    const double *smi = w->smi, *smv = w->smv;

    /* ---- CONV */
    const int n_tail = fx_n_tail(nW);
    const int t0 = imax(nw - n_tail, 0);        /* smi[-n_tail:] */
    const double di_end = fx_mean(smi + t0, nw - t0) - i_pre;
    f->di_end = di_end / I_rated;
    double amax = 0.0;
    for (int k = 0; k < nw; ++k) { double a = fabs(smi[k] - i_pre); if (a > amax) amax = a; }
    f->di_max = amax / I_rated;
    if (nw > 1) {
        double dmax = 0.0;
        for (int k = 0; k + 1 < nw; ++k) {
            double d = fabs((smi[k + 1] - smi[k]) * fs * 1e-6);   /* A/us */
            if (d > dmax) dmax = d;
        }
        f->didt_max = dmax / I_rated;
    } else {
        f->didt_max = 0.0;
    }

    /* ---- PHYS */
    const double tgt = fabs(di_end);
    if (tgt > 3.0 * f->onset.sig_i) {
        int k10 = 0, k90 = 0, f10 = 0, f90 = 0;   /* np.argmax of a boolean: first True, else 0 */
        for (int k = 0; k < nw; ++k) {
            double a = fabs(smi[k] - i_pre);
            if (!f10 && a >= 0.1 * tgt) { k10 = k; f10 = 1; }
            if (!f90 && a >= 0.9 * tgt) { k90 = k; f90 = 1; }
            if (f10 && f90) break;
        }
        f->t_rise = (double)imax(k90 - k10, 1) / fs * 1e3;     /* ms */
    } else {
        f->t_rise = W_s * 1e3;
    }
    const int n50 = FX_N_50US;
    const int e0 = imax(k_on - n50, 0), e1 = imin(k_on + n50, n);
    double vmin_e = w->sv[e0];
    for (int k = e0 + 1; k < e1; ++k) if (w->sv[k] < vmin_e) vmin_e = w->sv[k];
    f->dv_early = (v_pre - vmin_e) / V_ref;
    f->di_early = fabs(w->si[e1 - 1] - i_pre) / I_rated;
    const double v_end = fx_mean(smv + t0, nw - t0);
    f->v_sag_end = (v_pre - v_end) / V_ref;
    double smv_min = smv[0];
    for (int k = 1; k < nw; ++k) if (smv[k] < smv_min) smv_min = smv[k];
    f->v_min = smv_min / v_pre;
    f->r_dyn = ((v_pre - v_end) / V_ref) / (fabs(di_end) / I_rated + 1e-3);
    f->collapse = (smv_min < 0.8 * v_pre) ? 1.0 : 0.0;

    /* ---- spectral noise floor 1-100 kHz: causal band-pass from record start, zero state,
     *      on the mean-removed streams (v0.2.1 B3) */
    int n_sec;
    const fx_sos_t *bp = fx_sos_bandpass(&n_sec);
    fx_sos_state_t st[FX_N_SOS_BP];
    fx_sos_zero(st, n_sec);
    for (int k = 0; k < n; ++k) w->bp_i[k] = fx_sos_step(bp, n_sec, st, (fx_iir_t)(fi[k] - i_pre));
    fx_sos_zero(st, n_sec);
    for (int k = 0; k < n; ++k) w->bp_v[k] = fx_sos_step(bp, n_sec, st, (fx_iir_t)(fv[k] - v_pre));
    const int n_skip = FX_N_SKIP;
    const double pre_i = fx_std_iir(w->bp_i + n_skip, n_pre - n_skip) + 1e-9;
    const double pre_v = fx_std_iir(w->bp_v + n_skip, n_pre - n_skip) + 1e-9;
    const int kh = imin(k_on + fx_k_half(nW), n - 4);
    if (k1 > kh + 1) {
        f->spec_i = log10(fx_std_iir(w->bp_i + kh, k1 - kh) / pre_i + 1e-9);
        f->spec_v = log10(fx_std_iir(w->bp_v + kh, k1 - kh) / pre_v + 1e-9);
    } else {
        f->spec_i = 0.0;
        f->spec_v = 0.0;
    }

    /* ---- WORK: no cadence published (M5) */
    f->has_period = 0.0;
    f->period_strength = 0.0;
    f->phase_err = NAN;
    return 0;
}

void fx_features_vector(const fx_features_t *f, double x[FX_N_FEATURES])
{
    x[0] = f->di_end;   x[1] = f->di_max;    x[2] = f->didt_max;
    x[3] = f->t_rise;   x[4] = f->dv_early;  x[5] = f->di_early;  x[6] = f->r_dyn;
    x[7] = f->v_sag_end; x[8] = f->v_min;    x[9] = f->collapse;  x[10] = f->spec_i; x[11] = f->spec_v;
    x[12] = f->has_period; x[13] = f->period_strength; x[14] = f->phase_err;
}
