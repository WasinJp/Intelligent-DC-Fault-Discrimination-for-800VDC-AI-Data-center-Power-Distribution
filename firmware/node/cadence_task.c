#include "cadence_task.h"
#include "board.h"
#include "timing.h"
#include "fx_filters.h"
#include "fx_cadence32.h"
#include <string.h>

/* memory map (DEVIATIONS.md #12): history + learner shadow/ac/acc/cnt/state/peaks in AXI SRAM,
 * FFT work in D2 SRAM, edges in DTCM */
__attribute__((section(".ram_d1"))) static fx_hist32_t g_hist;
__attribute__((section(".ram_d1"))) static float g_shadow[FX_CAD32_H], g_ac[FX_CAD32_K], g_acc[FX_CAD32_K];
__attribute__((section(".ram_d1"))) static uint8_t g_cnt[FX_CAD32_K], g_state[FX_CAD32_STATE_BYTES];
__attribute__((section(".ram_d1"))) static int g_peaks[FX_CAD32_NPEAKS];
__attribute__((section(".ram_d1"))) static float g_heights[FX_CAD32_NPEAKS];
__attribute__((section(".ram_d2"))) static float g_fa[FX_CAD32_FFT_N], g_fb[FX_CAD32_FFT_N], g_fc[FX_CAD32_FFT_N];
static double g_e1[FX_CAD32_EDGES], g_e2[FX_CAD32_EDGES], g_e2cur[FX_CAD32_EDGES];
static int g_bounds[FX_CAD32_NBOUNDS];
static fx_cadence32_t g_learner;

/* two published copies: the learner writes the inactive one, then flips the index */
static fx_cadence_tiers_t g_pub[2];
__attribute__((section(".ram_d3"))) static double g_pub_e1[2][FX_CAD32_EDGES], g_pub_e2[2][FX_CAD32_EDGES], g_pub_e2cur[2][FX_CAD32_EDGES];
static volatile uint32_t g_active;            /* 0/1; generation = g_gen */
static volatile uint32_t g_gen, g_relearns, g_last_cycles;
static fx_decim_t g_decim;
static uint32_t g_last_ms;
static volatile uint32_t g_fast_count;        /* fast samples pushed (for t_end) */

void cadence_init(void)
{
    fx_hist32_init(&g_hist, FX_FS_SLOW, 0.0);
    fx_decim_init(&g_decim, FX_DECIM_SLOW);
    fx_fft32_init();
    fx_cadence32_bind(&g_learner, g_e1, g_e2, g_e2cur, g_shadow, g_ac, g_acc, g_cnt, g_state, g_fa, g_fb, g_fc,
                      g_peaks, g_heights, g_bounds);
    memset(g_pub, 0, sizeof g_pub);
    g_active = 0; g_gen = 0; g_relearns = 0; g_last_cycles = 0; g_fast_count = 0;
    g_last_ms = HAL_GetTick();
}

void cadence_push_fast(double fi)
{
    fx_iir_t y;
    g_fast_count++;
    if (fx_decim_push(&g_decim, (fx_iir_t)fi, &y)) fx_hist32_push(&g_hist, (float)y);
}

static void publish(const fx_cadence_tiers_t *src)
{
    uint32_t next = g_active ^ 1u;
    fx_cadence_tiers_t *dst = &g_pub[next];
    *dst = *src;
    for (int i = 0; i < src->n_tiers; ++i) {
        const fx_tier_t *t = &src->tier[i];
        fx_tier_t *d = &dst->tier[i];
        int ne = t->n_edges < FX_CAD32_EDGES ? t->n_edges : FX_CAD32_EDGES;
        double *e = i == 0 ? g_pub_e1[next] : g_pub_e2[next];
        memcpy(e, t->edges, sizeof(double) * (size_t)ne);
        d->edges = e; d->n_edges = ne;
        if (t->is_tier2) {
            int nc = t->n_current < FX_CAD32_EDGES ? t->n_current : FX_CAD32_EDGES;
            memcpy(g_pub_e2cur[next], t->edges_current, sizeof(double) * (size_t)nc);
            d->edges_current = g_pub_e2cur[next]; d->n_current = nc;
        }
    }
    __DMB();
    g_active = next;
    g_gen++;
}

void cadence_poll(void)
{
    uint32_t now = HAL_GetTick();
    if (now - g_last_ms < CADENCE_PERIOD_MS) return;
    g_last_ms = now;
    /* history up to "now" (the decision path uses t_on - 0.5 ms; the published tiers are at most
     * 200 ms old, which is the spec's background cadence) */
    double t_end = (double)g_fast_count / FX_FS_FAST;
    uint32_t t0 = dwt_now();
    fx_cadence32_learn(&g_learner, &g_hist, FX_W_025, t_end);
    g_last_cycles = dwt_now() - t0;
    timing_add(T_RELEARN, g_last_cycles);
    publish(&g_learner.tiers);
    g_relearns++;
}

const fx_cadence_tiers_t *cadence_published(uint32_t *generation)
{
    if (generation) *generation = g_gen;
    if (g_gen == 0) return NULL;
    return &g_pub[g_active];
}

uint32_t cadence_last_cycles(void) { return g_last_cycles; }
uint32_t cadence_relearns(void) { return g_relearns; }
uint32_t cadence_history_count(void) { return g_hist.count; }
