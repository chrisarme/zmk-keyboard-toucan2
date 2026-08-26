#include <errno.h>
#include <stddef.h>

#include <dt-bindings/zmk/toucan_screen.h>
#include <toucan/screen_selection.h>

int toucan_screen_restore(uint8_t persisted_screen, uint8_t *selected_screen) {
  if (selected_screen == NULL || persisted_screen >= TOUCAN_SCREEN_COUNT) {
    return -EINVAL;
  }

  *selected_screen = persisted_screen;
  return 0;
}

int toucan_screen_resolve(uint8_t current_screen, uint32_t command,
                          uint8_t *selected_screen) {
  if (selected_screen == NULL || current_screen >= TOUCAN_SCREEN_COUNT) {
    return -EINVAL;
  }

  switch (command) {
  case TOUCAN_SCREEN_0:
  case TOUCAN_SCREEN_1:
  case TOUCAN_SCREEN_2:
  case TOUCAN_SCREEN_3:
    *selected_screen = (uint8_t)command;
    return 0;
  case TOUCAN_SCREEN_NEXT:
    *selected_screen = (uint8_t)((current_screen + 1) % TOUCAN_SCREEN_COUNT);
    return 0;
  case TOUCAN_SCREEN_PREV:
    *selected_screen = (uint8_t)((current_screen + TOUCAN_SCREEN_COUNT - 1) %
                                 TOUCAN_SCREEN_COUNT);
    return 0;
  default:
    return -EINVAL;
  }
}
