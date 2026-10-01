/* fx_features.h — CONV + PHYS features of features.extract (FIRMWARE_SPEC.md §4), record mode.
 * WORK features come from the cadence learner (fx_cadence, M5); until it is published the
 * extractor reports has_period = 0, period_strength = 0, phase_err = NaN (§5). */
#ifndef FX_FEATURES_H
#define FX_FEATURES_H

#include "fx_config.h"
#include "fx_filters.h"
#include "fx_onset.h"

typedef struct {
    /* the 15 model inputs, in studies.ALL order */
    double di_end, di_max, didt_max;                                   /* CONV */
    double t_rise, dv_early, di_early, r_dyn, v_sag_end, v_min, collapse, spec_i, spec_v;   /* PHYS */
    double has_period, period_strength, phase_err;                     /* WORK */
    /* diagnostics */
    fx_onset_t onset;
    int n_w;
} fx_features_t;

/* working memory (no dynamic allocation): ~100 kB, place in AXI SRAM on the target */
typedef struct {
    double si[FX_N_REC_MAX], sv[FX_N_REC_MAX];       /* 5 us-smoothed streams */
    double smi[FX_N_W_MAX], smv[FX_N_W_MAX];         /* 10 us-smoothed decision window */
    fx_iir_t bp_i[FX_N_REC_MAX], bp_v[FX_N_REC_MAX]; /* band-pass outputs */
} fx_work_t;

/* a record in physical units (amperes, volts), sample 0 = record start */
typedef struct {
    const double *fi, *fv;
    int n;
    double fs;            /* must be FX_FS_FAST: the sample counts in fx_config.h assume it */
    double fs_i, fs_v;    /* full scales for the onset threshold floor (0.004 * fs) */
} fx_stream_t;

/* Returns 0 on success, < 0 on a malformed record. W_s is the decision window in seconds
 * (n_w = max(int(W_s * fs), 4), as in Python). Features are normalised by I_rated / V_ref. */
int fx_features_extract(const fx_stream_t *s, double W_s, double I_rated, double V_ref,
                        fx_work_t *w, fx_features_t *f);

/* the model input vector, studies.ALL order */
void fx_features_vector(const fx_features_t *f, double x[FX_N_FEATURES]);
extern const char *const fx_feature_names[FX_N_FEATURES];

#endif /* FX_FEATURES_H */
