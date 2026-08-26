#pragma once

#include <stdint.h>

int toucan_screen_resolve(uint8_t current_screen, uint32_t command,
                          uint8_t *selected_screen);
