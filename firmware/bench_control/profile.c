#include "profile.h"
#include "board_bc.h"
#include "fault.h"
#include <string.h>

/* conductance of each branch relative to all five closed (2.2, 4.7, 10, 22, 47 ohm) */
static const float g_frac[LOAD_N] = { 0.5451f, 0.2552f, 0.1199f, 0.0545f, 0.0255f };
static const uint16_t g_pins[LOAD_N] = LOAD_PINS;

TIM_HandleTypeDef htim2;                         /* 1 MHz scheduler */
static profile_cfg_t g_cfg;
static volatile uint32_t g_t_us;
static volatile int g_running;
static volatile uint8_t g_gates;
static uint32_t g_rng;

/* staircase in progress */
static volatile uint8_t g_stair_target, g_stair_pending;
static volatile uint32_t g_stair_next_us, g_stair_dt_us;
static volatile uint8_t g_stair_order[LOAD_N], g_stair_n, g_stair_i;

/* cadence state */
static uint32_t g_iter_start_us, g_iter;
static int g_phase_high;
static uint32_t g_next_burst_us;
static int g_in_burst;
static volatile uint32_t g_next_edge_us;

static uint32_t rng(void) { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 17; g_rng ^= g_rng << 5; return g_rng; }
static float rngf(float a, float b) { return a + (b - a) * (float)(rng() & 0xFFFFFF) / 16777215.0f; }

static void apply_gates(uint8_t mask)
{
    for (int i = 0; i < LOAD_N; ++i) HAL_GPIO_WritePin(LOAD_GPIO, g_pins[i], (mask >> i) & 1 ? GPIO_PIN_SET : GPIO_PIN_RESET);
    g_gates = mask;
}

uint8_t profile_mask_for(float frac)
{
    /* greedy subset: closest total conductance fraction */
    uint8_t best = 0; float bd = 1e9f;
    for (uint8_t m = 0; m < 32; ++m) {
        float s = 0.0f;
        for (int i = 0; i < LOAD_N; ++i) if ((m >> i) & 1) s += g_frac[i];
        float d = s > frac ? s - frac : frac - s;
        if (d < bd) { bd = d; best = m; }
    }
    return best;
}

void profile_defaults(profile_cfg_t *c)
{
    c->seed = 20261001u;
    c->T1_s = 1.0f; c->duty1 = 0.6f;
    c->T2_s = 0.05f; c->burst_frac = 0.10f;
    c->P_low = 0.30f; c->P_high = 0.70f;
    c->ramp_ms = 2.0f;
    c->idle_drop_every = 7;
}

void profile_init(void)
{
    __HAL_RCC_GPIOF_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Mode = GPIO_MODE_OUTPUT_PP; io.Pull = GPIO_NOPULL; io.Speed = GPIO_SPEED_FREQ_HIGH;
    for (int i = 0; i < LOAD_N; ++i) { io.Pin = g_pins[i]; HAL_GPIO_Init(LOAD_GPIO, &io); }
    io.Pin = LOAD_ENABLE_PIN; HAL_GPIO_Init(LOAD_ENABLE_GPIO, &io);
    HAL_GPIO_WritePin(LOAD_ENABLE_GPIO, LOAD_ENABLE_PIN, GPIO_PIN_SET);
    apply_gates(0);
    profile_defaults(&g_cfg);
    /* 1 MHz scheduler tick */
    __HAL_RCC_TIM2_CLK_ENABLE();
    htim2.Instance = TIM2;
    htim2.Init.Prescaler = BOARD_TIMCLK_HZ / 1000000u - 1u;
    htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim2.Init.Period = 0;                                   /* interrupt every microsecond would be too much: */
    htim2.Init.Period = 99;                                  /* tick every 100 us, time kept in us */
    htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    HAL_TIM_Base_Init(&htim2);
    HAL_NVIC_SetPriority(TIM2_IRQn, PRIO_SCHED_TIM, 0);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);
    HAL_TIM_Base_Start_IT(&htim2);
}

void profile_set(const profile_cfg_t *c) { g_cfg = *c; }
const profile_cfg_t *profile_cfg(void) { return &g_cfg; }
uint8_t profile_gates_now(void) { return g_gates; }
uint32_t profile_time_us(void) { return g_t_us; }
uint32_t profile_next_edge_us(void) { return g_next_edge_us; }
int profile_running(void) { return g_running; }
void profile_gates(uint8_t mask) { apply_gates(mask & 0x1F); }

/* begin a staircase from the current mask to target: branches switched one per ramp/5, largest first */
void profile_step(float frac, float ramp_ms)
{
    uint8_t target = profile_mask_for(frac);
    uint8_t diff = (uint8_t)(target ^ g_gates);
    g_stair_n = 0;
    for (int i = 0; i < LOAD_N; ++i) if ((diff >> i) & 1) g_stair_order[g_stair_n++] = (uint8_t)i;
    if (g_stair_n == 0) return;
    g_stair_target = target; g_stair_i = 0;
    g_stair_dt_us = (uint32_t)(ramp_ms * 1000.0f / 5.0f);
    if (g_stair_dt_us < 100u) g_stair_dt_us = 100u;
    g_stair_next_us = g_t_us;
    g_stair_pending = 1;
}

void profile_start(void)
{
    g_rng = g_cfg.seed ? g_cfg.seed : 1u;
    g_t_us = 0; g_iter = 0; g_iter_start_us = 0; g_phase_high = 0; g_in_burst = 0;
    g_next_edge_us = 0;
    g_running = 1;
}

void profile_stop(void)
{
    g_running = 0; g_stair_pending = 0;
    apply_gates(0);
}

/* 100 us tick */
void profile_tick(void)
{
    g_t_us += 100u;
    /* staircase */
    if (g_stair_pending && (int32_t)(g_t_us - g_stair_next_us) >= 0) {
        int i = g_stair_order[g_stair_i];
        uint8_t m = g_gates;
        if ((g_stair_target >> i) & 1) m |= (uint8_t)(1u << i); else m &= (uint8_t)~(1u << i);
        apply_gates(m);
        g_stair_next_us += g_stair_dt_us;
        if (++g_stair_i >= g_stair_n) g_stair_pending = 0;
    }
    if (!g_running || g_stair_pending) return;
    /* two-tier cadence */
    uint32_t T1 = (uint32_t)(g_cfg.T1_s * 1e6f), T_high = (uint32_t)(g_cfg.T1_s * g_cfg.duty1 * 1e6f);
    uint32_t T2 = (uint32_t)(g_cfg.T2_s * 1e6f);
    uint32_t t_in = g_t_us - g_iter_start_us;
    if (t_in >= T1) {                                        /* new iteration: low phase starts (falling edge) */
        g_iter++; g_iter_start_us = g_t_us; t_in = 0; g_phase_high = 0; g_in_burst = 0;
        int idle = g_cfg.idle_drop_every && (g_iter % g_cfg.idle_drop_every) == 0;
        profile_step(idle ? 0.0f : g_cfg.P_low, g_cfg.ramp_ms);
        /* jitter the next rising edge by up to 5 % of T1 (the model's jit1) */
        g_next_edge_us = g_iter_start_us + (T1 - T_high) + (uint32_t)rngf(0.0f, 0.05f * (float)T1);
        fault_schedule_notify(g_next_edge_us);
        return;
    }
    if (!g_phase_high && (int32_t)(g_t_us - g_next_edge_us) >= 0) {   /* rising edge: compute phase */
        g_phase_high = 1;
        sync_pulse();                                                 /* every scheduled event gets a SYNC */
        profile_step(g_cfg.P_high, rngf(0.5f, 20.0f));
        g_next_burst_us = g_t_us + T2;
        return;
    }
    if (g_phase_high && T2 > 0 && g_cfg.burst_frac > 0.0f && (int32_t)(g_t_us - g_next_burst_us) >= 0) {
        g_in_burst = !g_in_burst;
        profile_step(g_in_burst ? g_cfg.P_high + g_cfg.burst_frac : g_cfg.P_high, g_cfg.ramp_ms);
        g_next_burst_us += T2 / 2u;                                 /* 50 % burst duty */
    }
}
