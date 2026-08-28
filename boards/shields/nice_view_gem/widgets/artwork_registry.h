#pragma once

#include <stdint.h>

#include <lvgl.h>

struct toucan_artwork {
  const lv_img_dsc_t *const *frames;
  const uint8_t *frame_count;
  uint16_t interval_ms;
  int8_t x;
  int8_t y;
};

uint8_t toucan_artwork_count(void);
const struct toucan_artwork *toucan_artwork_get(uint8_t index);
