/* stm32h7xx_it.c — interrupt handlers of the node image. */
#include "board.h"
#include "stream.h"

extern DMA_HandleTypeDef hdma_adc1, hdma_usart3_rx;
extern UART_HandleTypeDef huart3;
extern FDCAN_HandleTypeDef hfdcan1;
extern PCD_HandleTypeDef hpcd_USB_OTG_FS;

void NMI_Handler(void) { for (;;) { } }
void HardFault_Handler(void) { for (;;) { } }
void MemManage_Handler(void) { for (;;) { } }
void BusFault_Handler(void) { for (;;) { } }
void UsageFault_Handler(void) { for (;;) { } }
void SVC_Handler(void) { }
void DebugMon_Handler(void) { }
void PendSV_Handler(void) { stream_decide(); }
void SysTick_Handler(void) { HAL_IncTick(); }

void DMA1_Stream0_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_adc1); }
void DMA1_Stream1_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_usart3_rx); }
void USART3_IRQHandler(void) { HAL_UART_IRQHandler(&huart3); }
void EXTI15_10_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(SYNC_PIN); }
void FDCAN1_IT0_IRQHandler(void) { HAL_FDCAN_IRQHandler(&hfdcan1); }
void OTG_FS_IRQHandler(void) { HAL_PCD_IRQHandler(&hpcd_USB_OTG_FS); }
