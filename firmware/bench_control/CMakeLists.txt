# firmware/bench_control — bench-control image (FIRMWARE_SPEC.md §10, M7): profile generator, fault
# one-shot triggers, UVLO emulation, SYNC, DAC replay, console. Same toolchain and flags as node/.
#
#   cmake -S firmware/bench_control -B firmware/bench_control/build -G Ninja \
#         -DCMAKE_TOOLCHAIN_FILE=../node/cmake/arm-none-eabi.cmake
#   cmake --build firmware/bench_control/build
cmake_minimum_required(VERSION 3.20)
project(fx_bench_control C ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(FX_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/..)
set(NODE ${FX_ROOT}/node)
set(TP ${FX_ROOT}/third_party)
set(HAL ${TP}/stm32h7xx_hal_driver)
set(DEV ${TP}/cmsis_device_h7)
set(CORE ${TP}/cmsis_core/CMSIS/Core/Include)
if(NOT EXISTS ${HAL}/Inc/stm32h7xx_hal.h)
  message(FATAL_ERROR "STM32 HAL not found under ${TP}; run firmware/tools/fetch_stm32.sh")
endif()

set(MCU_FLAGS -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard)
add_compile_options(${MCU_FLAGS} -O2 -g3 -ffunction-sections -fdata-sections -fno-common -ffp-contract=off)
add_compile_definitions(STM32H743xx USE_HAL_DRIVER HSE_VALUE=8000000U)

add_library(stm32hal STATIC
  ${HAL}/Src/stm32h7xx_hal.c ${HAL}/Src/stm32h7xx_hal_cortex.c
  ${HAL}/Src/stm32h7xx_hal_rcc.c ${HAL}/Src/stm32h7xx_hal_rcc_ex.c
  ${HAL}/Src/stm32h7xx_hal_pwr.c ${HAL}/Src/stm32h7xx_hal_pwr_ex.c
  ${HAL}/Src/stm32h7xx_hal_gpio.c ${HAL}/Src/stm32h7xx_hal_exti.c
  ${HAL}/Src/stm32h7xx_hal_dma.c ${HAL}/Src/stm32h7xx_hal_dma_ex.c
  ${HAL}/Src/stm32h7xx_hal_adc.c ${HAL}/Src/stm32h7xx_hal_adc_ex.c
  ${HAL}/Src/stm32h7xx_hal_dac.c ${HAL}/Src/stm32h7xx_hal_dac_ex.c
  ${HAL}/Src/stm32h7xx_hal_tim.c ${HAL}/Src/stm32h7xx_hal_tim_ex.c
  ${HAL}/Src/stm32h7xx_hal_uart.c ${HAL}/Src/stm32h7xx_hal_uart_ex.c
  ${DEV}/Source/Templates/system_stm32h7xx.c)
# the node's HAL configuration applies (same board, same clocks)
target_include_directories(stm32hal PUBLIC ${HAL}/Inc ${HAL}/Inc/Legacy ${DEV}/Include ${CORE} ${NODE})
target_compile_options(stm32hal PRIVATE -Wall -Wno-unused-parameter)

add_executable(fx_bench_control.elf
  main_bc.c profile.c fault.c uvlo.c dac_replay.c cli_bc.c stm32h7xx_it_bc.c
  ${NODE}/clock.c ${NODE}/timing.c
  ${DEV}/Source/Templates/gcc/startup_stm32h743xx.s)
target_include_directories(fx_bench_control.elf PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${NODE})
target_compile_options(fx_bench_control.elf PRIVATE -Wall -Wextra -Werror)
target_link_libraries(fx_bench_control.elf stm32hal m)
target_link_options(fx_bench_control.elf PRIVATE ${MCU_FLAGS}
  -T${NODE}/STM32H743ZITX_FLASH.ld
  -specs=nano.specs -specs=nosys.specs -u _printf_float
  -Wl,--gc-sections -Wl,-Map=${CMAKE_BINARY_DIR}/fx_bench_control.map -Wl,--print-memory-usage -Wl,--no-warn-rwx-segments)
add_custom_command(TARGET fx_bench_control.elf POST_BUILD
  COMMAND ${CMAKE_SIZE} $<TARGET_FILE:fx_bench_control.elf>
  COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:fx_bench_control.elf> ${CMAKE_BINARY_DIR}/fx_bench_control.bin
  COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:fx_bench_control.elf> ${CMAKE_BINARY_DIR}/fx_bench_control.hex)
