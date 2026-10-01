# arm-none-eabi.cmake — CMake toolchain file for the STM32H7 images.
#   cmake -S firmware/node -B firmware/node/build -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake
# Set ARM_TOOLCHAIN_DIR (or put arm-none-eabi-gcc on PATH).
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

if(DEFINED ENV{ARM_TOOLCHAIN_DIR})
  set(_bin "$ENV{ARM_TOOLCHAIN_DIR}/")
elseif(ARM_TOOLCHAIN_DIR)
  set(_bin "${ARM_TOOLCHAIN_DIR}/")
else()
  set(_bin "")
endif()
set(CMAKE_C_COMPILER   "${_bin}arm-none-eabi-gcc${CMAKE_EXECUTABLE_SUFFIX}")
set(CMAKE_ASM_COMPILER "${_bin}arm-none-eabi-gcc${CMAKE_EXECUTABLE_SUFFIX}")
set(CMAKE_OBJCOPY      "${_bin}arm-none-eabi-objcopy${CMAKE_EXECUTABLE_SUFFIX}" CACHE FILEPATH "")
set(CMAKE_SIZE         "${_bin}arm-none-eabi-size${CMAKE_EXECUTABLE_SUFFIX}" CACHE FILEPATH "")

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
