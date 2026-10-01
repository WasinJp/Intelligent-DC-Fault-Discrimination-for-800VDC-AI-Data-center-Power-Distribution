/* fx_fft32_cmsis.c — CMSIS-DSP backend: arm_rfft_fast_f32 (packed format, inverse scaled 1/N). */
#include "fx_fft32.h"
#include "arm_math.h"

static arm_rfft_fast_instance_f32 g_inst;
static int g_ok;

int fx_fft32_init(void)
{
    g_ok = (arm_rfft_fast_init_f32(&g_inst, FX_CAD32_FFT_N) == ARM_MATH_SUCCESS);
    return g_ok ? 0 : -1;
}
const char *fx_fft32_backend(void) { return "cmsis-dsp"; }

void fx_fft32_rfft(float *x, float *X) { arm_rfft_fast_f32(&g_inst, x, X, 0); }
void fx_fft32_irfft(float *X, float *x) { arm_rfft_fast_f32(&g_inst, X, x, 1); }
