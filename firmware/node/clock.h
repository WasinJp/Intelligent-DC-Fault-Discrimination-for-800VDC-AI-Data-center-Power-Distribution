#ifndef CLOCK_H
#define CLOCK_H
void clock_init(void);        /* 480 MHz core, PLL2 for the ADC, USART3 kernel clock */
void cache_init(void);        /* I-cache and D-cache on */
#endif
