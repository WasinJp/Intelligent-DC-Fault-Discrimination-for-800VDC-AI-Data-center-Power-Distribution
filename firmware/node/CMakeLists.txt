# firmware/node — STM32H743ZI sensing-node image (FIRMWARE_SPEC.md §2, §9).
#
#   bash firmware/tools/fetch_stm32.sh                       # once: CMSIS + HAL into firmware/third_party
#   cmake -S firmware/node -B firmware/node/build -G Ninja \
#         -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake [-DARM_TOOLCHAIN_DIR=<.../bin>]
#   cmake --build firmware/node/build                        # -> fx_node.elf / .bin / .hex / .map
#
# Flags of §1.3: C11, -O2 -Wall -Wextra -Werror, -mfpu=fpv5-d16 -mfloat-abi=hard, plus
# -ffp-contract=off (DEVIATIONS.md #4). common/ is compiled strictly; the HAL with relaxed warnings.
cmake_minimum_required(VERSION 3.20)
project(fx_node C ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(FX_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/..)
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

# ---- HAL + CMSIS (relaxed warnings: vendor code)
add_library(stm32hal STATIC
  ${HAL}/Src/stm32h7xx_hal.c ${HAL}/Src/stm32h7xx_hal_cortex.c
  ${HAL}/Src/stm32h7xx_hal_rcc.c ${HAL}/Src/stm32h7xx_hal_rcc_ex.c
  ${HAL}/Src/stm32h7xx_hal_pwr.c ${HAL}/Src/stm32h7xx_hal_pwr_ex.c
  ${HAL}/Src/stm32h7xx_hal_gpio.c ${HAL}/Src/stm32h7xx_hal_exti.c
  ${HAL}/Src/stm32h7xx_hal_dma.c ${HAL}/Src/stm32h7xx_hal_dma_ex.c
  ${HAL}/Src/stm32h7xx_hal_adc.c ${HAL}/Src/stm32h7xx_hal_adc_ex.c
  ${HAL}/Src/stm32h7xx_hal_tim.c ${HAL}/Src/stm32h7xx_hal_tim_ex.c
  ${HAL}/Src/stm32h7xx_hal_uart.c ${HAL}/Src/stm32h7xx_hal_uart_ex.c
  ${HAL}/Src/stm32h7xx_hal_flash.c ${HAL}/Src/stm32h7xx_hal_flash_ex.c
  ${HAL}/Src/stm32h7xx_hal_fdcan.c ${HAL}/Src/stm32h7xx_hal_pcd.c ${HAL}/Src/stm32h7xx_hal_pcd_ex.c
  ${HAL}/Src/stm32h7xx_ll_usb.c
  ${DEV}/Source/Templates/system_stm32h7xx.c)
target_include_directories(stm32hal PUBLIC ${HAL}/Inc ${HAL}/Inc/Legacy ${DEV}/Include ${CORE} ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(stm32hal PRIVATE -Wall -Wno-unused-parameter)

# ---- ST USB device library (CDC) for the record upload (§8, M6)
set(USBD ${TP}/stm32_mw_usb_device)
add_library(usbdev STATIC ${USBD}/Core/Src/usbd_core.c ${USBD}/Core/Src/usbd_ctlreq.c ${USBD}/Core/Src/usbd_ioreq.c
  ${USBD}/Class/CDC/Src/usbd_cdc.c)
target_include_directories(usbdev PUBLIC ${USBD}/Core/Inc ${USBD}/Class/CDC/Inc ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(usbdev PUBLIC stm32hal)
target_compile_options(usbdev PRIVATE -Wall -Wno-unused-parameter)

# ---- CMSIS-DSP: only the FFT and what it pulls in (float32 cadence learner, M5 target)
set(DSP ${TP}/cmsis_dsp)
add_library(cmsisdsp STATIC
  ${DSP}/Source/TransformFunctions/TransformFunctions.c ${DSP}/Source/CommonTables/CommonTables.c
  ${DSP}/Source/BasicMathFunctions/BasicMathFunctions.c ${DSP}/Source/ComplexMathFunctions/ComplexMathFunctions.c
  ${DSP}/Source/FastMathFunctions/FastMathFunctions.c ${DSP}/Source/MatrixFunctions/MatrixFunctions.c
  ${DSP}/Source/StatisticsFunctions/StatisticsFunctions.c ${DSP}/Source/SupportFunctions/SupportFunctions.c)
target_include_directories(cmsisdsp PUBLIC ${DSP}/Include ${DSP}/PrivateInclude ${CORE})
target_compile_definitions(cmsisdsp PUBLIC DISABLEFLOAT16)   # __FPU_PRESENT comes from stm32h743xx.h
target_compile_options(cmsisdsp PRIVATE -Wno-all -Wno-unused-parameter)

# ---- platform-independent core, strict (CMSIS FFT backend)
set(FX_COMMON ${FX_ROOT}/common)
add_library(fxcommon STATIC
  ${FX_COMMON}/fx_filters.c ${FX_COMMON}/fx_onset.c ${FX_COMMON}/fx_features.c
  ${FX_COMMON}/fx_cadence.c ${FX_COMMON}/fx_cadence32.c ${FX_COMMON}/fx_fft32_cmsis.c
  ${FX_COMMON}/fx_model.c ${FX_COMMON}/fx_relay.c ${FX_COMMON}/fx_record.c
  ${FX_COMMON}/fx_can.c ${FX_COMMON}/fx_upload.c)
target_include_directories(fxcommon PUBLIC ${FX_COMMON})
target_compile_definitions(fxcommon PUBLIC FX_FFT_CMSIS=1)
target_compile_options(fxcommon PRIVATE -Wall -Wextra -Werror)
target_link_libraries(fxcommon PUBLIC cmsisdsp)

# ---- the node image
add_executable(fx_node.elf
  main.c clock.c timing.c trip.c adc_dma.c settings.c stream.c cli.c stm32h7xx_it.c
  cadence_task.c can_link.c usb_upload.c usbd_conf.c usbd_desc.c
  ${DEV}/Source/Templates/gcc/startup_stm32h743xx.s)
target_include_directories(fx_node.elf PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(fx_node.elf PRIVATE -Wall -Wextra -Werror)
target_link_libraries(fx_node.elf fxcommon stm32hal usbdev m)
target_link_options(fx_node.elf PRIVATE ${MCU_FLAGS}
  -T${CMAKE_CURRENT_SOURCE_DIR}/STM32H743ZITX_FLASH.ld
  -specs=nano.specs -specs=nosys.specs -u _printf_float
  -Wl,--gc-sections -Wl,-Map=${CMAKE_BINARY_DIR}/fx_node.map -Wl,--print-memory-usage -Wl,--no-warn-rwx-segments)
add_custom_command(TARGET fx_node.elf POST_BUILD
  COMMAND ${CMAKE_SIZE} $<TARGET_FILE:fx_node.elf>
  COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:fx_node.elf> ${CMAKE_BINARY_DIR}/fx_node.bin
  COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:fx_node.elf> ${CMAKE_BINARY_DIR}/fx_node.hex)
