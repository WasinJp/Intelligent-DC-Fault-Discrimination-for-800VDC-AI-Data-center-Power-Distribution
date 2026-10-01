#include "fx_model.h"
/* the model tables; a build may point FX_MODEL_DATA_H_PATH at another exported header
 * (CMake -DFX_MODEL_DATA_H=<path>) for the §7.4 budget study */
#ifndef FX_MODEL_DATA_H_PATH
#define FX_MODEL_DATA_H_PATH "fx_model_data.h"
#endif
#include FX_MODEL_DATA_H_PATH
#include <math.h>
#include <string.h>

const char *const fx_class_names[FX_N_CLASSES] = { "ALERT", "HOLD", "TRIP" };

void fx_model_raw(const fx_model_t *m, const double *x, double raw[FX_N_CLASSES])
{
    for (int c = 0; c < m->n_classes; ++c) raw[c] = m->baseline[c];
    for (int t = 0; t < m->n_trees; ++t) {
        const fx_node_t *tree = m->nodes + m->tree_start[t];
        const fx_node_t *nd = tree;
        for (;;) {
            if (nd->flags & FX_NODE_LEAF) break;
            double xv = x[nd->feat];
            unsigned next;
            if (xv != xv) next = (nd->flags & FX_NODE_MISSING_LEFT) ? nd->left : nd->right;
            else          next = (xv <= nd->v) ? nd->left : nd->right;
            nd = tree + next;
        }
        raw[t % m->n_classes] += nd->v;
    }
}

void fx_model_softmax(const double *raw, int n, double *p)
{
    double mx = raw[0];
    for (int c = 1; c < n; ++c) if (raw[c] > mx) mx = raw[c];
    double s = 0.0;
    for (int c = 0; c < n; ++c) { p[c] = exp(raw[c] - mx); s += p[c]; }
    for (int c = 0; c < n; ++c) p[c] /= s;
}

int fx_model_argmax(const double *raw, int n)
{
    int a = 0;
    for (int c = 1; c < n; ++c) if (raw[c] > raw[a]) a = c;
    return a;
}

size_t fx_model_bytes(const fx_model_t *m)
{
    return (size_t)m->n_nodes * sizeof(fx_node_t) + ((size_t)m->n_trees + 1) * sizeof(uint32_t) + sizeof(fx_model_t);
}

int fx_model_count(void) { return FX_N_MODELS; }
const fx_model_t *fx_model_at(int i) { return (i >= 0 && i < FX_N_MODELS) ? FX_MODEL_TABLE[i] : NULL; }
const fx_model_t *fx_model_get(const char *name)
{
    for (int i = 0; i < FX_N_MODELS; ++i)
        if (strcmp(FX_MODEL_TABLE[i]->name, name) == 0) return FX_MODEL_TABLE[i];
    return NULL;
}
