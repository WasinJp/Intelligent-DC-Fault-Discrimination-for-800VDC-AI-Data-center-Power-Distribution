/* usbd_desc.c — USB descriptors of the node CDC device (test VID/PID of the ST CDC example;
 * replace before anything leaves the lab). */
#include "usbd_desc.h"
#include "usbd_core.h"
#include "stm32h7xx_hal.h"
#include <stdio.h>

#define USBD_VID            0x0483
#define USBD_PID            0x5740
#define USBD_LANGID         1033
#define USBD_MANUFACTURER   "IDCFC bench"
#define USBD_PRODUCT        "fx node record stream"
#define USBD_CONFIG         "CDC Config"
#define USBD_INTERFACE      "CDC Interface"

static uint8_t *dev_desc(USBD_SpeedTypeDef speed, uint16_t *len);
static uint8_t *langid_desc(USBD_SpeedTypeDef speed, uint16_t *len);
static uint8_t *manu_desc(USBD_SpeedTypeDef speed, uint16_t *len);
static uint8_t *prod_desc(USBD_SpeedTypeDef speed, uint16_t *len);
static uint8_t *serial_desc(USBD_SpeedTypeDef speed, uint16_t *len);
static uint8_t *config_desc(USBD_SpeedTypeDef speed, uint16_t *len);
static uint8_t *iface_desc(USBD_SpeedTypeDef speed, uint16_t *len);

USBD_DescriptorsTypeDef FS_Desc = { dev_desc, langid_desc, manu_desc, prod_desc, serial_desc, config_desc, iface_desc };

__ALIGN_BEGIN static uint8_t g_dev[USB_LEN_DEV_DESC] __ALIGN_END = {
    0x12, USB_DESC_TYPE_DEVICE, 0x00, 0x02, 0x02, 0x02, 0x00, USB_MAX_EP0_SIZE,
    LOBYTE(USBD_VID), HIBYTE(USBD_VID), LOBYTE(USBD_PID), HIBYTE(USBD_PID), 0x00, 0x02,
    USBD_IDX_MFC_STR, USBD_IDX_PRODUCT_STR, USBD_IDX_SERIAL_STR, USBD_MAX_NUM_CONFIGURATION
};
__ALIGN_BEGIN static uint8_t g_langid[USB_LEN_LANGID_STR_DESC] __ALIGN_END = { USB_LEN_LANGID_STR_DESC, USB_DESC_TYPE_STRING, LOBYTE(USBD_LANGID), HIBYTE(USBD_LANGID) };
__ALIGN_BEGIN static uint8_t g_str[USBD_MAX_STR_DESC_SIZ] __ALIGN_END;
__ALIGN_BEGIN static uint8_t g_serial[0x1A] __ALIGN_END = { 0x1A, USB_DESC_TYPE_STRING };

static uint8_t *dev_desc(USBD_SpeedTypeDef speed, uint16_t *len) { (void)speed; *len = sizeof g_dev; return g_dev; }
static uint8_t *langid_desc(USBD_SpeedTypeDef speed, uint16_t *len) { (void)speed; *len = sizeof g_langid; return g_langid; }
static uint8_t *manu_desc(USBD_SpeedTypeDef speed, uint16_t *len) { (void)speed; USBD_GetString((uint8_t *)USBD_MANUFACTURER, g_str, len); return g_str; }
static uint8_t *prod_desc(USBD_SpeedTypeDef speed, uint16_t *len) { (void)speed; USBD_GetString((uint8_t *)USBD_PRODUCT, g_str, len); return g_str; }
static uint8_t *config_desc(USBD_SpeedTypeDef speed, uint16_t *len) { (void)speed; USBD_GetString((uint8_t *)USBD_CONFIG, g_str, len); return g_str; }
static uint8_t *iface_desc(USBD_SpeedTypeDef speed, uint16_t *len) { (void)speed; USBD_GetString((uint8_t *)USBD_INTERFACE, g_str, len); return g_str; }

static void hex_unicode(uint32_t v, uint8_t *p, uint8_t n)
{
    for (uint8_t i = 0; i < n; ++i) {
        uint8_t d = (uint8_t)((v >> 28) & 0xF);
        p[2 * i] = (uint8_t)(d < 10 ? '0' + d : 'A' + d - 10);
        p[2 * i + 1] = 0;
        v <<= 4;
    }
}

static uint8_t *serial_desc(USBD_SpeedTypeDef speed, uint16_t *len)
{
    (void)speed;
    uint32_t a = HAL_GetUIDw0() + HAL_GetUIDw2(), b = HAL_GetUIDw1();
    hex_unicode(a, g_serial + 2, 8);
    hex_unicode(b, g_serial + 18, 4);
    *len = sizeof g_serial;
    return g_serial;
}
