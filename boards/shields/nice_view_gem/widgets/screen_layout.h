#pragma once

#include <stdint.h>

#include <lvgl.h>

#include "util.h"

void draw_toucan_status_layout(lv_obj_t *canvas,
                               const struct status_state *state,
                               uint8_t screen);
