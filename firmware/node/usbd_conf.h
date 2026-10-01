/* usbd_conf.h — ST USB device library configuration for the node (one CDC interface, FS). */
#ifndef USBD_CONF_H
#define USBD_CONF_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stm32h7xx_hal.h"

#define USBD_MAX_NUM_INTERFACES     1U
#define USBD_MAX_NUM_CONFIGURATION  1U
#define USBD_MAX_STR_DESC_SIZ       512U
#define USBD_SELF_POWERED           1U
#define USBD_DEBUG_LEVEL            0U
#define USBD_LPM_ENABLED            0U
#define USBD_CDC_INTERVAL           1000U
#define DEVICE_FS                   0
#define USBD_malloc(size)           usb_static_malloc(size)
#define USBD_free(p)                usb_static_free(p)
#define USBD_memset                 memset
#define USBD_memcpy                 memcpy
#define USBD_Delay                  HAL_Delay
#define USBD_UsrLog(...)
#define USBD_ErrLog(...)
#define USBD_DbgLog(...)
void *usb_static_malloc(uint32_t size);
void usb_static_free(void *p);
#endif
