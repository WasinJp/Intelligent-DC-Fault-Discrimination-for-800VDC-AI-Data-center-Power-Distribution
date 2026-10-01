/* fx_filters.h — causal SOS IIR (scipy.signal.sosfilt structure), the Python _movavg,
 * numpy-style mean/std, and the slow-stream anti-alias decimator (synth._aa_decimate). */
#ifndef FX_FILTERS_H
#define FX_FILTERS_H

#include <stdint.h>
#include "fx_config.h"

/* IIR arithmetic type. Default double: with double state and coefficients the cascade is
 * bit-identical to scipy.sosfilt (host test), and the Cortex-M7 FPU (fpv5-d16) has hardware
 * double. float32 (define FX_IIR_FLOAT) misses the §6.2 tolerance on spec_i/spec_v by up to
 * 4x on the quietest records; see docs/DEVIATIONS.md #2. */
#ifdef FX_IIR_FLOAT
typedef float fx_iir_t;
#else
typedef double fx_iir_t;
#endif

/* one second-order section, a0 normalised to 1 (scipy butter(..., output="sos")) */
typedef struct { fx_iir_t b0, b1, b2, a1, a2; } fx_sos_t;
typedef struct { fx_iir_t z1, z2; } fx_sos_state_t;

/* One sample through a cascade, direct form II transposed, exactly the update order of
 * scipy's _sosfilt (x_new = b0*x + z1; z1 = b1*x - a1*x_new + z2; z2 = b2*x - a2*x_new). */
static inline fx_iir_t fx_sos_step(const fx_sos_t *sec, int n_sec, fx_sos_state_t *st, fx_iir_t x)
{
    for (int s = 0; s < n_sec; ++s) {
        fx_iir_t y = sec[s].b0 * x + st[s].z1;
        st[s].z1 = sec[s].b1 * x - sec[s].a1 * y + st[s].z2;
        st[s].z2 = sec[s].b2 * x - sec[s].a2 * y;
        x = y;
    }
    return x;
}

const fx_sos_t *fx_sos_bandpass(int *n_sec);       /* 1-100 kHz at fs = 500 kSa/s */
const fx_sos_t *fx_sos_antialias(int *n_sec);      /* 2 kHz low-pass at fs = 500 kSa/s */
void fx_sos_zero(fx_sos_state_t *st, int n_sec);
void fx_sos_run(const fx_sos_t *sec, int n_sec, fx_sos_state_t *st, const fx_iir_t *x, fx_iir_t *y, int n);

/* features._movavg: cumulative-sum moving average of length win; outputs 0..win-2 are
 * set to output win-1. y may not alias x. Bit-compatible with the numpy expression. */
void fx_movavg(const double *x, int n, int win, double *y);
double fx_mean(const double *x, int n);
double fx_std(const double *x, int n);          /* population std (ddof = 0), two-pass */
double fx_std_iir(const fx_iir_t *x, int n);    /* same on filter outputs */

/* synth._aa_decimate(x, fs_in, decim): Butterworth-4 low-pass at 0.4*fs_out, initial state
 * sosfilt_zi * x[0], keep every decim-th output starting with the first. */
typedef struct {
    fx_sos_state_t st[FX_N_SOS_AA];
    int decim, count, started;
} fx_decim_t;
void fx_decim_init(fx_decim_t *d, int decim);
int  fx_decim_push(fx_decim_t *d, fx_iir_t x, fx_iir_t *y);   /* 1 when *y holds an output */

#endif /* FX_FILTERS_H */
