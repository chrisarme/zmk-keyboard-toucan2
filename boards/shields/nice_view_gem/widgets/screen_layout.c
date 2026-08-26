#include "screen_layout.h"

#include "battery.h"
#include "battery_arc.h"
#include "battery_arc_peripheral.h"
#include "battery_peripheral.h"
#include "chart.h"
#include "layer.h"
#include "layer_arc.h"
#include "layer_logo.h"
#include "output.h"
#include "output_arc.h"
#include "profile.h"
#include "profile_arc.h"

LV_IMG_DECLARE(naotoframe1);

static void draw_standard_status(lv_obj_t *canvas,
                                 const struct status_state *state) {
  draw_output_standard_status(canvas, state);
  draw_profile_standard_status(canvas, state);
  draw_battery_standard_status(canvas, state);
  draw_battery_peripheral_standard_status(canvas, state);
}

void draw_toucan_status_layout(lv_obj_t *canvas,
                               const struct status_state *state,
                               uint8_t screen) {
  switch (screen) {
  case 0:
    draw_standard_status(canvas, state);
    draw_layer_standard_status(canvas, state);
    break;
  case 1:
    draw_standard_status(canvas, state);
    draw_layer_logo_status(canvas, state);
    break;
  case 2:
    draw_output_arc_status(canvas, state);
    draw_chart_status(canvas, state);
    draw_layer_arc_status(canvas, state);
    draw_profile_arc_status(canvas, state);
    draw_battery_arc_status(canvas, state);
    draw_battery_peripheral_arc_status(canvas, state);
    break;
  case 3: {
    lv_draw_img_dsc_t image_descriptor;
    lv_draw_img_dsc_init(&image_descriptor);
    lv_canvas_draw_img(canvas, 0, (SCREEN_HEIGHT - naotoframe1.header.h) / 2,
                       &naotoframe1, &image_descriptor);
    break;
  }
  default:
    break;
  }
}
