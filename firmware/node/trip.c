#include "trip.h"

static void out_pin(GPIO_TypeDef *g, uint16_t pin)
{
    GPIO_InitTypeDef io = { 0 };
    io.Pin = pin; io.Mode = GPIO_MODE_OUTPUT_PP; io.Pull = GPIO_NOPULL; io.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    HAL_GPIO_Init(g, &io);
    HAL_GPIO_WritePin(g, pin, GPIO_PIN_RESET);
}

void pins_init(void)
{
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();
    __HAL_RCC_GPIOF_CLK_ENABLE();
    out_pin(TRIP_GPIO, TRIP_PIN);
    out_pin(ONSET_GPIO, ONSET_PIN);
    out_pin(ALERT_GPIO, ALERT_PIN);
    out_pin(LED_GREEN_GPIO, LED_GREEN_PIN);
    out_pin(LED_YELLOW_GPIO, LED_YELLOW_PIN);
    out_pin(LED_RED_GPIO, LED_RED_PIN);
    GPIO_InitTypeDef io = { 0 };
    io.Pin = ROLE_PIN; io.Mode = GPIO_MODE_INPUT; io.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(ROLE_GPIO, &io);
    io.Pin = SYNC_PIN; io.Mode = GPIO_MODE_IT_RISING; io.Pull = GPIO_PULLDOWN;
    HAL_GPIO_Init(SYNC_GPIO, &io);
    HAL_NVIC_SetPriority(SYNC_EXTI_IRQn, PRIO_SYNC, 0);
    HAL_NVIC_EnableIRQ(SYNC_EXTI_IRQn);
}

void alert_set(int on)
{
    HAL_GPIO_WritePin(ALERT_GPIO, ALERT_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(LED_YELLOW_GPIO, LED_YELLOW_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void onset_pulse_begin(void) { ONSET_GPIO->BSRR = ONSET_PIN; }
void onset_pulse_end(void) { ONSET_GPIO->BSRR = (uint32_t)ONSET_PIN << 16; }
int role_is_rack(void) { return HAL_GPIO_ReadPin(ROLE_GPIO, ROLE_PIN) == GPIO_PIN_RESET; }
void led_alive_toggle(void) { HAL_GPIO_TogglePin(LED_GREEN_GPIO, LED_GREEN_PIN); }
