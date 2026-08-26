cmake_minimum_required(VERSION 3.24)

project(toucan_widget_simulator LANGUAGES C)

include(CTest)
include(FetchContent)

set(TOUCAN_LVGL_REVISION "8a6a2d1d29d17d1e4bdc94c243c146a39d635fdd")

FetchContent_Declare(
  lvgl
  GIT_REPOSITORY https://github.com/zephyrproject-rtos/lvgl.git
  GIT_TAG ${TOUCAN_LVGL_REVISION}
  GIT_SHALLOW FALSE
)
FetchContent_MakeAvailable(lvgl)

set(TOUCAN_WIDGET_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../boards/shields/nice_view_gem/widgets")
set(TOUCAN_ASSET_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../boards/shields/nice_view_gem/assets")

add_executable(
  toucan_widget_simulator
  src/main.c
  src/zmk_shims.c
  ${TOUCAN_WIDGET_DIR}/battery.c
  ${TOUCAN_WIDGET_DIR}/battery_arc.c
  ${TOUCAN_WIDGET_DIR}/battery_peripheral.c
  ${TOUCAN_WIDGET_DIR}/battery_arc_peripheral.c
  ${TOUCAN_WIDGET_DIR}/chart.c
  ${TOUCAN_WIDGET_DIR}/layer.c
  ${TOUCAN_WIDGET_DIR}/layer_arc.c
  ${TOUCAN_WIDGET_DIR}/layer_logo.c
  ${TOUCAN_WIDGET_DIR}/output.c
  ${TOUCAN_WIDGET_DIR}/output_arc.c
  ${TOUCAN_WIDGET_DIR}/profile.c
  ${TOUCAN_WIDGET_DIR}/profile_arc.c
  ${TOUCAN_WIDGET_DIR}/screen_layout.c
  ${TOUCAN_WIDGET_DIR}/util.c
  ${TOUCAN_ASSET_DIR}/images.c
  ${TOUCAN_ASSET_DIR}/naotogif.c
  ${TOUCAN_ASSET_DIR}/quinquefive_8.c
  ${TOUCAN_ASSET_DIR}/quinquefive_12.c
  ${TOUCAN_ASSET_DIR}/quinquefive_18.c
  ${TOUCAN_ASSET_DIR}/quinquefive_24.c
)

target_include_directories(
  toucan_widget_simulator
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/shims
    ${TOUCAN_WIDGET_DIR}
    ${TOUCAN_ASSET_DIR}
)

target_compile_definitions(
  lvgl
  PUBLIC
    LV_CONF_PATH=${CMAKE_CURRENT_SOURCE_DIR}/lv_conf.h
)

target_compile_definitions(
  toucan_widget_simulator
  PRIVATE
    CONFIG_ZMK_SPLIT=0
    CONFIG_ZMK_SPLIT_ROLE_CENTRAL=1
    CONFIG_USB_DEVICE_STACK=0
    CONFIG_TOUCAN_STATUS_SCREEN=2
    _CRT_SECURE_NO_WARNINGS
)

target_link_libraries(toucan_widget_simulator PRIVATE lvgl)

if(BUILD_TESTING)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_executable(
    screen_selection_test
    tests/test_screen_selection.c
    ../../src/animation.c
    ../../src/screen_selection.c
  )
  target_include_directories(
    screen_selection_test
    PRIVATE
      ../../include
  )
  add_test(NAME resolves_runtime_screen_commands COMMAND screen_selection_test)
  add_test(
    NAME renders_battery_arc_state
    COMMAND
      ${Python3_EXECUTABLE}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/verify_battery_preview.py
      $<TARGET_FILE:toucan_widget_simulator>
      ${CMAKE_CURRENT_BINARY_DIR}/battery-preview.bmp
  )
  add_test(
    NAME renders_full_status_state
    COMMAND
      ${Python3_EXECUTABLE}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/verify_full_status_preview.py
      $<TARGET_FILE:toucan_widget_simulator>
      ${CMAKE_CURRENT_BINARY_DIR}/full-status-preview.bmp
  )
  add_test(
    NAME maps_gui_state_to_renderer_options
    COMMAND
      ${Python3_EXECUTABLE}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_preview_gui.py
  )
  add_test(
    NAME renders_all_runtime_screen_styles
    COMMAND
      ${Python3_EXECUTABLE}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/verify_screen_styles.py
      $<TARGET_FILE:toucan_widget_simulator>
      ${CMAKE_CURRENT_BINARY_DIR}/screen-styles
  )
endif()
