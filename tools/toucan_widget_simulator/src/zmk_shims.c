#include <zmk/keymap.h>

static const char *active_layer_name;

uint8_t zmk_keymap_layer_index_to_id(uint8_t layer_index) {
    return layer_index;
}

const char *zmk_keymap_layer_name(uint8_t layer_id) {
    (void)layer_id;
    return active_layer_name;
}

void toucan_simulator_set_layer_name(const char *layer_name) {
    active_layer_name = layer_name;
}
