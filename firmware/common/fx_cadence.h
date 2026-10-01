/* fx_cadence.h — slow-stream cadence learner and WORK features (FIRMWARE_SPEC.md §5, M5).
 *
 * Port of features._learn_cadence and its helpers (_cadence_candidates, _edges_two_level,
 * _tier2_from_segments) plus the phase_err fold at the end of features.extract. Arithmetic is
 * double; the FFT-based autocorrelation uses a radix-2 complex FFT on a power-of-two zero-padded
 * length (numpy uses rfft(2n)); both give the linear autocorrelation to rounding level.
 *
 * Host-side (M5 acceptance): the learner state below is ~4.5 MB and lives in a static object of
 * the CLI. The target version (float32 history, CMSIS-DSP FFT, 304 kB history, §5) is a later
 * step and must be re-validated against the same compare.py --work run. */
#ifndef FX_CADENCE_H
#define FX_CADENCE_H

#define FX_CADENCE_MAX_TIERS 2
#define FX_CAD_MAX_HIST      40000     /* 8 s of slow stream at 5 kSa/s */
#define FX_CAD_FFT_LOG2      17        /* 131072 >= 2 * FX_CAD_MAX_HIST */
#define FX_CAD_FFT_N         (1 << FX_CAD_FFT_LOG2)
#define FX_CAD_MAX_EDGES     4096

typedef struct {
    double T, strength;
    const double *edges; int n_edges;              /* rising-edge times (s), tier-1 rule */
    int is_tier2;                                  /* tier 2: current compute phase only */
    double phase_start;                            /* NaN when not in a compute phase */
    const double *edges_current; int n_current;    /* tier-2 edges in the current phase */
    double off2;                                   /* first-burst offset fallback (NaN if none) */
} fx_tier_t;

typedef struct {
    fx_tier_t tier[FX_CADENCE_MAX_TIERS];
    int n_tiers;
} fx_cadence_tiers_t;

/* learner state and working memory (no dynamic allocation) */
typedef struct {
    fx_cadence_tiers_t tiers;                      /* result of the last fx_cadence_learn */
    double e1[FX_CAD_MAX_EDGES], e2[FX_CAD_MAX_EDGES], e2cur[FX_CAD_MAX_EDGES];
    /* work */
    double t[FX_CAD_MAX_HIST], x[FX_CAD_MAX_HIST], xs[FX_CAD_MAX_HIST], xenv[FX_CAD_MAX_HIST];
    double seg[FX_CAD_MAX_HIST], tmp[FX_CAD_MAX_HIST], ac[FX_CAD_MAX_HIST], acc[FX_CAD_MAX_HIST];
    int cnt[FX_CAD_MAX_HIST];
    unsigned char state1[FX_CAD_MAX_HIST], st_tmp[FX_CAD_MAX_HIST];
    double re[FX_CAD_FFT_N], im[FX_CAD_FFT_N];
    int peaks[FX_CAD_MAX_HIST]; double heights[FX_CAD_MAX_HIST];
} fx_cadence_t;

/* Learn the cadence tiers from the slow current stream si[0..n) (float32 as stored / as decimated),
 * sampled at t_k = t0 + k / fs_slow, using the samples with t_k < t_end (Python: st < t_on - 0.5 ms).
 * W_s is the decision window (s). Returns the number of tiers (0, 1 or 2) and fills c->tiers. */
int fx_cadence_learn(fx_cadence_t *c, const float *si, int n, double t0, double fs_slow, double W_s, double t_end);

/* phase_err for an onset at t_on (s): distance to the nearest predicted rising edge of either
 * tier folded to [0, 0.5]; NaN when no tier gives a valid prediction. */
double fx_cadence_phase_err(const fx_cadence_tiers_t *t, double t_on);

/* has_period, period_strength, phase_err from published tiers (features.extract WORK block) */
void fx_cadence_work_features(const fx_cadence_tiers_t *t, double t_on,
                              double *has_period, double *period_strength, double *phase_err);

#endif /* FX_CADENCE_H */
