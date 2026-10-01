/* stream.h — the node pipeline (FIRMWARE_SPEC.md §4.2, §4.3, §7, §8):
 *   DMA block (8 dual samples, every 16 us, highest priority)
 *     -> ring buffer (2 x 8192 uint16, 16 ms) -> calibration -> Layer 1 -> stream-mode detector
 *     -> at the window close (k_on + N_W samples acquired): PendSV
 *   PendSV (lower priority, preemptible by the DMA block)
 *     -> record [k_on-100, k_on+N_W) in record mode: fx_features_extract -> model -> Layer 2 -> TRIP pin
 *   main loop: console, status, record upload (M6), cadence relearn (M5 target). */
#ifndef STREAM_H
#define STREAM_H
#include <stdint.h>
#include "fx_features.h"
#include "fx_relay.h"
#include "fx_record.h"

#define RING_N 8192

typedef struct {
    uint32_t valid;                 /* a decision has been made since arm */
    uint32_t k_on;                  /* absolute sample index of the onset */
    uint32_t rec_start;             /* first sample of the record the features were computed on */
    uint32_t layer;                 /* 1 or 2 */
    int used_two_node;              /* feeder: the 30-feature model was used (§7.3) */
    fx_features_t f;
    fx_relay_result_t r;
    uint32_t cyc_extract, cyc_infer, cyc_close_to_trip, cyc_onset_to_trip;
    uint32_t sync_sample;           /* absolute sample index at the last SYNC pulse (0 = none) */
} decision_t;

void stream_init(void);
void stream_on_block(const uint32_t *words, int n);     /* DMA callback */
void stream_decide(void);                                /* PendSV */
void stream_arm(void);
void stream_sync_mark(void);                             /* EXTI */
void stream_capture_request(void);                       /* `capture`: upload the last 5.2 ms */
void stream_poll_upload(void);                           /* main loop: record upload at k_on + 2500 (§8) */
const decision_t *stream_last(void);
uint32_t stream_sample_count(void);
int  stream_detector_armed(void);

/* synthetic-step self test on the stream's record buffers (detector paused); 0 ok */
int stream_selftest(fx_features_t *f, uint32_t *cycles);

/* record-mode parity path (§6.4): an FXR1 blob pushed by the host; prints one CSV line per window
 * through out() in the format of fx_cli extract (plus DWT cycle columns). Returns 0 on success. */
int stream_replay(const uint8_t *blob, uint32_t len, const double *W_s, int nW, void (*out)(const char *));

#endif
