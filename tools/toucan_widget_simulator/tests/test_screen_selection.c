#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>

#include <dt-bindings/zmk/toucan_screen.h>
#include <dt-bindings/zmk/toucan_artwork.h>
#include <toucan/animation.h>
#include <toucan/artwork_selection.h>
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

  assert(toucan_animation_interval_ms(TOUCAN_SCREEN_2, 200) == 0);
  assert(toucan_animation_interval_ms(TOUCAN_SCREEN_3, 200) == 200);
  assert(toucan_animation_next_frame(0, 9) == 1);
  assert(toucan_animation_next_frame(8, 9) == 0);
  assert(toucan_animation_next_frame(8, 0) == 0);

  selected = 99;
  assert(toucan_artwork_resolve(0, TOUCAN_ARTWORK_NEXT, 2, &selected) == 0);
  assert(selected == 1);
  assert(toucan_artwork_resolve(0, TOUCAN_ARTWORK_PREV, 2, &selected) == 0);
  assert(selected == 1);
  selected = 99;
  assert(toucan_artwork_resolve(0, TOUCAN_ARTWORK_1, 2, &selected) == 0);
  assert(selected == 1);
  selected = 99;
  assert(toucan_artwork_restore(1, 2, &selected) == 0);
  assert(selected == 1);
  assert(toucan_artwork_restore(2, 2, &selected) == -EINVAL);
  assert(selected == 1);

  return 0;
}
