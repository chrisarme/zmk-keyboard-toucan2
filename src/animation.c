#include <dt-bindings/zmk/toucan_screen.h>
#include <toucan/animation.h>

uint8_t toucan_animation_fps(uint8_t screen) {
  switch (screen) {
  case TOUCAN_SCREEN_3:
    return 8;
  default:
    return 0;
  }
}

uint32_t toucan_animation_interval_ms(uint8_t screen) {
  uint8_t fps = toucan_animation_fps(screen);
  return fps == 0 ? 0 : 1000U / fps;
}

uint8_t toucan_animation_next_frame(uint8_t current_frame,
                                    uint8_t frame_count) {
  return frame_count == 0 ? 0 : (uint8_t)((current_frame + 1) % frame_count);
}
