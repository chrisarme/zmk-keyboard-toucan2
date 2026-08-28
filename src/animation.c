#include <dt-bindings/zmk/toucan_screen.h>
#include <toucan/animation.h>

uint32_t toucan_animation_interval_ms(uint8_t screen,
                                      uint16_t artwork_interval_ms) {
  return screen == TOUCAN_SCREEN_3 ? artwork_interval_ms : 0;
}

uint8_t toucan_animation_next_frame(uint8_t current_frame,
                                    uint8_t frame_count) {
  return frame_count == 0 ? 0 : (uint8_t)((current_frame + 1) % frame_count);
}
