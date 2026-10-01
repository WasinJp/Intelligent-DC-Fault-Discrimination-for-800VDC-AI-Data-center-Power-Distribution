#include "uvlo.h"
#include "board_bc.h"
#include "profile.h"

ADC_HandleTypeDef hadc1_uvlo;
DMA_HandleTypeDef hdma_uvlo;
TIM_HandleTypeDef htim6_uvlo;
__attribute__((section(".ram_d2"), aligned(32))) static uint16_t g_buf[2 * UVLO_BLOCK];

static float g_v_off, g_v_on, g_vpc;
static uint32_t g_hold_n, g_below_n;
static volatile int g_tripped, g_enabled;
static volatile uint32_t g_trips;
static volatile uint16_t g_last_code;
static uint8_t g_saved_gates;

static void fatal(void) { for (;;) { } }

void uvlo_init(float v_off, float v_on, float volts_per_code, uint32_t hold_us)
{
    g_v_off = v_off; g_v_on = v_on; g_vpc = volts_per_code;
    g_hold_n = hold_us * UVLO_FS_HZ / 1000000u; g_below_n = 0; g_tripped = 0; g_enabled = 1;
    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Pin = UVLO_ADC_PIN; io.Mode = GPIO_MODE_ANALOG; io.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(UVLO_ADC_GPIO, &io);
    /* TIM6 TRGO at 1 MHz */
    __HAL_RCC_TIM6_CLK_ENABLE();
    htim6_uvlo.Instance = TIM6;
    htim6_uvlo.Init.Prescaler = 0;
    htim6_uvlo.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim6_uvlo.Init.Period = BOARD_TIMCLK_HZ / UVLO_FS_HZ - 1u;
    htim6_uvlo.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_Base_Init(&htim6_uvlo) != HAL_OK) fatal();
    TIM_MasterConfigTypeDef m = { 0 };
    m.MasterOutputTrigger = TIM_TRGO_UPDATE; m.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
    HAL_TIMEx_MasterConfigSynchronization(&htim6_uvlo, &m);
    /* ADC1 single channel, 16-bit, DMA circular */
    __HAL_RCC_ADC12_CLK_ENABLE(); __HAL_RCC_DMA1_CLK_ENABLE();
    hadc1_uvlo.Instance = ADC1;
    hadc1_uvlo.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV2;
    hadc1_uvlo.Init.Resolution = ADC_RESOLUTION_16B;
    hadc1_uvlo.Init.ScanConvMode = ADC_SCAN_DISABLE;
    hadc1_uvlo.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
    hadc1_uvlo.Init.LowPowerAutoWait = DISABLE;
    hadc1_uvlo.Init.ContinuousConvMode = DISABLE;
    hadc1_uvlo.Init.NbrOfConversion = 1;
    hadc1_uvlo.Init.DiscontinuousConvMode = DISABLE;
    hadc1_uvlo.Init.ExternalTrigConv = ADC_EXTERNALTRIG_T6_TRGO;
    hadc1_uvlo.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_RISING;
    hadc1_uvlo.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DMA_CIRCULAR;
    hadc1_uvlo.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
    hadc1_uvlo.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
    hadc1_uvlo.Init.OversamplingMode = DISABLE;
    if (HAL_ADC_Init(&hadc1_uvlo) != HAL_OK) fatal();
    ADC_ChannelConfTypeDef ch = { 0 };
    ch.Channel = UVLO_ADC_CHANNEL; ch.Rank = ADC_REGULAR_RANK_1; ch.SamplingTime = ADC_SAMPLETIME_8CYCLES_5;
    ch.SingleDiff = ADC_SINGLE_ENDED; ch.OffsetNumber = ADC_OFFSET_NONE; ch.Offset = 0;
    if (HAL_ADC_ConfigChannel(&hadc1_uvlo, &ch) != HAL_OK) fatal();
    HAL_ADCEx_Calibration_Start(&hadc1_uvlo, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED);
    hdma_uvlo.Instance = DMA1_Stream0;
    hdma_uvlo.Init.Request = DMA_REQUEST_ADC1;
    hdma_uvlo.Init.Direction = DMA_PERIPH_TO_MEMORY;
    hdma_uvlo.Init.PeriphInc = DMA_PINC_DISABLE; hdma_uvlo.Init.MemInc = DMA_MINC_ENABLE;
    hdma_uvlo.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD; hdma_uvlo.Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;
    hdma_uvlo.Init.Mode = DMA_CIRCULAR; hdma_uvlo.Init.Priority = DMA_PRIORITY_VERY_HIGH; hdma_uvlo.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
    if (HAL_DMA_Init(&hdma_uvlo) != HAL_OK) fatal();
    __HAL_LINKDMA(&hadc1_uvlo, DMA_Handle, hdma_uvlo);
    HAL_NVIC_SetPriority(DMA1_Stream0_IRQn, PRIO_UVLO_DMA, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream0_IRQn);
    if (HAL_ADC_Start_DMA(&hadc1_uvlo, (uint32_t *)g_buf, 2 * UVLO_BLOCK) != HAL_OK) fatal();
    HAL_TIM_Base_Start(&htim6_uvlo);
}

void uvlo_set(float v_off, float v_on) { g_v_off = v_off; g_v_on = v_on; }
void uvlo_enable(int on) { g_enabled = on; }
int uvlo_tripped(void) { return g_tripped; }
uint32_t uvlo_trips(void) { return g_trips; }
float uvlo_last_volts(void) { return (float)g_last_code * g_vpc; }

void uvlo_on_block(const uint16_t *codes, int n)
{
    for (int k = 0; k < n; ++k) {
        float v = (float)codes[k] * g_vpc;
        g_last_code = codes[k];
        if (!g_enabled) continue;
        if (!g_tripped) {
            if (v < g_v_off) { if (++g_below_n >= g_hold_n) { g_saved_gates = profile_gates_now(); profile_gates(0); g_tripped = 1; g_trips++; } }
            else g_below_n = 0;
        } else if (v > g_v_on) {
            g_tripped = 0; g_below_n = 0;
            profile_gates(g_saved_gates);
        }
    }
}

static void deliver(const uint16_t *half)
{
    SCB_InvalidateDCache_by_Addr((uint32_t *)half, UVLO_BLOCK * 2);
    uvlo_on_block(half, UVLO_BLOCK);
}
void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *h) { (void)h; deliver(g_buf); }
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *h) { (void)h; deliver(g_buf + UVLO_BLOCK); }
