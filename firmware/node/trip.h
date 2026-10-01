/* trip.h — TRIP / ONSET / ALERT pins, LEDs, role jumper, SYNC input. */
#ifndef TRIP_H
#define TRIP_H
#include <stdint.h>
void pins_init(void);
static inline void trip_set(void);
static inline void trip_clear(void);
void alert_set(int on);
void onset_pulse_begin(void);     /* ONSET high at detection ... */
void onset_pulse_end(void);       /* ... low at the decision */
int  role_is_rack(void);          /* jumper: 1 = rack, 0 = feeder */
void led_alive_toggle(void);

#include "board.h"
static inline void trip_set(void)
{
    TRIP_GPIO->BSRR = TRIP_PIN;                    /* one store: this is the measured edge */
    LED_RED_GPIO->BSRR = LED_RED_PIN;
}
static inline void trip_clear(void)
{
    TRIP_GPIO->BSRR = (uint32_t)TRIP_PIN << 16;
    LED_RED_GPIO->BSRR = (uint32_t)LED_RED_PIN << 16;
}
#endif
