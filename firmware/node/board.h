/* board.h — NUCLEO-H743ZI2 pin map of the sensing node (FIRMWARE_SPEC.md §8, §9; SCHEMATIC_DESIGN.md §2).
 * Candidate assignments on the CN7/CN10 headers; confirm against the front-end board before the
 * first power-up. Everything the rest of the code needs about the board is in this file. */
#ifndef BOARD_H
#define BOARD_H

#include "stm32h7xx_hal.h"

/* clocks: HSE 8 MHz bypass (ST-Link MCO) -> PLL1 480 MHz core, 240 MHz AHB, 120 MHz APB;
 * PLL2P 50 MHz -> ADC kernel clock, /2 in the ADC -> 25 MHz */
#define BOARD_SYSCLK_HZ      480000000u
#define BOARD_TIMCLK_HZ      240000000u   /* APB1 timers (APB prescaler 2 -> x2) */

/* analog inputs (Arduino header A0 / A1 on CN9) */
#define ADC_I_GPIO           GPIOA
#define ADC_I_PIN            GPIO_PIN_3     /* PA3  = ADC1_INP15  current channel  */
#define ADC_I_CHANNEL        ADC_CHANNEL_15
#define ADC_V_GPIO           GPIOC
#define ADC_V_PIN            GPIO_PIN_0     /* PC0  = ADC2_INP10  voltage channel  */
#define ADC_V_CHANNEL        ADC_CHANNEL_10

/* digital outputs for the breaker driver and the scope (CN10) */
#define TRIP_GPIO            GPIOF
#define TRIP_PIN             GPIO_PIN_13    /* PF13 "D7"  TRIP, active high, also LD3 red mirrors it */
#define ONSET_GPIO           GPIOF
#define ONSET_PIN            GPIO_PIN_14    /* PF14 "D4"  ONSET test pulse */
#define ALERT_GPIO           GPIOF
#define ALERT_PIN            GPIO_PIN_15    /* PF15 "D2"  ALERT (series arc), also LD2 yellow */
#define SYNC_GPIO            GPIOF
#define SYNC_PIN             GPIO_PIN_12    /* PF12 "D8"  SYNC input from the bench control (EXTI12) */
#define SYNC_EXTI_IRQn       EXTI15_10_IRQn
#define ROLE_GPIO            GPIOE
#define ROLE_PIN             GPIO_PIN_9     /* PE9  "D6"  role jumper: open (pull-up) = feeder, to GND = rack */

/* Nucleo LEDs */
#define LED_GREEN_GPIO       GPIOB
#define LED_GREEN_PIN        GPIO_PIN_0     /* LD1: alive */
#define LED_YELLOW_GPIO      GPIOE
#define LED_YELLOW_PIN       GPIO_PIN_1     /* LD2: alert */
#define LED_RED_GPIO         GPIOB
#define LED_RED_PIN          GPIO_PIN_14    /* LD3: trip */

/* console: ST-Link virtual COM port */
#define CONSOLE_USART        USART3
#define CONSOLE_BAUD         921600u
#define CONSOLE_TX_GPIO      GPIOD
#define CONSOLE_TX_PIN       GPIO_PIN_8
#define CONSOLE_RX_GPIO      GPIOD
#define CONSOLE_RX_PIN       GPIO_PIN_9
#define CONSOLE_AF           GPIO_AF7_USART3
#define CONSOLE_RX_DMA       DMA1_Stream1
#define CONSOLE_RX_DMA_REQ   DMA_REQUEST_USART3_RX
#define CONSOLE_RX_DMA_IRQn  DMA1_Stream1_IRQn

/* ADC DMA */
#define ADC_DMA_STREAM       DMA1_Stream0
#define ADC_DMA_REQ          DMA_REQUEST_ADC1
#define ADC_DMA_IRQn         DMA1_Stream0_IRQn
#define ADC_BLOCK            8              /* samples per DMA half buffer = 16 us (§7.4, §9) */

/* interrupt priorities (0 = highest) */
#define PRIO_ADC_DMA         0
#define PRIO_SYNC            1
#define PRIO_PENDSV          2              /* decision (feature extraction + inference) */
#define PRIO_CONSOLE_DMA     5
#define PRIO_SYSTICK         6

/* settings storage: last sector of bank 2 */
#define SETTINGS_FLASH_ADDR  0x081E0000u
#define SETTINGS_FLASH_BANK  FLASH_BANK_2
#define SETTINGS_FLASH_SECT  FLASH_SECTOR_7

#endif /* BOARD_H */
