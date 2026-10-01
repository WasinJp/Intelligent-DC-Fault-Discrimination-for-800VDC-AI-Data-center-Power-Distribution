/* main.c — sensing-node image for the NUCLEO-H743ZI2 (FIRMWARE_SPEC.md §2 node/).
 *
 * Status: M3 code, built with arm-none-eabi-gcc, NOT yet run on hardware (boards in transit).
 * On-target test procedure: firmware/docs/M3_TEST_PROCEDURE.md. */
#include "board.h"
#include "clock.h"
#include "timing.h"
#include "trip.h"
#include "settings.h"
#include "adc_dma.h"
#include "stream.h"
#include "cli.h"
#include "cadence_task.h"
#include "can_link.h"
#include "usb_upload.h"

int main(void)
{
    cache_init();
    HAL_Init();
    clock_init();
    timing_init();
    pins_init();
    settings_load();
    cli_init();
    cadence_init();
    can_init();
    usb_upload_init();
    stream_init();
    adc_dma_init(stream_on_block);
    adc_dma_start();

    uint32_t last_blink = HAL_GetTick();
    for (;;) {
        cli_poll();
        stream_poll_upload();        /* M6: record upload at k_on + 2500 over USB CDC */
        cadence_poll();              /* M5: relearn every 200 ms (background, preemptible) */
        if (HAL_GetTick() - last_blink >= 500u) { last_blink = HAL_GetTick(); led_alive_toggle(); }
    }
}

void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
    if (pin == SYNC_PIN) stream_sync_mark();
}
