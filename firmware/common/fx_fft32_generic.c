/* fx_fft32_generic.c — portable float32 real FFT (radix-2 complex FFT of N points with zero
 * imaginary part, twiddles from a double recurrence), CMSIS packed output. */
#include "fx_fft32.h"
#include <math.h>

#define N FX_CAD32_FFT_N
static float g_re[N], g_im[N];

int fx_fft32_init(void) { return 0; }
const char *fx_fft32_backend(void) { return "generic-radix2"; }

static void cfft(float *re, float *im, int inverse)
{
    for (int i = 1, j = 0; i < N; ++i) {
        int bit = N >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (int len = 2; len <= N; len <<= 1) {
        double ang = 2.0 * 3.14159265358979323846 / (double)len * (inverse ? 1.0 : -1.0);
        double wr = cos(ang), wi = sin(ang);
        for (int i = 0; i < N; i += len) {
            double cr = 1.0, ci = 0.0;
            for (int j = 0; j < len / 2; ++j) {
                int a = i + j, b = i + j + len / 2;
                float fcr = (float)cr, fci = (float)ci;
                float vr = re[b] * fcr - im[b] * fci, vi = re[b] * fci + im[b] * fcr;
                float ur = re[a], ui = im[a];
                re[a] = ur + vr; im[a] = ui + vi;
                re[b] = ur - vr; im[b] = ui - vi;
                double ncr = cr * wr - ci * wi;
                ci = cr * wi + ci * wr;
                cr = ncr;
            }
        }
    }
}

void fx_fft32_rfft(float *x, float *X)
{
    for (int i = 0; i < N; ++i) { g_re[i] = x[i]; g_im[i] = 0.0f; }
    cfft(g_re, g_im, 0);
    X[0] = g_re[0];
    X[1] = g_re[N / 2];
    for (int k = 1; k < N / 2; ++k) { X[2 * k] = g_re[k]; X[2 * k + 1] = g_im[k]; }
}

void fx_fft32_irfft(float *X, float *x)
{
    g_re[0] = X[0]; g_im[0] = 0.0f;
    g_re[N / 2] = X[1]; g_im[N / 2] = 0.0f;
    for (int k = 1; k < N / 2; ++k) {
        g_re[k] = X[2 * k]; g_im[k] = X[2 * k + 1];
        g_re[N - k] = X[2 * k]; g_im[N - k] = -X[2 * k + 1];      /* Hermitian symmetry */
    }
    cfft(g_re, g_im, 1);
    float s = 1.0f / (float)N;
    for (int i = 0; i < N; ++i) x[i] = g_re[i] * s;
}
