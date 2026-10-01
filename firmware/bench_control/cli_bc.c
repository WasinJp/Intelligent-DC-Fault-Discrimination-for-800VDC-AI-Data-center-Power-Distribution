/* cli_bc.c — bench-control console on the ST-Link VCP (USB serial), FIRMWARE_SPEC.md §10.
 * Text commands, one per line; tools/bench_run.py drives them. */
#include "board_bc.h"
#include "profile.h"
#include "fault.h"
#include "uvlo.h"
#include "dac_replay.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

UART_HandleTypeDef huart3;
DMA_HandleTypeDef hdma_usart3_rx;
#define RX_RING 4096
#define LINE_MAX 160
__attribute__((section(".ram_d2"), aligned(32))) static uint8_t rx_ring[RX_RING];
static uint32_t rx_tail;
static char line[LINE_MAX];
static int line_len;
static uint32_t blob_expect, blob_len;
static uint8_t *blob_dst;

static void fatal(void) { for (;;) { } }

void cli_puts(const char *s) { HAL_UART_Transmit(&huart3, (const uint8_t *)s, (uint16_t)strlen(s), 1000); }

void cli_init(void)
{
    __HAL_RCC_GPIOD_CLK_ENABLE(); __HAL_RCC_USART3_CLK_ENABLE(); __HAL_RCC_DMA1_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Pin = CONSOLE_TX_PIN | CONSOLE_RX_PIN; io.Mode = GPIO_MODE_AF_PP; io.Pull = GPIO_NOPULL;
    io.Speed = GPIO_SPEED_FREQ_LOW; io.Alternate = CONSOLE_AF;
    HAL_GPIO_Init(CONSOLE_TX_GPIO, &io);
    huart3.Instance = CONSOLE_USART;
    huart3.Init.BaudRate = CONSOLE_BAUD; huart3.Init.WordLength = UART_WORDLENGTH_8B; huart3.Init.StopBits = UART_STOPBITS_1;
    huart3.Init.Parity = UART_PARITY_NONE; huart3.Init.Mode = UART_MODE_TX_RX; huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart3.Init.OverSampling = UART_OVERSAMPLING_16; huart3.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    huart3.Init.ClockPrescaler = UART_PRESCALER_DIV1; huart3.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_UART_Init(&huart3) != HAL_OK) fatal();
    hdma_usart3_rx.Instance = CONSOLE_RX_DMA; hdma_usart3_rx.Init.Request = CONSOLE_RX_DMA_REQ;
    hdma_usart3_rx.Init.Direction = DMA_PERIPH_TO_MEMORY; hdma_usart3_rx.Init.PeriphInc = DMA_PINC_DISABLE; hdma_usart3_rx.Init.MemInc = DMA_MINC_ENABLE;
    hdma_usart3_rx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE; hdma_usart3_rx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    hdma_usart3_rx.Init.Mode = DMA_CIRCULAR; hdma_usart3_rx.Init.Priority = DMA_PRIORITY_LOW; hdma_usart3_rx.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
    if (HAL_DMA_Init(&hdma_usart3_rx) != HAL_OK) fatal();
    __HAL_LINKDMA(&huart3, hdmarx, hdma_usart3_rx);
    HAL_NVIC_SetPriority(CONSOLE_RX_DMA_IRQn, PRIO_CONSOLE_DMA, 0); HAL_NVIC_EnableIRQ(CONSOLE_RX_DMA_IRQn);
    HAL_NVIC_SetPriority(USART3_IRQn, PRIO_CONSOLE_DMA, 0); HAL_NVIC_EnableIRQ(USART3_IRQn);
    if (HAL_UART_Receive_DMA(&huart3, rx_ring, RX_RING) != HAL_OK) fatal();
    rx_tail = 0; line_len = 0; blob_expect = 0;
    cli_puts("\r\nfx bench_control ready\r\n");
}

static uint32_t rx_head(void) { return (RX_RING - __HAL_DMA_GET_COUNTER(&hdma_usart3_rx)) & (RX_RING - 1); }

static void status(void)
{
    char b[200];
    const profile_cfg_t *c = profile_cfg();
    snprintf(b, sizeof b, "t %lu us running %d gates 0x%02x armed %d faults %lu last_trigger %lu uvlo %s trips %lu v_out %.3f replays %lu busy %d\r\n",
             (unsigned long)profile_time_us(), profile_running(), profile_gates_now(), fault_armed(), (unsigned long)fault_count(),
             (unsigned long)fault_last_trigger_us(), uvlo_tripped() ? "TRIPPED" : "ok", (unsigned long)uvlo_trips(),
             (double)uvlo_last_volts(), (unsigned long)replay_count(), replay_busy());
    cli_puts(b);
    snprintf(b, sizeof b, "profile: seed %lu T1 %.3f duty %.2f T2 %.3f burst %.2f P_low %.2f P_high %.2f ramp %.1f ms idle_every %lu\r\n",
             (unsigned long)c->seed, (double)c->T1_s, (double)c->duty1, (double)c->T2_s, (double)c->burst_frac, (double)c->P_low,
             (double)c->P_high, (double)c->ramp_ms, (unsigned long)c->idle_drop_every);
    cli_puts(b);
}

static void handle(char *l)
{
    char *cmd = strtok(l, " \t");
    if (!cmd) return;
    char b[96];
    if (!strcmp(cmd, "status")) status();
    else if (!strcmp(cmd, "profile")) {
        char *sub = strtok(NULL, " \t");
        if (!sub) { cli_puts("usage: profile start|stop|set <key> <v>|step <frac> <ramp_ms>|gates <mask>\r\n"); return; }
        if (!strcmp(sub, "start")) { profile_start(); cli_puts("profile running\r\n"); }
        else if (!strcmp(sub, "stop")) { profile_stop(); cli_puts("profile stopped\r\n"); }
        else if (!strcmp(sub, "set")) {
            char *k = strtok(NULL, " \t"), *v = strtok(NULL, " \t");
            if (!k || !v) { cli_puts("usage: profile set <key> <value>\r\n"); return; }
            profile_cfg_t c = *profile_cfg();
            float f = (float)atof(v);
            if (!strcmp(k, "seed")) c.seed = (uint32_t)strtoul(v, NULL, 0);
            else if (!strcmp(k, "T1")) c.T1_s = f; else if (!strcmp(k, "duty")) c.duty1 = f;
            else if (!strcmp(k, "T2")) c.T2_s = f; else if (!strcmp(k, "burst")) c.burst_frac = f;
            else if (!strcmp(k, "P_low")) c.P_low = f; else if (!strcmp(k, "P_high")) c.P_high = f;
            else if (!strcmp(k, "ramp")) c.ramp_ms = f; else if (!strcmp(k, "idle_every")) c.idle_drop_every = (uint32_t)atoi(v);
            else { cli_puts("unknown key\r\n"); return; }
            profile_set(&c); cli_puts("ok\r\n");
        } else if (!strcmp(sub, "step")) {
            char *f = strtok(NULL, " \t"), *r = strtok(NULL, " \t");
            if (!f) { cli_puts("usage: profile step <frac 0..1> [ramp_ms]\r\n"); return; }
            sync_pulse();
            profile_step((float)atof(f), r ? (float)atof(r) : profile_cfg()->ramp_ms);
            snprintf(b, sizeof b, "step to mask 0x%02x\r\n", profile_mask_for((float)atof(f))); cli_puts(b);
        } else if (!strcmp(sub, "gates")) {
            char *m = strtok(NULL, " \t");
            profile_gates(m ? (uint8_t)strtoul(m, NULL, 0) : 0); cli_puts("ok\r\n");
        }
    } else if (!strcmp(cmd, "fault")) {
        /* fault rack <r_sel> <l_sel> [at <t_us>|edge <offset_us>|now] ; fault feeder <r_sel> [...] */
        char *who = strtok(NULL, " \t");
        if (!who) { cli_puts("usage: fault rack <r_sel> <l_sel> [now|at <t_us>|edge <offset_us>] | fault feeder <r_sel> [...] | fault cancel\r\n"); return; }
        if (!strcmp(who, "cancel")) { fault_cancel(); cli_puts("cancelled\r\n"); return; }
        if (!fault_armed()) { cli_puts("REFUSED: arm key switch is off\r\n"); return; }
        int kind = !strcmp(who, "feeder");
        char *r = strtok(NULL, " \t");
        if (!r) { cli_puts("missing selector\r\n"); return; }
        if (kind == 0) { char *lsel = strtok(NULL, " \t"); if (!lsel || fault_select_rack(atoi(r), atoi(lsel)) != 0) { cli_puts("bad selector\r\n"); return; } }
        else if (fault_select_feeder(atoi(r)) != 0) { cli_puts("bad selector\r\n"); return; }
        char *when = strtok(NULL, " \t");
        if (!when || !strcmp(when, "now")) { fault_trigger_now(kind); cli_puts("triggered\r\n"); }
        else if (!strcmp(when, "at")) { char *t = strtok(NULL, " \t"); fault_schedule(kind, (uint32_t)strtoul(t ? t : "0", NULL, 10)); cli_puts("scheduled\r\n"); }
        else if (!strcmp(when, "edge")) {
            char *o = strtok(NULL, " \t");
            uint32_t t = profile_next_edge_us() + (uint32_t)(o ? atoi(o) : 0);
            fault_schedule(kind, t);
            snprintf(b, sizeof b, "scheduled at %lu us (next edge %lu)\r\n", (unsigned long)t, (unsigned long)profile_next_edge_us()); cli_puts(b);
        }
    } else if (!strcmp(cmd, "uvlo")) {
        char *sub = strtok(NULL, " \t");
        if (sub && !strcmp(sub, "set")) { char *a = strtok(NULL, " \t"), *c2 = strtok(NULL, " \t"); if (a && c2) { uvlo_set((float)atof(a), (float)atof(c2)); cli_puts("ok\r\n"); } }
        else if (sub && !strcmp(sub, "on")) { uvlo_enable(1); cli_puts("ok\r\n"); }
        else if (sub && !strcmp(sub, "off")) { uvlo_enable(0); cli_puts("ok\r\n"); }
        else { snprintf(b, sizeof b, "uvlo %s trips %lu v %.3f\r\n", uvlo_tripped() ? "TRIPPED" : "ok", (unsigned long)uvlo_trips(), (double)uvlo_last_volts()); cli_puts(b); }
    } else if (!strcmp(cmd, "sync")) { sync_pulse(); cli_puts("sync\r\n"); }
    else if (!strcmp(cmd, "replay")) {
        /* replay load <n_samples>  then 4*n bytes (i u16[n], v u16[n]); replay start */
        char *sub = strtok(NULL, " \t");
        if (sub && !strcmp(sub, "load")) {
            char *n = strtok(NULL, " \t");
            uint32_t ns = n ? (uint32_t)strtoul(n, NULL, 10) : 0;
            if (ns == 0 || ns > REPLAY_MAX_SAMPLES) { cli_puts("bad length\r\n"); return; }
            blob_dst = (uint8_t *)replay_buffer(); blob_expect = ns * 4u; blob_len = 0;
            /* i then v, each ns samples: the host sends i[0..ns) then v[0..ns); place v at offset REPLAY_MAX_SAMPLES */
            cli_puts("send\r\n");
        } else if (sub && !strcmp(sub, "start")) { cli_puts(replay_start() == 0 ? "replaying\r\n" : "replay error\r\n"); }
        else cli_puts("usage: replay load <n> | replay start\r\n");
    } else if (!strcmp(cmd, "reset")) NVIC_SystemReset();
    else cli_puts("commands: status profile fault uvlo sync replay reset\r\n");
}

static void blob_byte(uint8_t ch)
{
    uint32_t ns = blob_expect / 4u;
    uint32_t idx = blob_len / 2u;
    uint16_t *tab = replay_buffer();
    uint32_t pos = idx < ns ? idx : REPLAY_MAX_SAMPLES + (idx - ns);
    if (blob_len & 1u) tab[pos] |= (uint16_t)(ch << 8); else tab[pos] = ch;
    blob_len++;
    if (blob_len >= blob_expect) {
        blob_expect = 0;
        cli_puts(replay_load_done(ns) == 0 ? "loaded\r\n" : "load error\r\n");
    }
}

void cli_poll(void)
{
    uint32_t head = rx_head();
    while (rx_tail != head) {
        uint8_t ch = rx_ring[rx_tail];
        rx_tail = (rx_tail + 1) & (RX_RING - 1);
        if (blob_expect) { blob_byte(ch); continue; }
        if (ch == '\r' || ch == '\n') { if (line_len) { line[line_len] = 0; handle(line); line_len = 0; } }
        else if (line_len < LINE_MAX - 1) line[line_len++] = (char)ch;
        else line_len = 0;
    }
}
