#include <errno.h>
#include <stddef.h>

#include <dt-bindings/zmk/toucan_artwork.h>
#include <toucan/artwork_selection.h>

int toucan_artwork_resolve(uint8_t current_artwork, uint32_t command,
                           uint8_t artwork_count, uint8_t *selected_artwork) {
  if (selected_artwork == NULL || artwork_count == 0 ||
      current_artwork >= artwork_count) {
    return -EINVAL;
  }

  if (command < artwork_count) {
    *selected_artwork = (uint8_t)command;
    return 0;
  }
  if (command == TOUCAN_ARTWORK_NEXT) {
    *selected_artwork = (uint8_t)((current_artwork + 1) % artwork_count);
    return 0;
  }
  if (command == TOUCAN_ARTWORK_PREV) {
    *selected_artwork = (uint8_t)((current_artwork + artwork_count - 1) %
                                  artwork_count);
    return 0;
  }

  return -EINVAL;
}

int toucan_artwork_restore(uint8_t persisted_artwork, uint8_t artwork_count,
                           uint8_t *selected_artwork) {
  if (selected_artwork == NULL || artwork_count == 0 ||
      persisted_artwork >= artwork_count) {
    return -EINVAL;
  }

  *selected_artwork = persisted_artwork;
  return 0;
}
