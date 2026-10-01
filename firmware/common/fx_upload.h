/* fx_upload.h — framed record upload (FIRMWARE_SPEC.md §8): the node sends, at k_on + 2 500 samples
 * (or on SYNC / `capture`), one frame per event over USB CDC:
 *
 *   "FXRU" | version u16 | payload_len u32 | payload | crc32 u32 (IEEE, over the payload)
 *   payload = FXR1 record header (128 bytes, fx_record.h; n_slow 0) | fast_i u16[n] | fast_v u16[n]
 *           | trailer (FX_UPLOAD_TRAILER_BYTES)
 *   trailer = k_on u32 | sample_count u32 | sync_sample u32 | decision u8 | layer u8 | has_period u8 |
 *             used_two_node u8 | p_trip f32 | 15 x feature f64 | cyc_extract, cyc_infer,
 *             cyc_close_to_trip, cyc_onset_to_trip u32
 *
 * tools/record_decoder.py reads the stream, checks the CRC, writes the FXR1 record (the layout
 * make_fixtures.py writes, so fx_cli extract / compare.py accept it) and a CSV of the trailers. */
#ifndef FX_UPLOAD_H
#define FX_UPLOAD_H

#include <stdint.h>
#include <stddef.h>
#include "fx_config.h"
#include "fx_record.h"

#define FX_UPLOAD_MAGIC          "FXRU"
#define FX_UPLOAD_VERSION        1u
#define FX_UPLOAD_HEAD_BYTES     10u      /* magic 4 + version 2 + len 4 */
#define FX_UPLOAD_TRAILER_BYTES  (12u + 4u + 4u + 8u * FX_N_FEATURES + 16u)   /* 156 */

typedef struct {
    uint32_t k_on, sample_count, sync_sample;
    uint8_t decision, layer, has_period, used_two_node;
    float p_trip;
    double x[FX_N_FEATURES];
    uint32_t cyc_extract, cyc_infer, cyc_close_to_trip, cyc_onset_to_trip;
} fx_upload_trailer_t;

uint32_t fx_crc32(const uint8_t *p, size_t n);
size_t fx_upload_frame_bytes(uint32_t n_fast);
/* builds the whole frame into out (cap bytes); returns the frame length or 0 if cap is too small */
size_t fx_upload_build(uint8_t *out, size_t cap, const fx_record_header_t *h, const uint16_t *ci, const uint16_t *cv,
                       const fx_upload_trailer_t *t);
/* host-side / test: parse a frame; returns 0 and fills h, pointers into buf and the trailer */
int fx_upload_parse(const uint8_t *buf, size_t len, fx_record_header_t *h, const uint16_t **ci, const uint16_t **cv,
                    fx_upload_trailer_t *t);
void fx_record_write_header(uint8_t *out /* FX_REC_HEADER_BYTES */, const fx_record_header_t *h);

#endif /* FX_UPLOAD_H */
