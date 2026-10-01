#include "cli.h"
#include "board.h"
#include "settings.h"
#include "stream.h"
#include "timing.h"
#include "trip.h"
#include "adc_dma.h"
#include "cadence_task.h"
#include "can_link.h"
#include "usb_upload.h"
#include "fx_config.h"
#include "fx_model.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

UART_HandleTypeDef huart3;
DMA_HandleTypeDef hdma_usart3_rx;

#define RX_RING 4096
#define LINE_MAX 160
#define BLOB_MAX (FX_REC_HEADER_BYTES + 4 * FX_N_REC_MAX)      /* one FXR1 record without slow streams */

__attribute__((section(".ram_d2"), aligned(32))) static uint8_t rx_ring[RX_RING];
__attribute__((section(".ram_d2"))) static uint8_t blob[BLOB_MAX];
static uint32_t rx_tail;
static char line[LINE_MAX];
static int line_len;
static uint32_t blob_expect, blob_len;
static char blob_event[16];

static void fatal(void) { for (;;) { } }

void cli_puts(const char *s)
{
    HAL_UART_Transmit(&huart3, (const uint8_t *)s, (uint16_t)strlen(s), 1000);
}

void cli_init(void)
{
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_USART3_CLK_ENABLE();
    __HAL_RCC_DMA1_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Pin = CONSOLE_TX_PIN | CONSOLE_RX_PIN; io.Mode = GPIO_MODE_AF_PP; io.Pull = GPIO_NOPULL;
    io.Speed = GPIO_SPEED_FREQ_LOW; io.Alternate = CONSOLE_AF;
    HAL_GPIO_Init(CONSOLE_TX_GPIO, &io);

    huart3.Instance = CONSOLE_USART;
    huart3.Init.BaudRate = CONSOLE_BAUD;
    huart3.Init.WordLength = UART_WORDLENGTH_8B;
    huart3.Init.StopBits = UART_STOPBITS_1;
    huart3.Init.Parity = UART_PARITY_NONE;
    huart3.Init.Mode = UART_MODE_TX_RX;
    huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart3.Init.OverSampling = UART_OVERSAMPLING_16;
    huart3.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    huart3.Init.ClockPrescaler = UART_PRESCALER_DIV1;
    huart3.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_UART_Init(&huart3) != HAL_OK) fatal();

    hdma_usart3_rx.Instance = CONSOLE_RX_DMA;
    hdma_usart3_rx.Init.Request = CONSOLE_RX_DMA_REQ;
    hdma_usart3_rx.Init.Direction = DMA_PERIPH_TO_MEMORY;
    hdma_usart3_rx.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_usart3_rx.Init.MemInc = DMA_MINC_ENABLE;
    hdma_usart3_rx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
    hdma_usart3_rx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    hdma_usart3_rx.Init.Mode = DMA_CIRCULAR;
    hdma_usart3_rx.Init.Priority = DMA_PRIORITY_LOW;
    hdma_usart3_rx.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
    if (HAL_DMA_Init(&hdma_usart3_rx) != HAL_OK) fatal();
    __HAL_LINKDMA(&huart3, hdmarx, hdma_usart3_rx);
    HAL_NVIC_SetPriority(CONSOLE_RX_DMA_IRQn, PRIO_CONSOLE_DMA, 0);
    HAL_NVIC_EnableIRQ(CONSOLE_RX_DMA_IRQn);
    HAL_NVIC_SetPriority(USART3_IRQn, PRIO_CONSOLE_DMA, 0);
    HAL_NVIC_EnableIRQ(USART3_IRQn);
    if (HAL_UART_Receive_DMA(&huart3, rx_ring, RX_RING) != HAL_OK) fatal();
    rx_tail = 0; line_len = 0; blob_expect = 0; blob_len = 0;
    cli_puts("\r\nfx node ready\r\n");
}

/* bytes written by the DMA so far: RX_RING - remaining counter */
static uint32_t rx_head(void)
{
    return (RX_RING - __HAL_DMA_GET_COUNTER(&hdma_usart3_rx)) & (RX_RING - 1);
}

static void print_status(void)
{
    char b[200];
    const decision_t *d = stream_last();
    snprintf(b, sizeof b, "samples %lu armed %d overruns %lu sysclk %lu\r\n", (unsigned long)stream_sample_count(),
             stream_detector_armed(), (unsigned long)adc_dma_overruns(), (unsigned long)HAL_RCC_GetSysClockFreq());
    cli_puts(b);
    if (d->valid) {
        snprintf(b, sizeof b, "last: layer %lu k_on %lu decision %s p_trip %.6f sync_sample %lu\r\n", (unsigned long)d->layer,
                 (unsigned long)d->k_on, fx_decision_name(d->r.decision), d->r.p_trip, (unsigned long)d->sync_sample);
        cli_puts(b);
        snprintf(b, sizeof b, "  cycles: extract %lu (%.1f us) infer %lu (%.1f us) close->trip %lu (%.1f us) onset->trip %lu (%.1f us)\r\n",
                 (unsigned long)d->cyc_extract, cycles_to_us(d->cyc_extract), (unsigned long)d->cyc_infer, cycles_to_us(d->cyc_infer),
                 (unsigned long)d->cyc_close_to_trip, cycles_to_us(d->cyc_close_to_trip),
                 (unsigned long)d->cyc_onset_to_trip, cycles_to_us(d->cyc_onset_to_trip));
        cli_puts(b);
        double x[FX_N_FEATURES];
        fx_features_vector(&d->f, x);
        for (int k = 0; k < FX_N_FEATURES; ++k) {
            snprintf(b, sizeof b, "  %s=%.9g", fx_feature_names[k], x[k]);
            cli_puts(b);
            if (k % 4 == 3) cli_puts("\r\n");
        }
        cli_puts("\r\n");
    } else {
        cli_puts("last: none\r\n");
    }
}

static void print_timing(void)
{
    char b[160];
    cli_puts("stage          n       mean_us    p99_us    max_us\r\n");
    for (int i = 0; i < T_COUNT; ++i) {
        const timing_stat_t *s = timing_get((timing_id_t)i);
        double mean = s->n ? (double)(s->sum / s->n) : 0.0;
        snprintf(b, sizeof b, "%-13s %8lu %10.2f %9.2f %9.2f\r\n", timing_name((timing_id_t)i), (unsigned long)s->n,
                 cycles_to_us((uint32_t)mean), cycles_to_us(timing_p99((timing_id_t)i)), s->n ? cycles_to_us(s->max) : 0.0);
        cli_puts(b);
    }
}

static void selftest(void)
{
    /* a synthetic step through the record-mode path (the host test_units check) on the stream's
     * own record buffers; the detector is paused meanwhile */
    fx_features_t f;
    uint32_t cycles;
    int rc = stream_selftest(&f, &cycles);
    int ok = rc == 0 && f.onset.k_on == 400 && fabs(f.di_end - 0.2) < 1e-12 && fabs(f.v_min - 0.99) < 1e-12;
    char b[160];
    snprintf(b, sizeof b, "selftest %s: k_on %d di_end %.12g v_min %.12g extract %lu cycles (%.1f us); models %d, node size %u\r\n",
             ok ? "PASS" : "FAIL", f.onset.k_on, f.di_end, f.v_min, (unsigned long)cycles, cycles_to_us(cycles),
             fx_model_count(), (unsigned)sizeof(fx_node_t));
    cli_puts(b);
}

static void handle_line(char *l)
{
    char *cmd = strtok(l, " \t");
    if (!cmd) return;
    if (!strcmp(cmd, "status")) print_status();
    else if (!strcmp(cmd, "timing")) print_timing();
    else if (!strcmp(cmd, "timing_reset")) { timing_reset(); cli_puts("ok\r\n"); }
    else if (!strcmp(cmd, "arm")) { stream_arm(); cli_puts("armed\r\n"); }
    else if (!strcmp(cmd, "selftest")) selftest();
    else if (!strcmp(cmd, "capture")) { stream_capture_request(); cli_puts("capture queued (USB CDC)\r\n"); }
    else if (!strcmp(cmd, "cadence")) {
        uint32_t gen; const fx_cadence_tiers_t *t = cadence_published(&gen);
        char b[160];
        snprintf(b, sizeof b, "relearns %lu history %lu samples last %lu cycles (%.1f ms) generation %lu\r\n",
                 (unsigned long)cadence_relearns(), (unsigned long)cadence_history_count(), (unsigned long)cadence_last_cycles(),
                 cycles_to_us(cadence_last_cycles()) * 1e-3, (unsigned long)gen);
        cli_puts(b);
        if (t) for (int i = 0; i < t->n_tiers; ++i) {
            snprintf(b, sizeof b, "  tier %d: T %.6f s strength %.4f edges %d%s\r\n", i + 1, t->tier[i].T, t->tier[i].strength,
                     t->tier[i].n_edges, t->tier[i].is_tier2 ? " (tier 2)" : "");
            cli_puts(b);
        } else cli_puts("  no tiers published\r\n");
    } else if (!strcmp(cmd, "can")) {
        char b[160]; fx_can_summary_t s; uint32_t rx;
        snprintf(b, sizeof b, "rx frames %lu tx errors %lu usb %s bytes %lu\r\n", (unsigned long)can_rx_count(), (unsigned long)can_tx_errors(),
                 usb_upload_connected() ? "connected" : "idle", (unsigned long)usb_upload_bytes());
        cli_puts(b);
        if (can_peer_summary(&s, &rx)) {
            snprintf(b, sizeof b, "  peer: node %u decision %u p_trip %.4f phase_err %.4f onset %lu rx@%lu\r\n", s.node, s.decision,
                     (double)s.p_trip, (double)s.phase_err, (unsigned long)s.onset_sample, (unsigned long)rx);
            cli_puts(b);
        }
    }
    else if (!strcmp(cmd, "settings")) {
        char *sub = strtok(NULL, " \t");
        if (!sub || !strcmp(sub, "show")) settings_print(cli_puts);
        else if (!strcmp(sub, "set")) {
            char *k = strtok(NULL, " \t"), *v = strtok(NULL, " \t");
            if (k && v && settings_set(k, v) == 0) { stream_init(); cli_puts("ok (not saved)\r\n"); }
            else cli_puts("usage: settings set <key> <value>\r\n");
        } else if (!strcmp(sub, "save")) cli_puts(settings_save() == 0 ? "saved\r\n" : "flash error\r\n");
        else if (!strcmp(sub, "defaults")) { settings_defaults(&g_set, role_is_rack()); stream_init(); cli_puts("defaults loaded (not saved)\r\n"); }
        else cli_puts("usage: settings show|set|save|defaults\r\n");
    } else if (!strcmp(cmd, "replay")) {
        /* replay <event> <nbytes>\n followed by nbytes of an FXR1 record (slow streams stripped) */
        char *ev = strtok(NULL, " \t"), *nb = strtok(NULL, " \t");
        uint32_t n = nb ? (uint32_t)strtoul(nb, NULL, 10) : 0;
        if (!ev || n < FX_REC_HEADER_BYTES || n > BLOB_MAX) { cli_puts("usage: replay <event> <nbytes>\r\n"); return; }
        strncpy(blob_event, ev, sizeof blob_event - 1); blob_event[sizeof blob_event - 1] = 0;
        blob_expect = n; blob_len = 0;
        cli_puts("send\r\n");
    } else if (!strcmp(cmd, "reset")) NVIC_SystemReset();
    else cli_puts("commands: status timing timing_reset arm selftest capture cadence can settings replay reset\r\n");
}

static void handle_blob(void)
{
    static const double W[3] = { FX_W_025, FX_W_050, FX_W_100 };
    int rc = stream_replay(blob, blob_len, W, 3, cli_puts);
    if (rc != 0) { char b[48]; snprintf(b, sizeof b, "replay error %d\r\n", rc); cli_puts(b); }
    else cli_puts("end\r\n");
}

void cli_poll(void)
{
    uint32_t head = rx_head();
    while (rx_tail != head) {
        uint8_t ch = rx_ring[rx_tail];
        rx_tail = (rx_tail + 1) & (RX_RING - 1);
        if (blob_expect) {
            blob[blob_len++] = ch;
            if (blob_len >= blob_expect) { blob_expect = 0; handle_blob(); }
            continue;
        }
        if (ch == '\r' || ch == '\n') {
            if (line_len) { line[line_len] = 0; handle_line(line); line_len = 0; }
        } else if (line_len < LINE_MAX - 1) {
            line[line_len++] = (char)ch;
        } else {
            line_len = 0;
        }
    }
}
