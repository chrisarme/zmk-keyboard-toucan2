#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>

#include <dt-bindings/zmk/toucan_screen.h>
#include <toucan/animation.h>
#include <toucan/screen_selection.h>

int main(void) {
  uint8_t selected = 99;

  assert(toucan_screen_resolve(2, TOUCAN_SCREEN_0, &selected) == 0);
  assert(selected == 0);
  assert(toucan_screen_resolve(2, TOUCAN_SCREEN_NEXT, &selected) == 0);
  assert(selected == 3);
  assert(toucan_screen_resolve(3, TOUCAN_SCREEN_NEXT, &selected) == 0);
  assert(selected == 0);
  assert(toucan_screen_resolve(0, TOUCAN_SCREEN_PREV, &selected) == 0);
  assert(selected == 3);
  assert(toucan_screen_resolve(0, TOUCAN_SCREEN_3, &selected) == 0);
  assert(selected == 3);
  assert(toucan_screen_resolve(1, 99, &selected) == -EINVAL);
  assert(selected == 3);

  selected = 99;
  assert(toucan_screen_restore(1, &selected) == 0);
  assert(selected == 1);
  assert(toucan_screen_restore(3, &selected) == 0);
  assert(selected == 3);
  assert(toucan_screen_restore(TOUCAN_SCREEN_COUNT, &selected) == -EINVAL);
  assert(selected == 3);
  assert(toucan_screen_restore(0, NULL) == -EINVAL);

  assert(toucan_animation_fps(TOUCAN_SCREEN_2) == 0);
  assert(toucan_animation_fps(TOUCAN_SCREEN_3) == 8);
  assert(toucan_animation_interval_ms(TOUCAN_SCREEN_3) == 125);
  assert(toucan_animation_next_frame(0, 14) == 1);
  assert(toucan_animation_next_frame(13, 14) == 0);
  assert(toucan_animation_next_frame(13, 0) == 0);

  return 0;
}
