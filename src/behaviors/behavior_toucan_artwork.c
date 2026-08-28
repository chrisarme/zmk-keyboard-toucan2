#define DT_DRV_COMPAT zmk_behavior_toucan_artwork

#include <errno.h>

#include <zephyr/device.h>
#include <zephyr/logging/log.h>

#include <drivers/behavior.h>
#include <zmk/behavior.h>

#include <toucan/artwork.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

static int on_toucan_artwork_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
  ARG_UNUSED(event);

#if (!IS_ENABLED(CONFIG_ZMK_SPLIT) ||                                          \
     IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)) &&                             \
    IS_ENABLED(CONFIG_NICE_VIEW_WIDGET_STATUS)
  int err = toucan_artwork_request(binding->param1);
  return err < 0 ? err : ZMK_BEHAVIOR_OPAQUE;
#else
  return ZMK_BEHAVIOR_OPAQUE;
#endif
}

static int on_toucan_artwork_released(struct zmk_behavior_binding *binding,
                                      struct zmk_behavior_binding_event event) {
  ARG_UNUSED(binding);
  ARG_UNUSED(event);
  return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api toucan_artwork_driver_api = {
    .binding_pressed = on_toucan_artwork_pressed,
    .binding_released = on_toucan_artwork_released,
    .locality = BEHAVIOR_LOCALITY_CENTRAL,
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT,
                        &toucan_artwork_driver_api);

#endif
