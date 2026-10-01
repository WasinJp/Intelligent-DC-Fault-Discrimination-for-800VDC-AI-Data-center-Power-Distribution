#include "fx_relay.h"
#include <math.h>

void fx_relay_cfg_default(fx_relay_cfg_t *c)
{
    c->theta = 0.5;
    c->l1_di = INFINITY;
    c->l1_v = -INFINITY;
}

int fx_relay_layer1(const fx_relay_cfg_t *c, double di_abs_pu, double v_pu)
{
    return (di_abs_pu > c->l1_di) || (v_pu < c->l1_v);
}

void fx_relay_layer2(const fx_relay_cfg_t *c, const fx_model_t *m, const double *x, fx_relay_result_t *r)
{
    fx_model_raw(m, x, r->raw);
    fx_model_softmax(r->raw, m->n_classes, r->proba);
    r->argmax = fx_model_argmax(r->raw, m->n_classes);
    r->p_trip = r->proba[FX_CLASS_TRIP];
    r->layer = 2;
    if (r->p_trip > c->theta) r->decision = FX_DEC_TRIP;
    else if (r->argmax == FX_CLASS_ALERT) r->decision = FX_DEC_ALERT;   /* alert pin, never the trip pin */
    else r->decision = FX_DEC_HOLD;
}

const char *fx_decision_name(fx_decision_t d)
{
    switch (d) {
    case FX_DEC_TRIP: return "TRIP";
    case FX_DEC_ALERT: return "ALERT";
    default: return "HOLD";
    }
}
