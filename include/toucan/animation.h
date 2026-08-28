#pragma once

#include <stdint.h>

uint32_t toucan_animation_interval_ms(uint8_t screen,
                                      uint16_t artwork_interval_ms);
uint8_t toucan_animation_next_frame(uint8_t current_frame, uint8_t frame_count);
