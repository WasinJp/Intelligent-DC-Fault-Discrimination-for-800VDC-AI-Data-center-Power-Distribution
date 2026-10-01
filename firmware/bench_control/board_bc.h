/* board_bc.h — NUCLEO-H743ZI2 pin map of the bench-control image (FIRMWARE_SPEC.md §10,
 * SCHEMATIC_DESIGN.md §3). Candidate pins on CN7/CN8/CN9/CN10; confirm against the driver board.
 * Everything else in bench_control/ refers to these names only. */
#ifndef BOARD_BC_H
#define BOARD_BC_H
#include "stm32h7xx_hal.h"

#define BOARD_TIMCLK_HZ      240000000u

/* five load gates (binary-weighted branches 2.2 / 4.7 / 10 / 22 / 47 ohm, SCHEMATIC §1.15) */
#define LOAD_N               5
#define LOAD_GPIO            GPIOF
#define LOAD_PINS            { GPIO_PIN_0, GPIO_PIN_1, GPIO_PIN_2, GPIO_PIN_3, GPIO_PIN_4 }   /* PF0..PF4 */
#define LOAD_ENABLE_GPIO     GPIOF
#define LOAD_ENABLE_PIN      GPIO_PIN_5                /* 6th GPIO: load bank enable through the thermal switch */

/* fault one-shot triggers: the MCU can only START a pulse (SCALING_SHEET §7); the length is the RC
 * of the 74HC123 (5 ms rack, 10 ms feeder). A physical arm key switch is in series with the outputs. */
#define FAULT_RACK_GPIO      GPIOE
#define FAULT_RACK_PIN       GPIO_PIN_7                /* trigger of one-shot B */
#define FAULT_FEEDER_GPIO    GPIOE
#define FAULT_FEEDER_PIN     GPIO_PIN_8                /* trigger of one-shot A */
#define ARM_SENSE_GPIO       GPIOE                     /* reads the arm key position (high = armed) */
#define ARM_SENSE_PIN        GPIO_PIN_10
/* selector relays for the fault resistance / inductance (rack: 3 x R, 3 x L; feeder: 2 x R) */
#define SEL_GPIO             GPIOG
#define SEL_R_PINS           { GPIO_PIN_0, GPIO_PIN_1, GPIO_PIN_2 }     /* 60 mOhm, 0.33 Ohm, 1.2 Ohm */
#define SEL_L_PINS           { GPIO_PIN_3, GPIO_PIN_4, GPIO_PIN_5 }     /* 10, 30, 100 uH */
#define SEL_FEEDER_R_PINS    { GPIO_PIN_6, GPIO_PIN_7 }                 /* 22 Ohm, 39 Ohm */

/* SYNC output to both nodes and the scope */
#define SYNC_GPIO            GPIOF
#define SYNC_PIN             GPIO_PIN_12               /* "D8" */
#define SYNC_PULSE_US        20

/* UVLO emulation: v_out through a divider on ADC1_INP15 (PA3, A0); 1 MSa/s */
#define UVLO_ADC_GPIO        GPIOA
#define UVLO_ADC_PIN         GPIO_PIN_3
#define UVLO_ADC_CHANNEL     ADC_CHANNEL_15
#define UVLO_FS_HZ           1000000u
#define UVLO_BLOCK           16

/* DAC replay: DAC1 OUT1 = PA4 (i), OUT2 = PA5 (v), 1 MSa/s, 12-bit */
#define DAC_I_PIN            GPIO_PIN_4
#define DAC_V_PIN            GPIO_PIN_5
#define DAC_FS_HZ            1000000u

/* LEDs */
#define LED_GREEN_GPIO       GPIOB
#define LED_GREEN_PIN        GPIO_PIN_0
#define LED_YELLOW_GPIO      GPIOE
#define LED_YELLOW_PIN       GPIO_PIN_1
#define LED_RED_GPIO         GPIOB
#define LED_RED_PIN          GPIO_PIN_14

/* console: ST-Link VCP (USB serial) */
#define CONSOLE_USART        USART3
#define CONSOLE_BAUD         921600u
#define CONSOLE_TX_GPIO      GPIOD
#define CONSOLE_TX_PIN       GPIO_PIN_8
#define CONSOLE_RX_PIN       GPIO_PIN_9
#define CONSOLE_AF           GPIO_AF7_USART3
#define CONSOLE_RX_DMA       DMA1_Stream1
#define CONSOLE_RX_DMA_REQ   DMA_REQUEST_USART3_RX
#define CONSOLE_RX_DMA_IRQn  DMA1_Stream1_IRQn

#define PRIO_UVLO_DMA        0
#define PRIO_DAC_DMA         1
#define PRIO_SCHED_TIM       2
#define PRIO_CONSOLE_DMA     5

#endif
