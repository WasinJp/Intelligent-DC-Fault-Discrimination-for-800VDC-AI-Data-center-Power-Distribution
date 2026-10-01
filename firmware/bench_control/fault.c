#include "fault.h"
#include "board_bc.h"
#include "profile.h"

static const uint16_t sel_r[3] = SEL_R_PINS, sel_l[3] = SEL_L_PINS, sel_fr[2] = SEL_FEEDER_R_PINS;
static volatile int g_sched_kind = -1;
static volatile uint32_t g_sched_t_us, g_last_trigger_us, g_count;
static volatile uint32_t g_next_edge_us;

static void out(GPIO_TypeDef *g, uint16_t pin)
{
    GPIO_InitTypeDef io = { 0 };
    io.Pin = pin; io.Mode = GPIO_MODE_OUTPUT_PP; io.Pull = GPIO_NOPULL; io.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(g, &io);
    HAL_GPIO_WritePin(g, pin, GPIO_PIN_RESET);
}

void fault_init(void)
{
    __HAL_RCC_GPIOE_CLK_ENABLE(); __HAL_RCC_GPIOF_CLK_ENABLE(); __HAL_RCC_GPIOG_CLK_ENABLE();
    out(FAULT_RACK_GPIO, FAULT_RACK_PIN);
    out(FAULT_FEEDER_GPIO, FAULT_FEEDER_PIN);
    out(SYNC_GPIO, SYNC_PIN);
    for (int i = 0; i < 3; ++i) { out(SEL_GPIO, sel_r[i]); out(SEL_GPIO, sel_l[i]); }
    for (int i = 0; i < 2; ++i) out(SEL_GPIO, sel_fr[i]);
    GPIO_InitTypeDef io = { 0 };
    io.Pin = ARM_SENSE_PIN; io.Mode = GPIO_MODE_INPUT; io.Pull = GPIO_PULLDOWN;
    HAL_GPIO_Init(ARM_SENSE_GPIO, &io);
}

int fault_armed(void) { return HAL_GPIO_ReadPin(ARM_SENSE_GPIO, ARM_SENSE_PIN) == GPIO_PIN_SET; }

int fault_select_rack(int r_sel, int l_sel)
{
    if (r_sel > 2 || l_sel > 2) return -1;
    for (int i = 0; i < 3; ++i) {
        HAL_GPIO_WritePin(SEL_GPIO, sel_r[i], i == r_sel ? GPIO_PIN_SET : GPIO_PIN_RESET);
        HAL_GPIO_WritePin(SEL_GPIO, sel_l[i], i == l_sel ? GPIO_PIN_SET : GPIO_PIN_RESET);
    }
    return 0;
}

int fault_select_feeder(int r_sel)
{
    if (r_sel > 1) return -1;
    for (int i = 0; i < 2; ++i) HAL_GPIO_WritePin(SEL_GPIO, sel_fr[i], i == r_sel ? GPIO_PIN_SET : GPIO_PIN_RESET);
    return 0;
}

static void pulse(GPIO_TypeDef *g, uint16_t pin, uint32_t us)
{
    g->BSRR = pin;
    uint32_t t0 = DWT->CYCCNT;
    while (DWT->CYCCNT - t0 < us * 480u) { }
    g->BSRR = (uint32_t)pin << 16;
}

void sync_pulse(void) { pulse(SYNC_GPIO, SYNC_PIN, SYNC_PULSE_US); }

int fault_trigger_now(int kind)
{
    if (!fault_armed()) return -1;                          /* the key switch also blocks it in hardware */
    sync_pulse();
    if (kind == 0) pulse(FAULT_RACK_GPIO, FAULT_RACK_PIN, 5);
    else pulse(FAULT_FEEDER_GPIO, FAULT_FEEDER_PIN, 5);     /* 5 us edge for the one-shot */
    g_last_trigger_us = profile_time_us();
    g_count++;
    return 0;
}

int fault_schedule(int kind, uint32_t t_us)
{
    if (!fault_armed()) return -1;
    g_sched_kind = kind; g_sched_t_us = t_us;
    return 0;
}

void fault_cancel(void) { g_sched_kind = -1; }
void fault_schedule_notify(uint32_t next_edge_us) { g_next_edge_us = next_edge_us; }
uint32_t fault_last_trigger_us(void) { return g_last_trigger_us; }
uint32_t fault_count(void) { return g_count; }

void fault_tick(void)
{
    if (g_sched_kind < 0) return;
    if ((int32_t)(profile_time_us() - g_sched_t_us) >= 0) {
        int k = g_sched_kind;
        g_sched_kind = -1;
        fault_trigger_now(k);
    }
}
