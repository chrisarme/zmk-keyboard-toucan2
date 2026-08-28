#pragma once

#include <stdint.h>

int toucan_artwork_resolve(uint8_t current_artwork, uint32_t command,
                           uint8_t artwork_count, uint8_t *selected_artwork);
int toucan_artwork_restore(uint8_t persisted_artwork, uint8_t artwork_count,
                           uint8_t *selected_artwork);
