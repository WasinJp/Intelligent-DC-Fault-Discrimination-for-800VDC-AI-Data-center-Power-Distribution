/* fault.h — fault one-shot triggers, selector relays, SYNC output (FIRMWARE_SPEC.md §10 `fault`,
 * `sync`; SCALING_SHEET §7). The firmware only starts a pulse; the 74HC123 one-shots bound it and the
 * arm key switch gates it in hardware. Software additionally refuses to trigger when the arm sense
 * input is low. */
#ifndef FAULT_H
#define FAULT_H
#include <stdint.h>

void fault_init(void);
int  fault_armed(void);                                   /* arm key sense */
int  fault_select_rack(int r_sel, int l_sel);             /* 0..2 each; -1 = none */
int  fault_select_feeder(int r_sel);                      /* 0..1 */
/* schedule a trigger at scheduler time t_us (profile_time_us base); kind 0 rack, 1 feeder; 0 ok */
int  fault_schedule(int kind, uint32_t t_us);
int  fault_trigger_now(int kind);                         /* unscheduled */
void fault_cancel(void);
void fault_tick(void);                                    /* from the 100 us scheduler tick */
void fault_schedule_notify(uint32_t next_edge_us);        /* profile tells us the next rising edge */
uint32_t fault_last_trigger_us(void);
uint32_t fault_count(void);
void sync_pulse(void);                                    /* SYNC_PULSE_US high pulse */

#endif
