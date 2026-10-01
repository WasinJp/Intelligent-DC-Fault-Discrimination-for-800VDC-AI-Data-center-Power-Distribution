#include "fx_can.h"
#include <string.h>
#include <math.h>

static void wr_u32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint32_t rd_u32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static void wr_f32(uint8_t *p, float f) { uint32_t u; memcpy(&u, &f, 4); wr_u32(p, u); }
static float rd_f32(const uint8_t *p) { uint32_t u = rd_u32(p); float f; memcpy(&f, &u, 4); return f; }
static void wr_f64(uint8_t *p, double d) { uint64_t u; memcpy(&u, &d, 8); wr_u32(p, (uint32_t)u); wr_u32(p + 4, (uint32_t)(u >> 32)); }
static double rd_f64(const uint8_t *p) { uint64_t u = (uint64_t)rd_u32(p) | ((uint64_t)rd_u32(p + 4) << 32); double d; memcpy(&d, &u, 8); return d; }

void fx_can_encode_summary(const fx_can_summary_t *s, uint8_t out[FX_CAN_SUMMARY_BYTES])
{
    out[0] = s->node; out[1] = s->decision; out[2] = s->has_period; out[3] = s->flags;
    wr_f32(out + 4, s->p_trip);
    wr_f32(out + 8, s->phase_err);
    wr_u32(out + 12, s->onset_sample);
}

int fx_can_decode_summary(const uint8_t in[FX_CAN_SUMMARY_BYTES], fx_can_summary_t *s)
{
    if (in[0] > 1 || in[1] > 2) return -1;
    s->node = in[0]; s->decision = in[1]; s->has_period = in[2]; s->flags = in[3];
    s->p_trip = rd_f32(in + 4); s->phase_err = rd_f32(in + 8); s->onset_sample = rd_u32(in + 12);
    return 0;
}

void fx_can_encode_features(const fx_can_features_t *f, uint8_t out[FX_CAN_FEATURE_PARTS][FX_CAN_FEATURE_BYTES])
{
    for (int part = 0; part < FX_CAN_FEATURE_PARTS; ++part) {
        uint8_t *p = out[part];
        memset(p, 0, FX_CAN_FEATURE_BYTES);
        p[0] = 'F'; p[1] = f->node; p[2] = (uint8_t)part; p[3] = FX_CAN_FEATURE_PARTS;
        wr_u32(p + 4, f->onset_sample);
        for (int j = 0; j < 7; ++j) {
            int idx = part * 7 + j;
            if (idx < FX_N_FEATURES) wr_f64(p + 8 + 8 * j, f->x[idx]);
        }
    }
}

int fx_can_decode_feature_part(const uint8_t in[FX_CAN_FEATURE_BYTES], fx_can_features_t *acc)
{
    if (in[0] != 'F' || in[2] >= FX_CAN_FEATURE_PARTS || in[3] != FX_CAN_FEATURE_PARTS) return -1;
    uint32_t onset = rd_u32(in + 4);
    if (acc->parts_mask == 0 || acc->onset_sample != onset || acc->node != in[1]) {   /* a new set */
        acc->parts_mask = 0; acc->onset_sample = onset; acc->node = in[1];
        for (int k = 0; k < FX_N_FEATURES; ++k) acc->x[k] = NAN;
    }
    int part = in[2];
    for (int j = 0; j < 7; ++j) {
        int idx = part * 7 + j;
        if (idx < FX_N_FEATURES) acc->x[idx] = rd_f64(in + 8 + 8 * j);
    }
    acc->parts_mask |= (uint8_t)(1u << part);
    return acc->parts_mask == (1u << FX_CAN_FEATURE_PARTS) - 1u;
}

void fx_combined_decide(const fx_relay_cfg_t *cfg, const fx_model_t *m_own, const fx_model_t *m_both,
                        const double x_own[FX_N_FEATURES], const fx_can_features_t *rack, uint32_t own_onset,
                        uint32_t onset_tol, fx_relay_result_t *r, int *used_two_node)
{
    int complete = rack && m_both && rack->parts_mask == (1u << FX_CAN_FEATURE_PARTS) - 1u;
    uint32_t d = 0;
    if (complete) d = own_onset > rack->onset_sample ? own_onset - rack->onset_sample : rack->onset_sample - own_onset;
    if (complete && d <= onset_tol) {
        double x[FX_N_FEATURES_TWO];
        memcpy(x, x_own, sizeof(double) * FX_N_FEATURES);
        memcpy(x + FX_N_FEATURES, rack->x, sizeof(double) * FX_N_FEATURES);
        fx_relay_layer2(cfg, m_both, x, r);
        *used_two_node = 1;
    } else {
        fx_relay_layer2(cfg, m_own, x_own, r);
        *used_two_node = 0;
    }
}
