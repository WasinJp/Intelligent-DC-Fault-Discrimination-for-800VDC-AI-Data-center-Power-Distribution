/* fx_relay.h — Layer 1 thresholds and the Layer 2 decision (FIRMWARE_SPEC.md §7.1-7.2).
 * The combined two-node decision (§7.3) is milestone M6. */
#ifndef FX_RELAY_H
#define FX_RELAY_H

#include "fx_config.h"
#include "fx_model.h"

typedef enum { FX_DEC_HOLD = 0, FX_DEC_TRIP = 1, FX_DEC_ALERT = 2 } fx_decision_t;

typedef struct {
    double theta;     /* P(TRIP) > theta -> TRIP (default 0.5) */
    double l1_di;     /* Layer 1: |delta i| (p.u., 5 us-smoothed) > l1_di -> TRIP; default +inf (off) */
    double l1_v;      /* Layer 1: v (p.u.) < l1_v -> TRIP; default -inf (off) */
} fx_relay_cfg_t;

typedef struct {
    fx_decision_t decision;
    int layer;                    /* 1 or 2 */
    int argmax;
    double p_trip;
    double raw[FX_N_CLASSES];
    double proba[FX_N_CLASSES];
} fx_relay_result_t;

void fx_relay_cfg_default(fx_relay_cfg_t *c);
int  fx_relay_layer1(const fx_relay_cfg_t *c, double di_abs_pu, double v_pu);   /* 1 = trip now */
void fx_relay_layer2(const fx_relay_cfg_t *c, const fx_model_t *m, const double *x, fx_relay_result_t *r);
const char *fx_decision_name(fx_decision_t d);

#endif /* FX_RELAY_H */
