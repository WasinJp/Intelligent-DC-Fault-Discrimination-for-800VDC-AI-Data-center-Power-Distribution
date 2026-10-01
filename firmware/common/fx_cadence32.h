/* fx_cadence32.h — target version of the cadence learner (FIRMWARE_SPEC.md §5, M5 on the node).
 *
 * Same algorithm as fx_cadence.c (features._learn_cadence), re-expressed for the STM32H743's memory:
 *   - history: FX_CAD32_H float32 current samples at 5 kSa/s (152 kB) in a ring; the voltage
 *     history is not kept (no feature uses it; DEVIATIONS.md #12);
 *   - no double copies of the history: the smoothed series are computed on the fly in double with
 *     a sliding sum; order statistics (percentiles, medians) through an exact two-step selection
 *     (sorted float32 shadow + tie resolution in double);
 *   - the autocorrelation as block cross-correlations with FX_CAD32_FFT_N-point real FFTs
 *     (fx_fft32: CMSIS-DSP on the target, generic radix-2 elsewhere), accumulated in float32.
 * Work buffers are bound by the owner (fx_cadence32_bind) so the node can place them in different
 * SRAM regions; FX_CAD32_* give their sizes. Published result: fx_cadence_tiers_t.
 * Host proof: fx_cli extract --cadence f32|cmsis against the Python reference (ctest m5_f32_*). */
#ifndef FX_CADENCE32_H
#define FX_CADENCE32_H

#include <stdint.h>
#include "fx_cadence.h"
#include "fx_fft32.h"

#define FX_CAD32_H        38000                 /* 7.6 s at 5 kSa/s */
#define FX_CAD32_K        17100                 /* max lag: int(0.45 * 7.6 s * 5 kSa/s) + margin */
#define FX_CAD32_NPEAKS   (FX_CAD32_K / 4)
#define FX_CAD32_EDGES    1024                  /* 8 kB per list; tier 1 <= 507 edges at T >= 15 ms */
#define FX_CAD32_NBOUNDS  1024
#define FX_CAD32_BLOCK    (FX_CAD32_FFT_N / 2)
#define FX_CAD32_STATE_BYTES ((FX_CAD32_H + 7) / 8)

typedef struct {
    float x[FX_CAD32_H];
    uint32_t count;          /* samples pushed since init (sample i has time t0 + i / fs) */
    double fs, t0;
} fx_hist32_t;

void fx_hist32_init(fx_hist32_t *h, double fs, double t0);
void fx_hist32_push(fx_hist32_t *h, float x);

typedef struct {
    fx_cadence_tiers_t tiers;
    /* bound buffers (sizes: see fx_cadence32_bind) */
    double *e1, *e2, *e2cur;                    /* FX_CAD32_EDGES each */
    float *shadow;                              /* FX_CAD32_H */
    float *ac, *acc;                            /* FX_CAD32_K each */
    uint8_t *cnt;                               /* FX_CAD32_K */
    uint8_t *state1;                            /* FX_CAD32_STATE_BYTES */
    float *fa, *fb, *fc;                        /* FX_CAD32_FFT_N each */
    int *peaks; float *heights;                 /* FX_CAD32_NPEAKS each */
    int *bounds;                                /* FX_CAD32_NBOUNDS */
    /* statistics of the last learn */
    uint32_t n_fft, n_select, n_used;
} fx_cadence32_t;

void fx_cadence32_bind(fx_cadence32_t *c, double *e1, double *e2, double *e2cur, float *shadow, float *ac, float *acc,
                       uint8_t *cnt, uint8_t *state1, float *fa, float *fb, float *fc, int *peaks, float *heights, int *bounds);

/* Learn from the samples of h with t < t_end (t_end = t_on - 0.5 ms), decision window W_s.
 * Returns the number of tiers (0..2); c->tiers is valid afterwards. */
int fx_cadence32_learn(fx_cadence32_t *c, const fx_hist32_t *h, double W_s, double t_end);

#endif /* FX_CADENCE32_H */
