#include "fx_filters.h"
#include "fx_filters_data.h"
#include <math.h>

const fx_sos_t *fx_sos_bandpass(int *n_sec) { *n_sec = FX_N_SOS_BP; return FX_SOS_BP; }
const fx_sos_t *fx_sos_antialias(int *n_sec) { *n_sec = FX_N_SOS_AA; return FX_SOS_AA; }

void fx_sos_zero(fx_sos_state_t *st, int n_sec)
{
    for (int s = 0; s < n_sec; ++s) { st[s].z1 = 0; st[s].z2 = 0; }
}

void fx_sos_run(const fx_sos_t *sec, int n_sec, fx_sos_state_t *st, const fx_iir_t *x, fx_iir_t *y, int n)
{
    for (int k = 0; k < n; ++k) y[k] = fx_sos_step(sec, n_sec, st, x[k]);
}

void fx_movavg(const double *x, int n, int win, double *y)
{
    if (win <= 1) {
        for (int k = 0; k < n; ++k) y[k] = x[k];
        return;
    }
    /* Python: c = cumsum(insert(x, 0, 0)); y = (c[win:] - c[:-win]) / win, then the first
     * win-1 outputs are y[0]. Here y[k] first holds c[k+1] (sequential cumsum), then is
     * replaced from the top down so no needed cumsum value is overwritten early. */
    double c = 0.0;
    for (int k = 0; k < n; ++k) { c += x[k]; y[k] = c; }
    for (int k = n - 1; k >= win - 1; --k) {
        double lo = (k - win >= 0) ? y[k - win] : 0.0;
        y[k] = (y[k] - lo) / (double)win;
    }
    int first = win - 1 < n ? win - 1 : n - 1;
    for (int k = 0; k < first; ++k) y[k] = y[first];
}

double fx_mean(const double *x, int n)
{
    double s = 0.0;
    for (int k = 0; k < n; ++k) s += x[k];
    return s / (double)n;
}

double fx_std(const double *x, int n)
{
    double m = fx_mean(x, n), s = 0.0;
    for (int k = 0; k < n; ++k) { double d = x[k] - m; s += d * d; }
    return sqrt(s / (double)n);
}

double fx_std_iir(const fx_iir_t *x, int n)
{
    double s = 0.0;
    for (int k = 0; k < n; ++k) s += (double)x[k];
    double m = s / (double)n;
    s = 0.0;
    for (int k = 0; k < n; ++k) { double d = (double)x[k] - m; s += d * d; }
    return sqrt(s / (double)n);
}

void fx_decim_init(fx_decim_t *d, int decim)
{
    d->decim = decim; d->count = 0; d->started = 0;
    fx_sos_zero(d->st, FX_N_SOS_AA);
}

int fx_decim_push(fx_decim_t *d, fx_iir_t x, fx_iir_t *y)
{
    if (!d->started) {                       /* zi = sosfilt_zi(sos) * x[0] */
        for (int s = 0; s < FX_N_SOS_AA; ++s) {
            d->st[s].z1 = (fx_iir_t)(FX_AA_ZI[s][0] * (double)x);
            d->st[s].z2 = (fx_iir_t)(FX_AA_ZI[s][1] * (double)x);
        }
        d->started = 1;
    }
    fx_iir_t out = fx_sos_step(FX_SOS_AA, FX_N_SOS_AA, d->st, x);
    int emit = (d->count == 0);
    d->count = (d->count + 1) % d->decim;
    if (emit) *y = out;
    return emit;
}
