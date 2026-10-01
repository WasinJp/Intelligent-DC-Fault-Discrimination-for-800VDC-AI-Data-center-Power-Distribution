#include "fx_upload.h"
#include <string.h>

static void wr_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void wr_u32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint16_t rd_u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t rd_u32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static void wr_f32(uint8_t *p, float f) { uint32_t u; memcpy(&u, &f, 4); wr_u32(p, u); }
static float rd_f32(const uint8_t *p) { uint32_t u = rd_u32(p); float f; memcpy(&f, &u, 4); return f; }
static void wr_f64(uint8_t *p, double d) { uint64_t u; memcpy(&u, &d, 8); wr_u32(p, (uint32_t)u); wr_u32(p + 4, (uint32_t)(u >> 32)); }
static double rd_f64(const uint8_t *p) { uint64_t u = (uint64_t)rd_u32(p) | ((uint64_t)rd_u32(p + 4) << 32); double d; memcpy(&d, &u, 8); return d; }

uint32_t fx_crc32(const uint8_t *p, size_t n)
{
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i) {
        c ^= p[i];
        for (int k = 0; k < 8; ++k) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

void fx_record_write_header(uint8_t *b, const fx_record_header_t *h)
{
    memset(b, 0, FX_REC_HEADER_BYTES);
    memcpy(b, FX_REC_MAGIC, 4);
    wr_u16(b + 4, FX_REC_VERSION);
    wr_u16(b + 6, FX_REC_HEADER_BYTES);
    wr_u32(b + 8, h->n_fast);
    wr_u32(b + 12, h->n_slow);
    wr_f32(b + 16, h->fs_fast); wr_f32(b + 20, h->fs_slow); wr_f32(b + 24, h->gain_i); wr_f32(b + 28, h->gain_v);
    wr_u16(b + 32, h->offset_i); wr_u16(b + 34, h->offset_v);
    wr_f64(b + 36, h->I_rated); wr_f64(b + 44, h->V_ref); wr_f64(b + 52, h->fs_i); wr_f64(b + 60, h->fs_v);
    wr_f64(b + 68, h->t0_fast); wr_f64(b + 76, h->t0_slow); wr_f64(b + 84, h->t_event);
    b[92] = h->node; b[93] = h->adc_bits;
    wr_u16(b + 94, h->slow_format);
    memcpy(b + 96, h->event_id, 12);
    memcpy(b + 108, h->label, 20);
}

size_t fx_upload_frame_bytes(uint32_t n_fast)
{
    return FX_UPLOAD_HEAD_BYTES + FX_REC_HEADER_BYTES + 4u * (size_t)n_fast + FX_UPLOAD_TRAILER_BYTES + 4u;
}

static void encode_trailer(uint8_t *p, const fx_upload_trailer_t *t)
{
    wr_u32(p, t->k_on); wr_u32(p + 4, t->sample_count); wr_u32(p + 8, t->sync_sample);
    p[12] = t->decision; p[13] = t->layer; p[14] = t->has_period; p[15] = t->used_two_node;
    wr_f32(p + 16, t->p_trip);
    for (int k = 0; k < FX_N_FEATURES; ++k) wr_f64(p + 20 + 8 * k, t->x[k]);
    uint8_t *q = p + 20 + 8 * FX_N_FEATURES;
    wr_u32(q, t->cyc_extract); wr_u32(q + 4, t->cyc_infer); wr_u32(q + 8, t->cyc_close_to_trip); wr_u32(q + 12, t->cyc_onset_to_trip);
}

static void decode_trailer(const uint8_t *p, fx_upload_trailer_t *t)
{
    t->k_on = rd_u32(p); t->sample_count = rd_u32(p + 4); t->sync_sample = rd_u32(p + 8);
    t->decision = p[12]; t->layer = p[13]; t->has_period = p[14]; t->used_two_node = p[15];
    t->p_trip = rd_f32(p + 16);
    for (int k = 0; k < FX_N_FEATURES; ++k) t->x[k] = rd_f64(p + 20 + 8 * k);
    const uint8_t *q = p + 20 + 8 * FX_N_FEATURES;
    t->cyc_extract = rd_u32(q); t->cyc_infer = rd_u32(q + 4); t->cyc_close_to_trip = rd_u32(q + 8); t->cyc_onset_to_trip = rd_u32(q + 12);
}

size_t fx_upload_build(uint8_t *out, size_t cap, const fx_record_header_t *h, const uint16_t *ci, const uint16_t *cv,
                       const fx_upload_trailer_t *t)
{
    size_t total = fx_upload_frame_bytes(h->n_fast);
    if (cap < total) return 0;
    size_t plen = total - FX_UPLOAD_HEAD_BYTES - 4u;
    memcpy(out, FX_UPLOAD_MAGIC, 4);
    wr_u16(out + 4, FX_UPLOAD_VERSION);
    wr_u32(out + 6, (uint32_t)plen);
    uint8_t *p = out + FX_UPLOAD_HEAD_BYTES;
    fx_record_header_t hh = *h;
    hh.n_slow = 0; hh.slow_format = FX_REC_SLOW_NONE;
    fx_record_write_header(p, &hh);
    p += FX_REC_HEADER_BYTES;
    for (uint32_t k = 0; k < h->n_fast; ++k) wr_u16(p + 2 * k, ci[k]);
    p += 2u * h->n_fast;
    for (uint32_t k = 0; k < h->n_fast; ++k) wr_u16(p + 2 * k, cv[k]);
    p += 2u * h->n_fast;
    encode_trailer(p, t);
    p += FX_UPLOAD_TRAILER_BYTES;
    wr_u32(p, fx_crc32(out + FX_UPLOAD_HEAD_BYTES, plen));
    return total;
}

int fx_upload_parse(const uint8_t *buf, size_t len, fx_record_header_t *h, const uint16_t **ci, const uint16_t **cv,
                    fx_upload_trailer_t *t)
{
    if (len < FX_UPLOAD_HEAD_BYTES + FX_REC_HEADER_BYTES + FX_UPLOAD_TRAILER_BYTES + 4u) return -1;
    if (memcmp(buf, FX_UPLOAD_MAGIC, 4) != 0 || rd_u16(buf + 4) != FX_UPLOAD_VERSION) return -2;
    uint32_t plen = rd_u32(buf + 6);
    if (len < FX_UPLOAD_HEAD_BYTES + plen + 4u) return -3;
    const uint8_t *p = buf + FX_UPLOAD_HEAD_BYTES;
    if (fx_crc32(p, plen) != rd_u32(p + plen)) return -4;
    if (fx_record_parse_header(p, plen, h) != 0) return -5;
    if (plen != FX_REC_HEADER_BYTES + 4u * h->n_fast + FX_UPLOAD_TRAILER_BYTES) return -6;
    *ci = (const uint16_t *)(const void *)(p + FX_REC_HEADER_BYTES);               /* little-endian host */
    *cv = (const uint16_t *)(const void *)(p + FX_REC_HEADER_BYTES + 2u * h->n_fast);
    decode_trailer(p + FX_REC_HEADER_BYTES + 4u * h->n_fast, t);
    return 0;
}
