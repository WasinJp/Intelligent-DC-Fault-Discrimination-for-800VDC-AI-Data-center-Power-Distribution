/* cadence_task.h — M5 on the node: slow-stream history (100:1 anti-alias decimation of the fast
 * stream, FIRMWARE_SPEC.md §3/§5) and the 200 ms background relearn that publishes the tiers used
 * by the decision path for phase_err. */
#ifndef CADENCE_TASK_H
#define CADENCE_TASK_H
#include <stdint.h>
#include "fx_cadence.h"

void cadence_init(void);
/* called per fast sample from the DMA block handler (physical current) */
void cadence_push_fast(double fi);
/* main loop: relearns every CADENCE_PERIOD_MS from the history, publishes atomically */
void cadence_poll(void);
/* the published tiers (NULL if none) and the publication count; t_on in seconds of the node time base */
const fx_cadence_tiers_t *cadence_published(uint32_t *generation);
uint32_t cadence_last_cycles(void);
uint32_t cadence_relearns(void);
uint32_t cadence_history_count(void);

#define CADENCE_PERIOD_MS 200u
#endif
