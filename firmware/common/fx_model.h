/* fx_model.h — gradient-boosted tree inference (sklearn HistGradientBoostingClassifier,
 * FIRMWARE_SPEC.md §6.3). Tables come from tools/export_model.py -> fx_model_data.h. */
#ifndef FX_MODEL_H
#define FX_MODEL_H

#include <stdint.h>
#include <stddef.h>
#include "fx_config.h"

/* 12-byte node (packed, 4-byte aligned: 12-byte stride, VLDR-compatible on Cortex-M7).
 * Split node: v = num_threshold, exact float64 (go left if x <= v), feat = feature index,
 * left/right = child index relative to the tree start. Leaf: v = leaf value (learning rate
 * already applied by sklearn). NaN in a feature follows FX_NODE_MISSING_LEFT.
 * Thresholds must stay float64: sklearn's thresholds are midpoints of training values and
 * grid-valued features (t_rise) land exactly on them; float32 rounding flipped 12 splits in
 * the fixture set (raw-score error up to 1.4). */
typedef struct __attribute__((packed, aligned(4))) {
    double v;
    uint8_t left, right, feat, flags;
} fx_node_t;
#define FX_NODE_LEAF          1u
#define FX_NODE_MISSING_LEFT  2u

typedef struct {
    const char *name;
    const fx_node_t *nodes;
    const uint32_t *tree_start;        /* n_trees + 1 entries into nodes[] */
    uint32_t n_nodes;
    uint16_t n_trees;                  /* n_iter * n_classes, iteration-major */
    uint8_t n_classes, n_features;
    double baseline[FX_N_CLASSES];     /* clf._baseline_prediction */
} fx_model_t;

/* raw class scores = baseline + sum of leaf values (== clf.decision_function) */
void fx_model_raw(const fx_model_t *m, const double *x, double raw[FX_N_CLASSES]);
void fx_model_softmax(const double *raw, int n, double *p);   /* == clf.predict_proba */
int  fx_model_argmax(const double *raw, int n);
size_t fx_model_bytes(const fx_model_t *m);

int fx_model_count(void);
const fx_model_t *fx_model_at(int i);
const fx_model_t *fx_model_get(const char *name);             /* "feeder", "rack", "both"; NULL if absent */
extern const char *const fx_class_names[FX_N_CLASSES];

#endif /* FX_MODEL_H */
