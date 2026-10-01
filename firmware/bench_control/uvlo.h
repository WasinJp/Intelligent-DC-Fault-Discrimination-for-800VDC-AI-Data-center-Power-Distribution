/* uvlo.h — POL under-voltage lockout emulation (FIRMWARE_SPEC.md §10 `uvlo`, SCALING_SHEET §2):
 * ADC1 at 1 MSa/s on v_out; below v_off for t_hold (100 us) -> all load gates off; re-enable above v_on. */
#ifndef UVLO_H
#define UVLO_H
#include <stdint.h>
void uvlo_init(float v_off, float v_on, float volts_per_code, uint32_t hold_us);
void uvlo_set(float v_off, float v_on);
void uvlo_enable(int on);
int  uvlo_tripped(void);
uint32_t uvlo_trips(void);
float uvlo_last_volts(void);
void uvlo_on_block(const uint16_t *codes, int n);     /* DMA callback */
#endif
