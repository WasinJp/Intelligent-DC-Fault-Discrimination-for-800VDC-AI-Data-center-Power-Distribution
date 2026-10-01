/* usb_upload.h — record stream over the H7's own USB (OTG_FS on PA11/PA12, CN13) as a CDC ACM
 * device (ST USB device library). Frames: fx_upload.h. */
#ifndef USB_UPLOAD_H
#define USB_UPLOAD_H
#include <stdint.h>
#include <stddef.h>
void usb_upload_init(void);
int  usb_upload_send(const uint8_t *data, size_t len);   /* blocking in 512-byte chunks; 0 ok */
int  usb_upload_connected(void);
uint32_t usb_upload_bytes(void);
#endif
