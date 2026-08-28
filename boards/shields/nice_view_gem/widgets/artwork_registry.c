#include "artwork_registry.h"

#include <stddef.h>

#include <dt-bindings/zmk/toucan_artwork.h>

extern const lv_img_dsc_t *const naotogif_frames[];
extern const uint8_t naotogif_frame_count;
extern const lv_img_dsc_t *const darkSoulsBonfire_frames[];
extern const uint8_t darkSoulsBonfire_frame_count;

static const struct toucan_artwork artwork_registry[] = {
    {
        .frames = naotogif_frames,
        .frame_count = &naotogif_frame_count,
        .interval_ms = 200,
        .x = 1,
        .y = 2,
    },
    {
        .frames = darkSoulsBonfire_frames,
        .frame_count = &darkSoulsBonfire_frame_count,
        .interval_ms = 200,
        .x = 1,
        .y = 2,
    },
};

_Static_assert(sizeof(artwork_registry) / sizeof(artwork_registry[0]) ==
                   TOUCAN_ARTWORK_COUNT,
               "artwork constants must match the registry");

uint8_t toucan_artwork_count(void) { return TOUCAN_ARTWORK_COUNT; }

const struct toucan_artwork *toucan_artwork_get(uint8_t index) {
  return index < toucan_artwork_count() ? &artwork_registry[index] : NULL;
}
