/* profile.h — table-driven workload generator (FIRMWARE_SPEC.md §10 `profile`): two-tier cadence
 * (T1 0.3-3 s with a duty, T2 bursts inside the high phase), steps of 10-80 % of rating as 5-step
 * staircase ramps over 0.5-20 ms across the five load gates, idle drops. Deterministic from a seed
 * (xorshift32), so a run is reproducible. Time base: a 1 MHz scheduler timer (TIM2). */
#ifndef PROFILE_H
#define PROFILE_H
#include <stdint.h>

typedef struct {
    uint32_t seed;
    float T1_s, duty1;            /* iteration period and duty of the high phase */
    float T2_s, burst_frac;       /* burst period inside the high phase and its height (fraction of rating) */
    float P_low, P_high;          /* fractions of rating in the low / high phase */
    float ramp_ms;                /* staircase length for every step */
    uint32_t idle_drop_every;     /* every n-th iteration drops to 0 for one low phase (0 = never) */
} profile_cfg_t;

typedef struct { uint32_t t_us; uint8_t gates; uint8_t kind; } profile_event_t;   /* kind: 0 step, 1 idle, 2 burst */

void profile_init(void);
void profile_defaults(profile_cfg_t *c);
void profile_set(const profile_cfg_t *c);
void profile_start(void);                 /* begins at the scheduler's t = 0 */
void profile_stop(void);                  /* all gates off */
int  profile_running(void);
/* one step to a power fraction (0..1) as a staircase over ramp_ms; also used by the CLI */
void profile_step(float frac, float ramp_ms);
void profile_gates(uint8_t mask);         /* direct gate control */
uint8_t profile_gates_now(void);
uint8_t profile_mask_for(float frac);     /* gate subset closest to the fraction */
uint32_t profile_time_us(void);           /* scheduler time */
uint32_t profile_next_edge_us(void);      /* next scheduled rising edge (for scheduled faults) */
void profile_tick(void);                  /* 1 MHz timer interrupt */
const profile_cfg_t *profile_cfg(void);

#endif
