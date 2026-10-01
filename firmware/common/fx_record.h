/* fx_record.h — event record layout (FIRMWARE_SPEC.md §8 / §6.1 fixtures), format FXR1.
 *
 *   header, 128 bytes, little-endian (Python struct "<4sHHIIffffHHdddddddBBH12s20s"):
 *     magic "FXR1", version u16, header_bytes u16, n_fast u32, n_slow u32,
 *     fs_fast f32, fs_slow f32, gain_i f32, gain_v f32, offset_i u16, offset_v u16,
 *     I_rated f64, V_ref f64, fs_i f64, fs_v f64, t0_fast f64, t0_slow f64, t_event f64,
 *     node u8 (0 feeder, 1 rack), adc_bits u8, slow_format u16 (0 none, 2 float32 physical),
 *     event_id char[12], label char[20]
 *   data: fast_i u16[n_fast], fast_v u16[n_fast], slow_i f32[n_slow], slow_v f32[n_slow]
 *
 * Physical value of a code: (float)(code - offset) * gain, evaluated in float32 (the node's
 * calibration path), then promoted to double for the features.
 * The node's ring buffer and the on-target record queue (§8) are milestone M3. */
#ifndef FX_RECORD_H
#define FX_RECORD_H

#include <stdint.h>
#include <stddef.h>

#define FX_REC_MAGIC        "FXR1"
#define FX_REC_VERSION      1
#define FX_REC_HEADER_BYTES 128
#define FX_REC_SLOW_NONE    0
#define FX_REC_SLOW_F32     2

typedef struct {
    char magic[5];
    uint16_t version, header_bytes;
    uint32_t n_fast, n_slow;
    float fs_fast, fs_slow, gain_i, gain_v;
    uint16_t offset_i, offset_v;
    double I_rated, V_ref, fs_i, fs_v, t0_fast, t0_slow, t_event;
    uint8_t node, adc_bits;
    uint16_t slow_format;
    char event_id[13], label[21];
} fx_record_header_t;

int fx_record_parse_header(const uint8_t *buf, size_t len, fx_record_header_t *h);  /* 0 = ok */
size_t fx_record_data_bytes(const fx_record_header_t *h);
void fx_record_codes_to_phys(const uint16_t *codes, int n, uint16_t offset, float gain, double *out);

#endif /* FX_RECORD_H */
