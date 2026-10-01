/* usb_upload.c — CDC ACM transmit path on USB OTG_FS, built on the ST USB device library
 * (third_party/stm32_mw_usb_device): usbd_core + usbd_cdc with the descriptor and conf below. */
#include "usb_upload.h"
#include "board.h"
#include "usbd_core.h"
#include "usbd_cdc.h"
#include "usbd_desc.h"
#include <string.h>

USBD_HandleTypeDef hUsbDevice;
PCD_HandleTypeDef hpcd_USB_OTG_FS;
static volatile uint32_t g_tx_busy, g_bytes;
static uint8_t g_rx_buf[CDC_DATA_FS_MAX_PACKET_SIZE];
static int g_connected;

/* ---- CDC interface callbacks (usbd_cdc_if) */
static int8_t cdc_init(void)
{
    USBD_CDC_SetRxBuffer(&hUsbDevice, g_rx_buf);
    USBD_CDC_ReceivePacket(&hUsbDevice);
    g_connected = 1;
    return USBD_OK;
}
static int8_t cdc_deinit(void) { g_connected = 0; return USBD_OK; }
static int8_t cdc_control(uint8_t cmd, uint8_t *pbuf, uint16_t length)
{
    (void)cmd; (void)pbuf; (void)length;             /* line coding is irrelevant for a binary stream */
    return USBD_OK;
}
static int8_t cdc_receive(uint8_t *buf, uint32_t *len)
{
    (void)buf; (void)len;                            /* commands go over the ST-Link VCP, not here */
    USBD_CDC_SetRxBuffer(&hUsbDevice, g_rx_buf);
    USBD_CDC_ReceivePacket(&hUsbDevice);
    return USBD_OK;
}
static int8_t cdc_tx_complete(uint8_t *buf, uint32_t *len, uint8_t epnum)
{
    (void)buf; (void)len; (void)epnum;
    g_tx_busy = 0;
    return USBD_OK;
}

static USBD_CDC_ItfTypeDef g_cdc_if = { cdc_init, cdc_deinit, cdc_control, cdc_receive, cdc_tx_complete };

void usb_upload_init(void)
{
    HAL_PWREx_EnableUSBVoltageDetector();
    if (USBD_Init(&hUsbDevice, &FS_Desc, 0) != USBD_OK) return;
    if (USBD_RegisterClass(&hUsbDevice, &USBD_CDC) != USBD_OK) return;
    if (USBD_CDC_RegisterInterface(&hUsbDevice, &g_cdc_if) != USBD_OK) return;
    USBD_Start(&hUsbDevice);
}

int usb_upload_connected(void) { return g_connected && hUsbDevice.dev_state == USBD_STATE_CONFIGURED; }
uint32_t usb_upload_bytes(void) { return g_bytes; }

int usb_upload_send(const uint8_t *data, size_t len)
{
    if (!usb_upload_connected()) return -1;
    size_t off = 0;
    while (off < len) {
        size_t chunk = len - off > 512 ? 512 : len - off;
        uint32_t t0 = HAL_GetTick();
        while (g_tx_busy) { if (HAL_GetTick() - t0 > 100) return -2; }
        g_tx_busy = 1;
        USBD_CDC_SetTxBuffer(&hUsbDevice, (uint8_t *)data + off, (uint16_t)chunk);
        if (USBD_CDC_TransmitPacket(&hUsbDevice) != USBD_OK) { g_tx_busy = 0; return -3; }
        off += chunk;
        g_bytes += (uint32_t)chunk;
    }
    return 0;
}
