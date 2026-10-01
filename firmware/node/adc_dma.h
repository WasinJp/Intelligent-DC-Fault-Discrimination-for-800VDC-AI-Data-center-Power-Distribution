/* adc_dma.h — TIM3-triggered ADC1+ADC2 dual simultaneous 16-bit sampling at 500 kSa/s, DMA
 * circular into a 2 x 8-word buffer; a callback per 8-sample block (FIRMWARE_SPEC.md §9).
 * Each 32-bit word holds ADC1 (current) in the low half and ADC2 (voltage) in the high half. */
#ifndef ADC_DMA_H
#define ADC_DMA_H
#include <stdint.h>

typedef void (*adc_block_cb_t)(const uint32_t *words, int n);

void adc_dma_init(adc_block_cb_t cb);
void adc_dma_start(void);
void adc_dma_stop(void);
uint32_t adc_dma_overruns(void);

#endif
