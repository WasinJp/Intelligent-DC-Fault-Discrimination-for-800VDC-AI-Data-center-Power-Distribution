#!/usr/bin/env bash
# fetch_stm32.sh — vendor the STM32H7 CMSIS + HAL sources the node image compiles against.
# They are not committed (firmware/.gitignore: third_party/); run this once per checkout.
#   bash firmware/tools/fetch_stm32.sh [tag]
# Sources (BSD-3-Clause, STMicroelectronics on GitHub): cmsis-core (Arm CMSIS Core headers),
# cmsis-device-h7 (device headers, startup, system file, linker scripts), stm32h7xx-hal-driver.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DST="$HERE/third_party"
mkdir -p "$DST"
clone() {  # repo dir [tag]
    if [ -d "$DST/$2/.git" ]; then echo "$2: present"; return; fi
    if [ -n "${3:-}" ]; then
        git clone --depth 1 --branch "$3" "https://github.com/STMicroelectronics/$1" "$DST/$2"
    else
        git clone --depth 1 "https://github.com/STMicroelectronics/$1" "$DST/$2"
    fi
}
clone cmsis-core           cmsis_core
clone cmsis-device-h7      cmsis_device_h7
clone stm32h7xx-hal-driver stm32h7xx_hal_driver
clone stm32_mw_usb_device  stm32_mw_usb_device          # USB device library (CDC record upload, M6)
# CMSIS-DSP (Arm) for the float32 FFT backend of the cadence learner (M5 target); also compiled on the host
if [ ! -d "$DST/cmsis_dsp/.git" ]; then
    git clone --depth 1 --branch v1.16.2 https://github.com/ARM-software/CMSIS-DSP "$DST/cmsis_dsp"
else
    echo "cmsis_dsp: present"
fi
for d in cmsis_core cmsis_device_h7 stm32h7xx_hal_driver stm32_mw_usb_device cmsis_dsp; do
    echo "$d: $(git -C "$DST/$d" describe --tags --always 2>/dev/null)"
done
