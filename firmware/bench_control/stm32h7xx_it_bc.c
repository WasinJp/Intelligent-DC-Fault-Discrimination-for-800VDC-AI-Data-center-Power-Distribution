#include "board_bc.h"
#include "profile.h"
#include "fault.h"

extern DMA_HandleTypeDef hdma_uvlo, hdma_dac, hdma_usart3_rx;
extern UART_HandleTypeDef huart3;
extern TIM_HandleTypeDef htim2;

void NMI_Handler(void) { for (;;) { } }
void HardFault_Handler(void) { for (;;) { } }
void MemManage_Handler(void) { for (;;) { } }
void BusFault_Handler(void) { for (;;) { } }
void UsageFault_Handler(void) { for (;;) { } }
void SVC_Handler(void) { }
void DebugMon_Handler(void) { }
void PendSV_Handler(void) { }
void SysTick_Handler(void) { HAL_IncTick(); }

void DMA1_Stream0_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_uvlo); }
void DMA1_Stream1_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_usart3_rx); }
void DMA1_Stream2_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_dac); }
void USART3_IRQHandler(void) { HAL_UART_IRQHandler(&huart3); }
void TIM2_IRQHandler(void)
{
    if (__HAL_TIM_GET_FLAG(&htim2, TIM_FLAG_UPDATE)) {
        __HAL_TIM_CLEAR_IT(&htim2, TIM_IT_UPDATE);
        profile_tick();
        fault_tick();
    }
}
