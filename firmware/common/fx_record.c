#include "fx_record.h"
#include <string.h>

static uint16_t rd_u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t rd_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static float rd_f32(const uint8_t *p) { uint32_t u = rd_u32(p); float f; memcpy(&f, &u, 4); return f; }
static double rd_f64(const uint8_t *p)
{
    uint64_t u = (uint64_t)rd_u32(p) | ((uint64_t)rd_u32(p + 4) << 32);
    double d; memcpy(&d, &u, 8); return d;
}

int fx_record_parse_header(const uint8_t *b, size_t len, fx_record_header_t *h)
{
    if (len < FX_REC_HEADER_BYTES) return -1;
    if (memcmp(b, FX_REC_MAGIC, 4) != 0) return -2;
    memcpy(h->magic, b, 4); h->magic[4] = 0;
    h->version = rd_u16(b + 4);
    h->header_bytes = rd_u16(b + 6);
    if (h->version != FX_REC_VERSION || h->header_bytes != FX_REC_HEADER_BYTES) return -3;
    h->n_fast = rd_u32(b + 8);
    h->n_slow = rd_u32(b + 12);
    h->fs_fast = rd_f32(b + 16);
    h->fs_slow = rd_f32(b + 20);
    h->gain_i = rd_f32(b + 24);
    h->gain_v = rd_f32(b + 28);
    h->offset_i = rd_u16(b + 32);
    h->offset_v = rd_u16(b + 34);
    h->I_rated = rd_f64(b + 36);
    h->V_ref = rd_f64(b + 44);
    h->fs_i = rd_f64(b + 52);
    h->fs_v = rd_f64(b + 60);
    h->t0_fast = rd_f64(b + 68);
    h->t0_slow = rd_f64(b + 76);
    h->t_event = rd_f64(b + 84);
    h->node = b[92];
    h->adc_bits = b[93];
    h->slow_format = rd_u16(b + 94);
    memcpy(h->event_id, b + 96, 12); h->event_id[12] = 0;
    memcpy(h->label, b + 108, 20); h->label[20] = 0;
    return 0;
}

size_t fx_record_data_bytes(const fx_record_header_t *h)
{
    size_t n = 2u * (size_t)h->n_fast * 2u;
    if (h->slow_format == FX_REC_SLOW_F32) n += 2u * (size_t)h->n_slow * 4u;
    return n;
}

void fx_record_codes_to_phys(const uint16_t *codes, int n, uint16_t offset, float gain, double *out)
{
    for (int k = 0; k < n; ++k) {
        float x = (float)((int)codes[k] - (int)offset) * gain;   /* one float32 rounding */
        out[k] = (double)x;
    }
}
