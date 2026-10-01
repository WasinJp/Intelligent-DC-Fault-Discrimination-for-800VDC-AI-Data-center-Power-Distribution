/* fx_fft32.h — float32 real FFT of a fixed power-of-two length, CMSIS-DSP packed format:
 *   X[0] = Re(0), X[1] = Re(N/2), X[2k], X[2k+1] = Re(k), Im(k) for k = 1 .. N/2-1.
 * Two backends with the same contract: fx_fft32_cmsis.c (arm_rfft_fast_f32, N <= 4096) for the
 * target and fx_fft32_generic.c (own radix-2, any power of two) for the host and as a fallback.
 * The inverse is scaled by 1/N (as CMSIS does). */
#ifndef FX_FFT32_H
#define FX_FFT32_H

#ifndef FX_CAD32_FFT_N
#ifdef FX_FFT_CMSIS
#define FX_CAD32_FFT_N 4096          /* arm_rfft_fast_f32 maximum */
#else
#define FX_CAD32_FFT_N 8192
#endif
#endif

int  fx_fft32_init(void);                                 /* 0 ok */
void fx_fft32_rfft(float *x_inout, float *X);             /* x is destroyed (CMSIS behaviour) */
void fx_fft32_irfft(float *X_inout, float *x);            /* X is destroyed */
const char *fx_fft32_backend(void);

#endif /* FX_FFT32_H */
