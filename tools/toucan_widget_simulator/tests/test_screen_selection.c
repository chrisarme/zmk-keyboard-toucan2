#include <assert.h>
#include <errno.h>
#include <stdint.h>

#include <dt-bindings/zmk/toucan_screen.h>
#include <toucan/screen_selection.h>

int main(void) {
  uint8_t selected = 99;

  assert(toucan_screen_resolve(2, TOUCAN_SCREEN_0, &selected) == 0);
  assert(selected == 0);
  assert(toucan_screen_resolve(2, TOUCAN_SCREEN_NEXT, &selected) == 0);
  assert(selected == 0);
  assert(toucan_screen_resolve(0, TOUCAN_SCREEN_PREV, &selected) == 0);
  assert(selected == 2);
  assert(toucan_screen_resolve(1, 99, &selected) == -EINVAL);
  assert(selected == 2);

  return 0;
}
