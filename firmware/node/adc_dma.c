#include "adc_dma.h"
#include "board.h"

ADC_HandleTypeDef hadc1, hadc2;
DMA_HandleTypeDef hdma_adc1;
TIM_HandleTypeDef htim3;

/* two blocks of ADC_BLOCK dual samples; 32-byte aligned so each half is one D-cache line */
__attribute__((section(".ram_d2"), aligned(32))) static uint32_t adc_buf[2 * ADC_BLOCK];
static adc_block_cb_t g_cb;
static volatile uint32_t g_overruns;

static void fatal(void) { for (;;) { } }

static void adc_gpio_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Mode = GPIO_MODE_ANALOG; io.Pull = GPIO_NOPULL;
    io.Pin = ADC_I_PIN; HAL_GPIO_Init(ADC_I_GPIO, &io);
    io.Pin = ADC_V_PIN; HAL_GPIO_Init(ADC_V_GPIO, &io);
}

static void tim3_init(void)
{
    __HAL_RCC_TIM3_CLK_ENABLE();
    uint32_t timclk = HAL_RCC_GetPCLK1Freq() * 2u;          /* APB1 prescaler 2 -> timers x2 */
    htim3.Instance = TIM3;
    htim3.Init.Prescaler = 0;
    htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim3.Init.Period = timclk / 500000u - 1u;               /* 480 - 1 at 240 MHz */
    htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_Base_Init(&htim3) != HAL_OK) fatal();
    TIM_MasterConfigTypeDef m = { 0 };
    m.MasterOutputTrigger = TIM_TRGO_UPDATE;
    m.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
    if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &m) != HAL_OK) fatal();
}

static void adc_one_init(ADC_HandleTypeDef *h, ADC_TypeDef *inst, uint32_t trig, uint32_t datamgmt, uint32_t channel)
{
    h->Instance = inst;
    h->Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV2;           /* 50 MHz PLL2P / 2 = 25 MHz */
    h->Init.Resolution = ADC_RESOLUTION_16B;
    h->Init.ScanConvMode = ADC_SCAN_DISABLE;
    h->Init.EOCSelection = ADC_EOC_SINGLE_CONV;
    h->Init.LowPowerAutoWait = DISABLE;
    h->Init.ContinuousConvMode = DISABLE;
    h->Init.NbrOfConversion = 1;
    h->Init.DiscontinuousConvMode = DISABLE;
    h->Init.ExternalTrigConv = trig;
    h->Init.ExternalTrigConvEdge = (trig == ADC_SOFTWARE_START) ? ADC_EXTERNALTRIGCONVEDGE_NONE : ADC_EXTERNALTRIGCONVEDGE_RISING;
    h->Init.ConversionDataManagement = datamgmt;
    h->Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
    h->Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
    h->Init.OversamplingMode = DISABLE;
    if (HAL_ADC_Init(h) != HAL_OK) fatal();
    ADC_ChannelConfTypeDef ch = { 0 };
    ch.Channel = channel;
    ch.Rank = ADC_REGULAR_RANK_1;
    ch.SamplingTime = ADC_SAMPLETIME_8CYCLES_5;              /* 0.34 us at 25 MHz; total < 0.7 us */
    ch.SingleDiff = ADC_SINGLE_ENDED;
    ch.OffsetNumber = ADC_OFFSET_NONE;
    ch.Offset = 0;
    if (HAL_ADC_ConfigChannel(h, &ch) != HAL_OK) fatal();
    if (HAL_ADCEx_Calibration_Start(h, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED) != HAL_OK) fatal();
}

void adc_dma_init(adc_block_cb_t cb)
{
    g_cb = cb;
    adc_gpio_init();
    tim3_init();
    __HAL_RCC_ADC12_CLK_ENABLE();
    __HAL_RCC_DMA1_CLK_ENABLE();

    adc_one_init(&hadc1, ADC1, ADC_EXTERNALTRIG_T3_TRGO, ADC_CONVERSIONDATA_DMA_CIRCULAR, ADC_I_CHANNEL);
    adc_one_init(&hadc2, ADC2, ADC_SOFTWARE_START, ADC_CONVERSIONDATA_DR, ADC_V_CHANNEL);

    ADC_MultiModeTypeDef mm = { 0 };
    mm.Mode = ADC_DUALMODE_REGSIMULT;
    mm.DualModeData = ADC_DUALMODEDATAFORMAT_32_10_BITS;      /* both 16-bit results in one 32-bit word */
    mm.TwoSamplingDelay = ADC_TWOSAMPLINGDELAY_1CYCLE;
    if (HAL_ADCEx_MultiModeConfigChannel(&hadc1, &mm) != HAL_OK) fatal();

    hdma_adc1.Instance = ADC_DMA_STREAM;
    hdma_adc1.Init.Request = ADC_DMA_REQ;
    hdma_adc1.Init.Direction = DMA_PERIPH_TO_MEMORY;
    hdma_adc1.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_adc1.Init.MemInc = DMA_MINC_ENABLE;
    hdma_adc1.Init.PeriphDataAlignment = DMA_PDATAALIGN_WORD;
    hdma_adc1.Init.MemDataAlignment = DMA_MDATAALIGN_WORD;
    hdma_adc1.Init.Mode = DMA_CIRCULAR;
    hdma_adc1.Init.Priority = DMA_PRIORITY_VERY_HIGH;
    hdma_adc1.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
    if (HAL_DMA_Init(&hdma_adc1) != HAL_OK) fatal();
    __HAL_LINKDMA(&hadc1, DMA_Handle, hdma_adc1);
    HAL_NVIC_SetPriority(ADC_DMA_IRQn, PRIO_ADC_DMA, 0);
    HAL_NVIC_EnableIRQ(ADC_DMA_IRQn);
}

void adc_dma_start(void)
{
    if (HAL_ADCEx_MultiModeStart_DMA(&hadc1, adc_buf, 2 * ADC_BLOCK) != HAL_OK) fatal();
    if (HAL_TIM_Base_Start(&htim3) != HAL_OK) fatal();
}

void adc_dma_stop(void)
{
    HAL_TIM_Base_Stop(&htim3);
    HAL_ADCEx_MultiModeStop_DMA(&hadc1);
}

uint32_t adc_dma_overruns(void) { return g_overruns; }

static void deliver(const uint32_t *half)
{
    SCB_InvalidateDCache_by_Addr((uint32_t *)half, ADC_BLOCK * 4);   /* DMA wrote behind the cache */
    if (g_cb) g_cb(half, ADC_BLOCK);
}

void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc) { (void)hadc; deliver(adc_buf); }
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc) { (void)hadc; deliver(adc_buf + ADC_BLOCK); }
void HAL_ADC_ErrorCallback(ADC_HandleTypeDef *hadc) { (void)hadc; g_overruns++; }
