#include "screen_layout.h"

#include <stdio.h>

#include "../assets/custom_fonts.h"
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

extern const lv_img_dsc_t *const naotogif_frames[];
extern const uint8_t naotogif_frame_count;

#define IMAGE_FOOTER_Y 144
#define IMAGE_PROFILE_X 48
#define IMAGE_PROFILE_Y 152
#define IMAGE_PROFILE_SIZE 8
#define IMAGE_PROFILE_SPACING 10
#define IMAGE_PROFILE_COUNT 5

static void draw_standard_status(lv_obj_t *canvas,
                                 const struct status_state *state) {
  draw_output_standard_status(canvas, state);
  draw_profile_standard_status(canvas, state);
  draw_battery_standard_status(canvas, state);
  draw_battery_peripheral_standard_status(canvas, state);
}

static void draw_footer_rect(lv_obj_t *canvas, lv_coord_t x, lv_coord_t y,
                             lv_coord_t width, lv_coord_t height,
                             lv_color_t color) {
  lv_draw_rect_dsc_t descriptor;
  init_rect_dsc(&descriptor, color);
  lv_canvas_draw_rect(canvas, x, y, width, height, &descriptor);
}

static void draw_footer_battery(lv_obj_t *canvas, lv_coord_t x,
                                const char *side, uint8_t level) {
  char label[5];
  snprintf(label, sizeof(label), "%s%u", side, (unsigned int)level);

  lv_draw_label_dsc_t descriptor;
  init_label_dsc(&descriptor, LVGL_FOREGROUND, &quinquefive_8,
                 LV_TEXT_ALIGN_CENTER);
  lv_canvas_draw_text(canvas, x, 151, 40, &descriptor, label);
}

static void draw_footer_profiles(lv_obj_t *canvas,
                                 int active_profile_index) {
  for (int profile = 0; profile < IMAGE_PROFILE_COUNT; profile++) {
    lv_coord_t x = IMAGE_PROFILE_X + (profile * IMAGE_PROFILE_SPACING);
    draw_footer_rect(canvas, x, IMAGE_PROFILE_Y, IMAGE_PROFILE_SIZE,
                     IMAGE_PROFILE_SIZE, LVGL_FOREGROUND);

    if (profile != active_profile_index) {
      draw_footer_rect(canvas, x + 1, IMAGE_PROFILE_Y + 1,
                       IMAGE_PROFILE_SIZE - 2, IMAGE_PROFILE_SIZE - 2,
                       LVGL_BACKGROUND);
    }
  }
}

static void draw_art_footer(lv_obj_t *canvas,
                            const struct status_state *state) {
  /* Match the other screens: light panel background with dark status ink. */
  draw_footer_rect(canvas, 0, IMAGE_FOOTER_Y, SCREEN_WIDTH,
                   SCREEN_HEIGHT - IMAGE_FOOTER_Y, LVGL_BACKGROUND);
  draw_footer_battery(canvas, 0, "L", state->battery);
  draw_footer_profiles(canvas, state->active_profile_index);
  draw_footer_battery(canvas, 104, "R", state->battery_p);
}

static void draw_animation_status(lv_obj_t *canvas,
                                  const struct status_state *state,
                                  uint8_t animation_frame) {
  lv_draw_img_dsc_t image_descriptor;
  lv_draw_img_dsc_init(&image_descriptor);
  const lv_img_dsc_t *frame =
      naotogif_frames[animation_frame % naotogif_frame_count];
  lv_canvas_draw_img(canvas, 1, 2, frame, &image_descriptor);
  draw_art_footer(canvas, state);
}

void draw_toucan_status_layout(lv_obj_t *canvas,
                               const struct status_state *state,
                               uint8_t screen,
                               uint8_t animation_frame) {
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
  case 3:
    draw_animation_status(canvas, state, animation_frame);
    break;
  default:
    break;
  }
}
