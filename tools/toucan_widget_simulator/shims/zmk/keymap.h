#pragma once

#include <stdint.h>

uint8_t zmk_keymap_layer_index_to_id(uint8_t layer_index);
const char *zmk_keymap_layer_name(uint8_t layer_id);

void toucan_simulator_set_layer_name(const char *layer_name);
