/* can_link.h — FDCAN1 between the two nodes (FIRMWARE_SPEC.md §7.3, M6): 1 Mbit/s nominal,
 * 5 Mbit/s data, standard ids of fx_can.h. PD0 (RX) / PD1 (TX), TCAN1042 transceiver. */
#ifndef CAN_LINK_H
#define CAN_LINK_H
#include <stdint.h>
#include "fx_can.h"

void can_init(void);
int  can_send_summary(const fx_can_summary_t *s);                 /* one 16-byte FD frame */
int  can_send_features(const fx_can_features_t *f);              /* three 64-byte FD frames */
/* latest frames received from the other node (copied under the RX interrupt), with the local
 * sample counter at reception; returns 0 if none */
int  can_peer_summary(fx_can_summary_t *s, uint32_t *rx_sample);
int  can_peer_features(fx_can_features_t *f, uint32_t *rx_sample);   /* only complete sets */
uint32_t can_rx_count(void);
uint32_t can_tx_errors(void);

#endif
