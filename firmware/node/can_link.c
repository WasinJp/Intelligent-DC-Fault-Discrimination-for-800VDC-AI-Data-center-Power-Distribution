#include "can_link.h"
#include "board.h"
#include "stream.h"
#include <string.h>

FDCAN_HandleTypeDef hfdcan1;
static volatile uint32_t g_rx_count, g_tx_err;
static fx_can_summary_t g_peer_sum; static volatile uint32_t g_peer_sum_sample, g_peer_sum_valid;
static fx_can_features_t g_peer_feat; static volatile uint32_t g_peer_feat_sample, g_peer_feat_valid;

static void fatal(void) { for (;;) { } }

void can_init(void)
{
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_FDCAN_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Pin = GPIO_PIN_0 | GPIO_PIN_1; io.Mode = GPIO_MODE_AF_PP; io.Pull = GPIO_NOPULL;
    io.Speed = GPIO_SPEED_FREQ_VERY_HIGH; io.Alternate = GPIO_AF9_FDCAN1;
    HAL_GPIO_Init(GPIOD, &io);

    /* kernel clock: PLL2Q = 50 MHz (clock.c). Nominal 1 Mbit/s = 50 tq: 1 + 37 + 12; data 5 Mbit/s = 10 tq: 1 + 7 + 2 */
    hfdcan1.Instance = FDCAN1;
    hfdcan1.Init.FrameFormat = FDCAN_FRAME_FD_BRS;
    hfdcan1.Init.Mode = FDCAN_MODE_NORMAL;
    hfdcan1.Init.AutoRetransmission = DISABLE;        /* a late frame is useless: §7.3 50 us window */
    hfdcan1.Init.TransmitPause = DISABLE;
    hfdcan1.Init.ProtocolException = DISABLE;
    hfdcan1.Init.NominalPrescaler = 1;
    hfdcan1.Init.NominalSyncJumpWidth = 12;
    hfdcan1.Init.NominalTimeSeg1 = 37;
    hfdcan1.Init.NominalTimeSeg2 = 12;
    hfdcan1.Init.DataPrescaler = 1;
    hfdcan1.Init.DataSyncJumpWidth = 2;
    hfdcan1.Init.DataTimeSeg1 = 7;
    hfdcan1.Init.DataTimeSeg2 = 2;
    hfdcan1.Init.MessageRAMOffset = 0;
    hfdcan1.Init.StdFiltersNbr = 1;
    hfdcan1.Init.ExtFiltersNbr = 0;
    hfdcan1.Init.RxFifo0ElmtsNbr = 8;
    hfdcan1.Init.RxFifo0ElmtSize = FDCAN_DATA_BYTES_64;
    hfdcan1.Init.RxFifo1ElmtsNbr = 0;
    hfdcan1.Init.RxBuffersNbr = 0;
    hfdcan1.Init.TxEventsNbr = 0;
    hfdcan1.Init.TxBuffersNbr = 0;
    hfdcan1.Init.TxFifoQueueElmtsNbr = 4;
    hfdcan1.Init.TxFifoQueueMode = FDCAN_TX_FIFO_OPERATION;
    hfdcan1.Init.TxElmtSize = FDCAN_DATA_BYTES_64;
    if (HAL_FDCAN_Init(&hfdcan1) != HAL_OK) fatal();

    FDCAN_FilterTypeDef f = { 0 };               /* accept every standard id into FIFO 0 */
    f.IdType = FDCAN_STANDARD_ID; f.FilterIndex = 0; f.FilterType = FDCAN_FILTER_RANGE;
    f.FilterConfig = FDCAN_FILTER_TO_RXFIFO0; f.FilterID1 = 0x000; f.FilterID2 = 0x7FF;
    if (HAL_FDCAN_ConfigFilter(&hfdcan1, &f) != HAL_OK) fatal();
    HAL_FDCAN_ConfigGlobalFilter(&hfdcan1, FDCAN_REJECT, FDCAN_REJECT, FDCAN_FILTER_REMOTE, FDCAN_FILTER_REMOTE);
    HAL_NVIC_SetPriority(FDCAN1_IT0_IRQn, PRIO_SYNC, 0);
    HAL_NVIC_EnableIRQ(FDCAN1_IT0_IRQn);
    if (HAL_FDCAN_ActivateNotification(&hfdcan1, FDCAN_IT_RX_FIFO0_NEW_MESSAGE, 0) != HAL_OK) fatal();
    if (HAL_FDCAN_Start(&hfdcan1) != HAL_OK) fatal();
}

static int send(uint32_t id, const uint8_t *data, uint32_t dlc_code)
{
    FDCAN_TxHeaderTypeDef h = { 0 };
    h.Identifier = id; h.IdType = FDCAN_STANDARD_ID; h.TxFrameType = FDCAN_DATA_FRAME;
    h.DataLength = dlc_code; h.ErrorStateIndicator = FDCAN_ESI_ACTIVE; h.BitRateSwitch = FDCAN_BRS_ON;
    h.FDFormat = FDCAN_FD_CAN; h.TxEventFifoControl = FDCAN_NO_TX_EVENTS; h.MessageMarker = 0;
    if (HAL_FDCAN_AddMessageToTxFifoQ(&hfdcan1, &h, (uint8_t *)data) != HAL_OK) { g_tx_err++; return -1; }
    return 0;
}

int can_send_summary(const fx_can_summary_t *s)
{
    uint8_t b[FX_CAN_SUMMARY_BYTES];
    fx_can_encode_summary(s, b);
    return send(s->node ? FX_CAN_ID_SUMMARY_RACK : FX_CAN_ID_SUMMARY_FEEDER, b, FDCAN_DLC_BYTES_16);
}

int can_send_features(const fx_can_features_t *f)
{
    uint8_t b[FX_CAN_FEATURE_PARTS][FX_CAN_FEATURE_BYTES];
    fx_can_encode_features(f, b);
    int rc = 0;
    for (int p = 0; p < FX_CAN_FEATURE_PARTS; ++p)
        rc |= send(f->node ? FX_CAN_ID_FEATURES_RACK : FX_CAN_ID_FEATURES_FEEDER, b[p], FDCAN_DLC_BYTES_64);
    return rc;
}

void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef *h, uint32_t its)
{
    if (!(its & FDCAN_IT_RX_FIFO0_NEW_MESSAGE)) return;
    FDCAN_RxHeaderTypeDef rh;
    static uint8_t data[64];
    while (HAL_FDCAN_GetRxFifoFillLevel(h, FDCAN_RX_FIFO0) > 0) {
        if (HAL_FDCAN_GetRxMessage(h, FDCAN_RX_FIFO0, &rh, data) != HAL_OK) break;
        g_rx_count++;
        uint32_t now = stream_sample_count();
        if (rh.Identifier == FX_CAN_ID_SUMMARY_FEEDER || rh.Identifier == FX_CAN_ID_SUMMARY_RACK) {
            fx_can_summary_t s;
            if (fx_can_decode_summary(data, &s) == 0) { g_peer_sum = s; g_peer_sum_sample = now; g_peer_sum_valid = 1; }
        } else if (rh.Identifier == FX_CAN_ID_FEATURES_FEEDER || rh.Identifier == FX_CAN_ID_FEATURES_RACK) {
            static fx_can_features_t acc;
            int done = fx_can_decode_feature_part(data, &acc);
            if (done == 1) { g_peer_feat = acc; g_peer_feat_sample = now; g_peer_feat_valid = 1; acc.parts_mask = 0; }
        }
    }
}

int can_peer_summary(fx_can_summary_t *s, uint32_t *rx_sample)
{
    if (!g_peer_sum_valid) return 0;
    *s = g_peer_sum; *rx_sample = g_peer_sum_sample; return 1;
}

int can_peer_features(fx_can_features_t *f, uint32_t *rx_sample)
{
    if (!g_peer_feat_valid) return 0;
    *f = g_peer_feat; *rx_sample = g_peer_feat_sample; return 1;
}

uint32_t can_rx_count(void) { return g_rx_count; }
uint32_t can_tx_errors(void) { return g_tx_err; }
