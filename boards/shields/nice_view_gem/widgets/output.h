#pragma once

#include <lvgl.h>
#include <zmk/endpoints.h>
#include "util.h"

void draw_output_standard_status(lv_obj_t *canvas, const struct status_state *state);
