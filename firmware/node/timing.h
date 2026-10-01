/* timing.h — DWT cycle counter and per-stage statistics (FIRMWARE_SPEC.md §1.5, §7.4). */
#ifndef TIMING_H
#define TIMING_H

#include <stdint.h>
#include "stm32h7xx_hal.h"

typedef enum {
    T_DETECT_BLOCK = 0,   /* detector + ring copy per 8-sample DMA block */
    T_EXTRACT,            /* fx_features_extract (record mode on the stream record) */
    T_INFER,              /* fx_model_raw + softmax + decision */
    T_CLOSE_TO_TRIP,      /* window-close block interrupt -> trip pin */
    T_ONSET_TO_TRIP,      /* onset sample detected -> trip pin (includes the 250 us window) */
    T_RELEARN,            /* cadence relearn (M5, background) */
    T_COUNT
} timing_id_t;

#define TIMING_RING 1024

typedef struct {
    uint32_t n, last, min, max;
    uint64_t sum;
    uint32_t ring[TIMING_RING];   /* last TIMING_RING samples for p99 */
} timing_stat_t;

void timing_init(void);
static inline uint32_t dwt_now(void) { return DWT->CYCCNT; }
void timing_add(timing_id_t id, uint32_t cycles);
const timing_stat_t *timing_get(timing_id_t id);
const char *timing_name(timing_id_t id);
uint32_t timing_p99(timing_id_t id);           /* over the ring (sorted copy) */
void timing_reset(void);
static inline double cycles_to_us(uint32_t c) { return (double)c / 480.0; }

#endif
