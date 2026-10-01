/* main_bc.c — bench-control image for the third NUCLEO-H743ZI2 (FIRMWARE_SPEC.md §10, M7).
 * Status: built with arm-none-eabi-gcc, NOT run on hardware. Test plan: docs/M7_TEST_PROCEDURE.md. */
#include "board_bc.h"
#include "../node/clock.h"
#include "../node/timing.h"
#include "profile.h"
#include "fault.h"
#include "uvlo.h"
#include "dac_replay.h"

void cli_init(void);
void cli_poll(void);

static void leds_init(void)
{
    __HAL_RCC_GPIOB_CLK_ENABLE(); __HAL_RCC_GPIOE_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Mode = GPIO_MODE_OUTPUT_PP; io.Pull = GPIO_NOPULL; io.Speed = GPIO_SPEED_FREQ_LOW;
    io.Pin = LED_GREEN_PIN; HAL_GPIO_Init(LED_GREEN_GPIO, &io);
    io.Pin = LED_RED_PIN; HAL_GPIO_Init(LED_RED_GPIO, &io);
    io.Pin = LED_YELLOW_PIN; HAL_GPIO_Init(LED_YELLOW_GPIO, &io);
}

int main(void)
{
    cache_init();
    HAL_Init();
    clock_init();
    timing_init();
    leds_init();
    cli_init();
    profile_init();
    fault_init();
    /* v_out divider 20k / 4.7k -> 3.3 V full scale = 17.34 V; 9.6 V off, 10.1 V on, 100 us */
    uvlo_init(9.6f, 10.1f, (float)(3.3 * (24.7 / 4.7) / 65536.0), 100u);
    replay_init();
    uint32_t last = HAL_GetTick();
    for (;;) {
        cli_poll();
        if (HAL_GetTick() - last >= 500u) { last = HAL_GetTick(); HAL_GPIO_TogglePin(LED_GREEN_GPIO, LED_GREEN_PIN); }
        HAL_GPIO_WritePin(LED_RED_GPIO, LED_RED_PIN, uvlo_tripped() ? GPIO_PIN_SET : GPIO_PIN_RESET);
        HAL_GPIO_WritePin(LED_YELLOW_GPIO, LED_YELLOW_PIN, fault_armed() ? GPIO_PIN_SET : GPIO_PIN_RESET);
    }
}
