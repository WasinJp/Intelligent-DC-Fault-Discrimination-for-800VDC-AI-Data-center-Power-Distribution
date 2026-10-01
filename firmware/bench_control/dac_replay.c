#include "dac_replay.h"
#include "board_bc.h"
#include "fault.h"
#include <string.h>

DAC_HandleTypeDef hdac1;
DMA_HandleTypeDef hdma_dac;
TIM_HandleTypeDef htim7_dac;
__attribute__((section(".ram_d2"))) static uint16_t g_table[2 * REPLAY_MAX_SAMPLES];
__attribute__((section(".ram_d2"), aligned(32))) static uint32_t g_dual[REPLAY_MAX_SAMPLES];   /* DHR12RD: ch2 << 16 | ch1 */
static uint32_t g_n;
static volatile int g_busy;
static volatile uint32_t g_count;

static void fatal(void) { for (;;) { } }

void replay_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Pin = DAC_I_PIN | DAC_V_PIN; io.Mode = GPIO_MODE_ANALOG; io.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &io);
    __HAL_RCC_DAC12_CLK_ENABLE();
    hdac1.Instance = DAC1;
    if (HAL_DAC_Init(&hdac1) != HAL_OK) fatal();
    DAC_ChannelConfTypeDef c = { 0 };
    c.DAC_SampleAndHold = DAC_SAMPLEANDHOLD_DISABLE;
    c.DAC_Trigger = DAC_TRIGGER_T7_TRGO;
    c.DAC_OutputBuffer = DAC_OUTPUTBUFFER_ENABLE;
    c.DAC_ConnectOnChipPeripheral = DAC_CHIPCONNECT_DISABLE;
    c.DAC_UserTrimming = DAC_TRIMMING_FACTORY;
    if (HAL_DAC_ConfigChannel(&hdac1, &c, DAC_CHANNEL_1) != HAL_OK) fatal();
    if (HAL_DAC_ConfigChannel(&hdac1, &c, DAC_CHANNEL_2) != HAL_OK) fatal();
    /* TIM7 TRGO at 1 MHz */
    __HAL_RCC_TIM7_CLK_ENABLE();
    htim7_dac.Instance = TIM7;
    htim7_dac.Init.Prescaler = 0;
    htim7_dac.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim7_dac.Init.Period = BOARD_TIMCLK_HZ / DAC_FS_HZ - 1u;
    htim7_dac.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_Base_Init(&htim7_dac) != HAL_OK) fatal();
    TIM_MasterConfigTypeDef m = { 0 };
    m.MasterOutputTrigger = TIM_TRGO_UPDATE; m.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
    HAL_TIMEx_MasterConfigSynchronization(&htim7_dac, &m);
    /* DMA: memory word -> DAC dual holding register */
    __HAL_RCC_DMA1_CLK_ENABLE();
    hdma_dac.Instance = DMA1_Stream2;
    hdma_dac.Init.Request = DMA_REQUEST_DAC1_CH1;
    hdma_dac.Init.Direction = DMA_MEMORY_TO_PERIPH;
    hdma_dac.Init.PeriphInc = DMA_PINC_DISABLE; hdma_dac.Init.MemInc = DMA_MINC_ENABLE;
    hdma_dac.Init.PeriphDataAlignment = DMA_PDATAALIGN_WORD; hdma_dac.Init.MemDataAlignment = DMA_MDATAALIGN_WORD;
    hdma_dac.Init.Mode = DMA_NORMAL; hdma_dac.Init.Priority = DMA_PRIORITY_HIGH; hdma_dac.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
    if (HAL_DMA_Init(&hdma_dac) != HAL_OK) fatal();
    __HAL_LINKDMA(&hdac1, DMA_Handle1, hdma_dac);
    HAL_NVIC_SetPriority(DMA1_Stream2_IRQn, PRIO_DAC_DMA, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream2_IRQn);
    g_n = 0; g_busy = 0;
}

uint16_t *replay_buffer(void) { return g_table; }

int replay_load_done(uint32_t n)
{
    if (n == 0 || n > REPLAY_MAX_SAMPLES) return -1;
    for (uint32_t k = 0; k < n; ++k) g_dual[k] = ((uint32_t)(g_table[REPLAY_MAX_SAMPLES + k] & 0x0FFF) << 16) | (g_table[k] & 0x0FFF);
    SCB_CleanDCache_by_Addr(g_dual, (int32_t)(n * 4u));
    g_n = n;
    return 0;
}

int replay_start(void)
{
    if (g_n == 0 || g_busy) return -1;
    g_busy = 1;
    /* dual mode: the DMA writes DHR12RD; HAL_DACEx_DualStart_DMA does it on the channel-1 DMA */
    HAL_DAC_Stop_DMA(&hdac1, DAC_CHANNEL_1);
    if (HAL_DACEx_DualStart_DMA(&hdac1, DAC_CHANNEL_1, g_dual, g_n, DAC_ALIGN_12B_R) != HAL_OK) { g_busy = 0; return -2; }
    sync_pulse();
    HAL_TIM_Base_Start(&htim7_dac);
    return 0;
}

int replay_busy(void) { return g_busy; }
uint32_t replay_count(void) { return g_count; }

void HAL_DAC_ConvCpltCallbackCh1(DAC_HandleTypeDef *h)
{
    (void)h;
    HAL_TIM_Base_Stop(&htim7_dac);
    g_busy = 0; g_count++;
}
