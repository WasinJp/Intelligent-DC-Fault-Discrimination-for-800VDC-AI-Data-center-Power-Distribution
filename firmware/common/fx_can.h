/* fx_can.h — CAN-FD frames between the two nodes and the combined decision (FIRMWARE_SPEC.md §7.3).
 *
 * Frames (little-endian, CAN-FD, standard 11-bit ids):
 *   summary (16 bytes, within 20 us of the window close): node, decision, has_period, flags,
 *            p_trip f32, phase_err f32, onset_sample u32 (500 kSa/s sample counter of the sender).
 *   features (3 x 64 bytes): the sender's 15 features as exact float64, 7 per frame, with an 8-byte
 *            header (magic 'F', node, part 0..2, n_parts 3, onset_sample u32). The two-node model
 *            needs the exact doubles (DEVIATIONS.md #6); float32 would flip splits.
 * The spec's single 16-byte frame cannot carry the 15 features the 30-feature model needs; this is
 * DEVIATIONS.md #13. Platform code (node/can.c) only moves bytes; everything here is testable on the host. */
#ifndef FX_CAN_H
#define FX_CAN_H

#include <stdint.h>
#include "fx_config.h"
#include "fx_model.h"
#include "fx_relay.h"

#define FX_CAN_ID_SUMMARY_FEEDER   0x101u
#define FX_CAN_ID_SUMMARY_RACK     0x102u
#define FX_CAN_ID_FEATURES_FEEDER  0x111u
#define FX_CAN_ID_FEATURES_RACK    0x112u
#define FX_CAN_SUMMARY_BYTES       16
#define FX_CAN_FEATURE_BYTES       64
#define FX_CAN_FEATURE_PARTS       3

typedef struct {
    uint8_t node;            /* 0 feeder, 1 rack */
    uint8_t decision;        /* fx_decision_t */
    uint8_t has_period;
    uint8_t flags;           /* bit0: layer 1 trip; bit1: two-node path used */
    float p_trip, phase_err;
    uint32_t onset_sample;
} fx_can_summary_t;

typedef struct {
    uint8_t node;
    uint32_t onset_sample;
    double x[FX_N_FEATURES];
    uint8_t parts_mask;      /* bits 0..2: parts received */
} fx_can_features_t;

void fx_can_encode_summary(const fx_can_summary_t *s, uint8_t out[FX_CAN_SUMMARY_BYTES]);
int  fx_can_decode_summary(const uint8_t in[FX_CAN_SUMMARY_BYTES], fx_can_summary_t *s);
void fx_can_encode_features(const fx_can_features_t *f, uint8_t out[FX_CAN_FEATURE_PARTS][FX_CAN_FEATURE_BYTES]);
/* decode one part into *acc (which accumulates parts of one onset); returns 1 when all parts are in */
int  fx_can_decode_feature_part(const uint8_t in[FX_CAN_FEATURE_BYTES], fx_can_features_t *acc);

/* Combined decision (feeder side): if a complete rack feature set is present whose onset is within
 * onset_tol samples of own_onset, score the 30-feature model on [own, rack]; else the own model.
 * *used_two_node reports the path. */
void fx_combined_decide(const fx_relay_cfg_t *cfg, const fx_model_t *m_own, const fx_model_t *m_both,
                        const double x_own[FX_N_FEATURES], const fx_can_features_t *rack, uint32_t own_onset,
                        uint32_t onset_tol, fx_relay_result_t *r, int *used_two_node);

#endif /* FX_CAN_H */
