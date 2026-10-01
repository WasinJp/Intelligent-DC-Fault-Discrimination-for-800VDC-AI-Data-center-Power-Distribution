/* usbd_conf.c — low-level glue between the ST USB device library and the HAL PCD (OTG_FS). */
#include "usbd_conf.h"
#include "usbd_core.h"
#include "usbd_cdc.h"
#include "board.h"

extern PCD_HandleTypeDef hpcd_USB_OTG_FS;

/* the library allocates one class-data block; serve it statically */
static uint32_t g_class_mem[(sizeof(USBD_CDC_HandleTypeDef) + 3) / 4];
void *usb_static_malloc(uint32_t size) { (void)size; return g_class_mem; }
void usb_static_free(void *p) { (void)p; }

void HAL_PCD_MspInit(PCD_HandleTypeDef *h)
{
    if (h->Instance != USB_OTG_FS) return;
    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitTypeDef io = { 0 };
    io.Pin = GPIO_PIN_11 | GPIO_PIN_12;             /* DM / DP */
    io.Mode = GPIO_MODE_AF_PP; io.Pull = GPIO_NOPULL; io.Speed = GPIO_SPEED_FREQ_VERY_HIGH; io.Alternate = GPIO_AF10_OTG1_FS;
    HAL_GPIO_Init(GPIOA, &io);
    __HAL_RCC_USB2_OTG_FS_CLK_ENABLE();
    HAL_NVIC_SetPriority(OTG_FS_IRQn, PRIO_CONSOLE_DMA, 0);
    HAL_NVIC_EnableIRQ(OTG_FS_IRQn);
}

/* ---- PCD -> device library callbacks */
void HAL_PCD_SetupStageCallback(PCD_HandleTypeDef *h) { USBD_LL_SetupStage((USBD_HandleTypeDef *)h->pData, (uint8_t *)h->Setup); }
void HAL_PCD_DataOutStageCallback(PCD_HandleTypeDef *h, uint8_t ep) { USBD_LL_DataOutStage((USBD_HandleTypeDef *)h->pData, ep, h->OUT_ep[ep].xfer_buff); }
void HAL_PCD_DataInStageCallback(PCD_HandleTypeDef *h, uint8_t ep) { USBD_LL_DataInStage((USBD_HandleTypeDef *)h->pData, ep, h->IN_ep[ep].xfer_buff); }
void HAL_PCD_SOFCallback(PCD_HandleTypeDef *h) { USBD_LL_SOF((USBD_HandleTypeDef *)h->pData); }
void HAL_PCD_ResetCallback(PCD_HandleTypeDef *h)
{
    USBD_LL_SetSpeed((USBD_HandleTypeDef *)h->pData, USBD_SPEED_FULL);
    USBD_LL_Reset((USBD_HandleTypeDef *)h->pData);
}
void HAL_PCD_SuspendCallback(PCD_HandleTypeDef *h) { USBD_LL_Suspend((USBD_HandleTypeDef *)h->pData); __HAL_PCD_GATE_PHYCLOCK(h); }
void HAL_PCD_ResumeCallback(PCD_HandleTypeDef *h) { USBD_LL_Resume((USBD_HandleTypeDef *)h->pData); }
void HAL_PCD_ISOOUTIncompleteCallback(PCD_HandleTypeDef *h, uint8_t ep) { USBD_LL_IsoOUTIncomplete((USBD_HandleTypeDef *)h->pData, ep); }
void HAL_PCD_ISOINIncompleteCallback(PCD_HandleTypeDef *h, uint8_t ep) { USBD_LL_IsoINIncomplete((USBD_HandleTypeDef *)h->pData, ep); }
void HAL_PCD_ConnectCallback(PCD_HandleTypeDef *h) { USBD_LL_DevConnected((USBD_HandleTypeDef *)h->pData); }
void HAL_PCD_DisconnectCallback(PCD_HandleTypeDef *h) { USBD_LL_DevDisconnected((USBD_HandleTypeDef *)h->pData); }

/* ---- device library -> PCD */
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *pdev)
{
    hpcd_USB_OTG_FS.pData = pdev;
    pdev->pData = &hpcd_USB_OTG_FS;
    hpcd_USB_OTG_FS.Instance = USB_OTG_FS;
    hpcd_USB_OTG_FS.Init.dev_endpoints = 9;
    hpcd_USB_OTG_FS.Init.speed = PCD_SPEED_FULL;
    hpcd_USB_OTG_FS.Init.dma_enable = DISABLE;
    hpcd_USB_OTG_FS.Init.phy_itface = PCD_PHY_EMBEDDED;
    hpcd_USB_OTG_FS.Init.Sof_enable = DISABLE;
    hpcd_USB_OTG_FS.Init.low_power_enable = DISABLE;
    hpcd_USB_OTG_FS.Init.lpm_enable = DISABLE;
    hpcd_USB_OTG_FS.Init.vbus_sensing_enable = DISABLE;
    hpcd_USB_OTG_FS.Init.use_dedicated_ep1 = DISABLE;
    if (HAL_PCD_Init(&hpcd_USB_OTG_FS) != HAL_OK) return USBD_FAIL;
    HAL_PCDEx_SetRxFiFo(&hpcd_USB_OTG_FS, 0x80);
    HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 0, 0x40);
    HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 1, 0x80);
    return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef *pdev) { HAL_PCD_DeInit(pdev->pData); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *pdev) { HAL_PCD_Start(pdev->pData); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *pdev) { HAL_PCD_Stop(pdev->pData); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *pdev, uint8_t ep, uint8_t type, uint16_t mps) { HAL_PCD_EP_Open(pdev->pData, ep, mps, type); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *pdev, uint8_t ep) { HAL_PCD_EP_Close(pdev->pData, ep); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *pdev, uint8_t ep) { HAL_PCD_EP_Flush(pdev->pData, ep); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *pdev, uint8_t ep) { HAL_PCD_EP_SetStall(pdev->pData, ep); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef *pdev, uint8_t ep) { HAL_PCD_EP_ClrStall(pdev->pData, ep); return USBD_OK; }
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef *pdev, uint8_t ep)
{
    PCD_HandleTypeDef *h = pdev->pData;
    return (ep & 0x80) ? h->IN_ep[ep & 0x7F].is_stall : h->OUT_ep[ep & 0x7F].is_stall;
}
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef *pdev, uint8_t addr) { HAL_PCD_SetAddress(pdev->pData, addr); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *pdev, uint8_t ep, uint8_t *buf, uint32_t size) { HAL_PCD_EP_Transmit(pdev->pData, ep, buf, size); return USBD_OK; }
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *pdev, uint8_t ep, uint8_t *buf, uint32_t size) { HAL_PCD_EP_Receive(pdev->pData, ep, buf, size); return USBD_OK; }
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *pdev, uint8_t ep) { return HAL_PCD_EP_GetRxCount(pdev->pData, ep); }
void USBD_LL_Delay(uint32_t ms) { HAL_Delay(ms); }
