#pragma once

#include <zephyr/kernel.h>

enum zmk_transport {
    ZMK_TRANSPORT_USB,
    ZMK_TRANSPORT_BLE,
    TOUCAN_SIMULATOR_TRANSPORT_NONE,
};

struct zmk_endpoint_instance {
    enum zmk_transport transport;
};
