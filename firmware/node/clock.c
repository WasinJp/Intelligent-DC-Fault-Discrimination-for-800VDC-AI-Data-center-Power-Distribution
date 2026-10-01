/* clock.c — STM32H743 at 480 MHz (VOS0) from the Nucleo's 8 MHz HSE bypass. */
#include "board.h"
#include "clock.h"

static void fatal(void) { for (;;) { } }

void clock_init(void)
{
    HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE0);       /* 480 MHz needs VOS0 */
    while (!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) { }

    RCC_OscInitTypeDef osc = { 0 };
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    osc.HSEState = RCC_HSE_BYPASS;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLM = 1;                 /* 8 MHz VCO input */
    osc.PLL.PLLN = 120;               /* 960 MHz VCO */
    osc.PLL.PLLP = 2;                 /* 480 MHz SYSCLK */
    osc.PLL.PLLQ = 4;
    osc.PLL.PLLR = 2;
    osc.PLL.PLLRGE = RCC_PLL1VCIRANGE_3;
    osc.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
    osc.PLL.PLLFRACN = 0;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) fatal();

    RCC_ClkInitTypeDef clk = { 0 };
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_D1PCLK1 | RCC_CLOCKTYPE_PCLK1
                  | RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_D3PCLK1;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.SYSCLKDivider = RCC_SYSCLK_DIV1;
    clk.AHBCLKDivider = RCC_HCLK_DIV2;       /* 240 MHz */
    clk.APB3CLKDivider = RCC_APB3_DIV2;      /* 120 MHz */
    clk.APB1CLKDivider = RCC_APB1_DIV2;
    clk.APB2CLKDivider = RCC_APB2_DIV2;
    clk.APB4CLKDivider = RCC_APB4_DIV2;
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_4) != HAL_OK) fatal();

    RCC_PeriphCLKInitTypeDef p = { 0 };
    p.PeriphClockSelection = RCC_PERIPHCLK_ADC | RCC_PERIPHCLK_USART3 | RCC_PERIPHCLK_FDCAN | RCC_PERIPHCLK_USB;
    p.PLL2.PLL2M = 1;                 /* 8 MHz */
    p.PLL2.PLL2N = 25;                /* 200 MHz VCO */
    p.PLL2.PLL2P = 4;                 /* 50 MHz adc_ker_ck; ADC prescaler /2 -> 25 MHz */
    p.PLL2.PLL2Q = 4;
    p.PLL2.PLL2R = 4;
    p.PLL2.PLL2RGE = RCC_PLL2VCIRANGE_3;
    p.PLL2.PLL2VCOSEL = RCC_PLL2VCOMEDIUM;
    p.PLL2.PLL2FRACN = 0;
    p.AdcClockSelection = RCC_ADCCLKSOURCE_PLL2;
    p.Usart234578ClockSelection = RCC_USART234578CLKSOURCE_D2PCLK1;
    p.FdcanClockSelection = RCC_FDCANCLKSOURCE_PLL2;        /* PLL2Q = 50 MHz (can_link.c bit timing) */
    p.PLL3.PLL3M = 1;                 /* 8 MHz */
    p.PLL3.PLL3N = 24;                /* 192 MHz VCO */
    p.PLL3.PLL3P = 4;
    p.PLL3.PLL3Q = 4;                 /* 48 MHz USB */
    p.PLL3.PLL3R = 4;
    p.PLL3.PLL3RGE = RCC_PLL3VCIRANGE_3;
    p.PLL3.PLL3VCOSEL = RCC_PLL3VCOWIDE;
    p.PLL3.PLL3FRACN = 0;
    p.UsbClockSelection = RCC_USBCLKSOURCE_PLL3;
    if (HAL_RCCEx_PeriphCLKConfig(&p) != HAL_OK) fatal();
}

void cache_init(void)
{
    SCB_EnableICache();
    SCB_EnableDCache();
}
