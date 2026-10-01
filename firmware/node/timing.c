#include "timing.h"
#include <string.h>
#include <stdlib.h>

static timing_stat_t g_stat[T_COUNT];
static const char *const g_names[T_COUNT] = {
    "detect_block", "extract", "infer", "close_to_trip", "onset_to_trip", "relearn"
};

void timing_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->LAR = 0xC5ACCE55;                     /* unlock on Cortex-M7 */
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    timing_reset();
}

void timing_reset(void)
{
    memset(g_stat, 0, sizeof g_stat);
    for (int i = 0; i < T_COUNT; ++i) g_stat[i].min = 0xFFFFFFFFu;
}

void timing_add(timing_id_t id, uint32_t cycles)
{
    timing_stat_t *s = &g_stat[id];
    s->ring[s->n % TIMING_RING] = cycles;
    s->n++;
    s->last = cycles;
    s->sum += cycles;
    if (cycles < s->min) s->min = cycles;
    if (cycles > s->max) s->max = cycles;
}

const timing_stat_t *timing_get(timing_id_t id) { return &g_stat[id]; }
const char *timing_name(timing_id_t id) { return g_names[id]; }

static int cmp_u32(const void *a, const void *b)
{
    uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b;
    return (x > y) - (x < y);
}

uint32_t timing_p99(timing_id_t id)
{
    static uint32_t tmp[TIMING_RING];
    const timing_stat_t *s = &g_stat[id];
    uint32_t n = s->n < TIMING_RING ? s->n : TIMING_RING;
    if (n == 0) return 0;
    memcpy(tmp, s->ring, sizeof(uint32_t) * n);
    qsort(tmp, n, sizeof(uint32_t), cmp_u32);
    return tmp[(uint32_t)((double)n * 0.99) < n ? (uint32_t)((double)n * 0.99) : n - 1];
}
