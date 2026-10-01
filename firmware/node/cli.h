/* cli.h — console on the ST-Link VCP (USART3): settings, status, arm, capture, selftest,
 * replay (record-mode parity), timing (FIRMWARE_SPEC.md §8). */
#ifndef CLI_H
#define CLI_H
void cli_init(void);
void cli_poll(void);               /* call from the main loop */
void cli_puts(const char *s);      /* blocking transmit */
#endif
