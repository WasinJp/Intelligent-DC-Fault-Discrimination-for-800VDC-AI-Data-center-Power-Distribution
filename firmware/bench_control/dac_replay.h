/* dac_replay.h — DAC1 OUT1/OUT2 at 1 MSa/s from a table (FIRMWARE_SPEC.md §10 `replay`): tables
 * come from tools/replay_waveforms.py (.dac: uint16 i[n] then v[n], 12-bit codes), uploaded over
 * the console into RAM, started by `replay start` (which also pulses SYNC). */
#ifndef DAC_REPLAY_H
#define DAC_REPLAY_H
#include <stdint.h>
#define REPLAY_MAX_SAMPLES 5200          /* 5.2 ms at 1 MSa/s = one fixture record */
void replay_init(void);
uint16_t *replay_buffer(void);           /* 2 * REPLAY_MAX_SAMPLES uint16: i then v */
int  replay_load_done(uint32_t n_samples);   /* after the host wrote the buffer */
int  replay_start(void);                 /* SYNC then DMA (dual DAC); 0 ok */
int  replay_busy(void);
uint32_t replay_count(void);
#endif
