#pragma once

#include <stdint.h>

int toucan_screen_resolve(uint8_t current_screen, uint32_t command,
                          uint8_t *selected_screen);
int toucan_screen_restore(uint8_t persisted_screen, uint8_t *selected_screen);
