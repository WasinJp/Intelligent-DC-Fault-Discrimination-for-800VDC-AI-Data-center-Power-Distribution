# firmware/host — gcc build of the platform-independent core, the CLI and the milestone tests.
#
#   cmake -S firmware/host -B firmware/host/build -G Ninja
#   cmake --build firmware/host/build
#   ctest --test-dir firmware/host/build --output-on-failure
#
# Windows: put the WinLibs/MinGW gcc on PATH and use the repo venv's cmake/ninja
# (see firmware/host/README.md). Option -DFX_IIR_FLOAT=ON runs the IIR filters in float32.
cmake_minimum_required(VERSION 3.20)
project(fx_host C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()
option(FX_IIR_FLOAT "run the SOS IIR filters in float32 instead of double (precision comparison)" OFF)

set(FX_MODEL_DATA_H "" CACHE FILEPATH "alternative fx_model_data.h to compile in (default: common/fx_model_data.h)")

add_compile_options(-Wall -Wextra -Werror -ffp-contract=off)
if(FX_IIR_FLOAT)
  add_compile_definitions(FX_IIR_FLOAT=1)
endif()
if(FX_MODEL_DATA_H)
  add_compile_definitions(FX_MODEL_DATA_H_PATH="${FX_MODEL_DATA_H}")
endif()

set(FX_COMMON_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../common)
set(FX_COMMON_SRC
  ${FX_COMMON_DIR}/fx_filters.c ${FX_COMMON_DIR}/fx_onset.c ${FX_COMMON_DIR}/fx_features.c
  ${FX_COMMON_DIR}/fx_cadence.c ${FX_COMMON_DIR}/fx_cadence32.c ${FX_COMMON_DIR}/fx_model.c
  ${FX_COMMON_DIR}/fx_relay.c ${FX_COMMON_DIR}/fx_record.c ${FX_COMMON_DIR}/fx_can.c ${FX_COMMON_DIR}/fx_upload.c)
add_library(fxcommon STATIC ${FX_COMMON_SRC} ${FX_COMMON_DIR}/fx_fft32_generic.c)
target_include_directories(fxcommon PUBLIC ${FX_COMMON_DIR})
set_target_properties(fxcommon PROPERTIES C_EXTENSIONS OFF)   # strict C11, as on the target
target_link_libraries(fxcommon PUBLIC m)

add_executable(fx_cli fx_cli.c)
target_link_libraries(fx_cli fxcommon)

# ---- the same CLI with the CMSIS-DSP FFT backend (the one the node uses), if CMSIS-DSP is fetched
set(FX_CMSIS_DSP ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/cmsis_dsp)
if(EXISTS ${FX_CMSIS_DSP}/Include/arm_math.h)
  add_library(cmsisdsp_host STATIC
    ${FX_CMSIS_DSP}/Source/TransformFunctions/TransformFunctions.c
    ${FX_CMSIS_DSP}/Source/CommonTables/CommonTables.c
    ${FX_CMSIS_DSP}/Source/BasicMathFunctions/BasicMathFunctions.c
    ${FX_CMSIS_DSP}/Source/ComplexMathFunctions/ComplexMathFunctions.c
    ${FX_CMSIS_DSP}/Source/FastMathFunctions/FastMathFunctions.c
    ${FX_CMSIS_DSP}/Source/MatrixFunctions/MatrixFunctions.c
    ${FX_CMSIS_DSP}/Source/StatisticsFunctions/StatisticsFunctions.c
    ${FX_CMSIS_DSP}/Source/SupportFunctions/SupportFunctions.c)
  target_include_directories(cmsisdsp_host PUBLIC ${FX_CMSIS_DSP}/Include ${FX_CMSIS_DSP}/PrivateInclude)
  target_compile_definitions(cmsisdsp_host PUBLIC __GNUC_PYTHON__=1)   # CMSIS-DSP's host mode (no cmsis_compiler.h)
  target_compile_options(cmsisdsp_host PRIVATE -Wno-all -Wno-extra -Wno-error -Wno-unused-parameter)
  add_library(fxcommon_cmsis STATIC ${FX_COMMON_SRC} ${FX_COMMON_DIR}/fx_fft32_cmsis.c)
  target_include_directories(fxcommon_cmsis PUBLIC ${FX_COMMON_DIR})
  target_compile_definitions(fxcommon_cmsis PUBLIC FX_FFT_CMSIS=1)
  target_link_libraries(fxcommon_cmsis PUBLIC cmsisdsp_host m)
  add_executable(fx_cli_cmsis fx_cli.c)
  target_link_libraries(fx_cli_cmsis fxcommon_cmsis)
  set(FX_HAVE_CMSIS ON)
endif()

add_executable(test_units tests/test_units.c)
target_include_directories(test_units PRIVATE tests)
target_link_libraries(test_units fxcommon)

# ---- tests (FIRMWARE_SPEC.md §6.2, §6.3)
enable_testing()
set(FX_REPO ${CMAKE_CURRENT_SOURCE_DIR}/../..)
if(EXISTS ${FX_REPO}/.venv/Scripts/python.exe)
  set(FX_PYTHON ${FX_REPO}/.venv/Scripts/python.exe)
elseif(EXISTS ${FX_REPO}/.venv/bin/python)
  set(FX_PYTHON ${FX_REPO}/.venv/bin/python)
else()
  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  set(FX_PYTHON ${Python3_EXECUTABLE})
endif()
set(FX_FIX ${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures)
set(FX_TOOLS ${CMAKE_CURRENT_SOURCE_DIR}/../tools)

add_test(NAME unit_common COMMAND test_units)

add_test(NAME m1_extract COMMAND fx_cli extract --dir ${FX_FIX} --out ${CMAKE_BINARY_DIR}/features_c.csv)
add_test(NAME m1_feature_agreement
         COMMAND ${FX_PYTHON} ${FX_TOOLS}/compare.py features ${CMAKE_BINARY_DIR}/features_c.csv ${FX_FIX}/reference_features.csv)
set_tests_properties(m1_extract PROPERTIES FIXTURES_SETUP m1csv)
set_tests_properties(m1_feature_agreement PROPERTIES FIXTURES_REQUIRED m1csv)

add_test(NAME m2_score COMMAND fx_cli score --features ${FX_FIX}/reference_features.csv --out ${CMAKE_BINARY_DIR}/scores_c.csv)
add_test(NAME m2_model_agreement
         COMMAND ${FX_PYTHON} ${FX_TOOLS}/compare.py scores ${CMAKE_BINARY_DIR}/scores_c.csv ${FX_FIX}/reference_scores.csv)
set_tests_properties(m2_score PROPERTIES FIXTURES_SETUP m2csv)
set_tests_properties(m2_model_agreement PROPERTIES FIXTURES_REQUIRED m2csv)
add_test(NAME m2_bench COMMAND fx_cli bench --features ${FX_FIX}/reference_features.csv --repeat 20)

# §4.2 on replayed records (host preview of the M3 acceptance): onset within +-2 samples in >= 99 %,
# identical decisions in >= 99.5 %
add_test(NAME m3_stream_vs_record COMMAND fx_cli stream --dir ${FX_FIX} --out ${CMAKE_BINARY_DIR}/stream_vs_record.csv)
add_test(NAME m3_stream_vs_record_prefix COMMAND fx_cli stream --dir ${FX_FIX} --prefix 2375 --seed 1 --out ${CMAKE_BINARY_DIR}/stream_vs_record_prefix.csv)
# §6.2 WORK features (M5) on the records that carry the slow stream
add_test(NAME m5_work_agreement
         COMMAND ${FX_PYTHON} ${FX_TOOLS}/compare.py features ${CMAKE_BINARY_DIR}/features_c.csv ${FX_FIX}/reference_features.csv --work)
set_tests_properties(m5_work_agreement PROPERTIES FIXTURES_REQUIRED m1csv)
# M5 target learner (float32 history, block FFT autocorrelation) on the host, generic FFT backend
add_test(NAME m5_f32_extract COMMAND fx_cli extract --dir ${FX_FIX} --cadence f32 --out ${CMAKE_BINARY_DIR}/features_f32.csv)
add_test(NAME m5_f32_agreement
         COMMAND ${FX_PYTHON} ${FX_TOOLS}/compare.py features ${CMAKE_BINARY_DIR}/features_f32.csv ${FX_FIX}/reference_features.csv --work)
set_tests_properties(m5_f32_extract PROPERTIES FIXTURES_SETUP m5f32csv)
set_tests_properties(m5_f32_agreement PROPERTIES FIXTURES_REQUIRED m5f32csv)
if(FX_HAVE_CMSIS)
  add_test(NAME m5_cmsis_extract COMMAND fx_cli_cmsis extract --dir ${FX_FIX} --cadence f32 --out ${CMAKE_BINARY_DIR}/features_cmsis.csv)
  add_test(NAME m5_cmsis_agreement
           COMMAND ${FX_PYTHON} ${FX_TOOLS}/compare.py features ${CMAKE_BINARY_DIR}/features_cmsis.csv ${FX_FIX}/reference_features.csv --work)
  set_tests_properties(m5_cmsis_extract PROPERTIES FIXTURES_SETUP m5cmsiscsv)
  set_tests_properties(m5_cmsis_agreement PROPERTIES FIXTURES_REQUIRED m5cmsiscsv)
endif()
