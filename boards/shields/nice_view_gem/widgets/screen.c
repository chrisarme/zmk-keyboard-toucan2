#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#if IS_ENABLED(CONFIG_TOUCAN_STATUS_SCREEN_PERSIST)
#include <zephyr/settings/settings.h>
#endif

#include <zephyr/logging/log.h>
LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#include <zmk/event_manager.h>
#include <zmk/events/activity_state_changed.h>
#include <zmk/events/battery_state_changed.h>
#include <zmk/events/split_peripheral_status_changed.h>
#include <zmk/events/ble_active_profile_changed.h>
#include <zmk/events/endpoint_changed.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/usb_conn_state_changed.h>
#include <zmk/events/wpm_state_changed.h>
#include <zmk/battery.h>
#include <zmk/ble.h>
#include <zmk/display.h>
#include <zmk/display/widgets/battery_status.h>
#include <zmk/endpoints.h>
#include <zmk/keymap.h>
#include <zmk/usb.h>
#include <zmk/split/central.h>

#include "battery.h"
#include "battery_peripheral.h"
#include "artwork_registry.h"
#include "chart.h"
#include "layer.h"
#include "output.h"

#include "screen.h"
#include "screen_layout.h"
#include "sleep.h"

#include <toucan/screen.h>
#include <toucan/animation.h>
#include <toucan/artwork.h>
#include <toucan/artwork_selection.h>
#include <toucan/screen_selection.h>

struct connection_status_state {
    bool connected;
};

static sys_slist_t widgets = SYS_SLIST_STATIC_INIT(&widgets);
static atomic_t requested_screen = ATOMIC_INIT(CONFIG_TOUCAN_STATUS_SCREEN);
static atomic_t requested_artwork = ATOMIC_INIT(0);
static atomic_t animation_activity_active = ATOMIC_INIT(1);
static uint8_t active_screen = CONFIG_TOUCAN_STATUS_SCREEN;
static uint8_t active_artwork;
static uint8_t animation_frame;

static void force_redraw_all_widgets(void);
static void update_animation_schedule(void);

static void animation_work_cb(struct k_work *work) {
    ARG_UNUSED(work);

    const struct toucan_artwork *artwork = toucan_artwork_get(active_artwork);
    uint8_t frame_count = artwork == NULL ? 0 : *artwork->frame_count;
    if (!atomic_get(&animation_activity_active) || artwork == NULL ||
        toucan_animation_interval_ms(active_screen, artwork->interval_ms) == 0 ||
        frame_count < 2) {
        return;
    }

    animation_frame = toucan_animation_next_frame(animation_frame, frame_count);
    force_redraw_all_widgets();
    update_animation_schedule();
}

K_WORK_DELAYABLE_DEFINE(animation_work, animation_work_cb);

static void update_animation_schedule(void) {
    const struct toucan_artwork *artwork = toucan_artwork_get(active_artwork);
    uint8_t frame_count = artwork == NULL ? 0 : *artwork->frame_count;
    uint32_t interval_ms = artwork == NULL
                               ? 0
                               : toucan_animation_interval_ms(
                                     active_screen, artwork->interval_ms);
    if (!atomic_get(&animation_activity_active) || interval_ms == 0 ||
        frame_count < 2) {
        /* A queued callback may still run, but it rechecks both conditions above. */
        (void)k_work_cancel_delayable(&animation_work);
        return;
    }

    int result = k_work_reschedule_for_queue(
        zmk_display_work_q(), &animation_work, K_MSEC(interval_ms));
    if (result < 0) {
        LOG_WRN("Failed to schedule display animation: %d", result);
    }
}

#if IS_ENABLED(CONFIG_TOUCAN_STATUS_SCREEN_PERSIST)
#define SETTINGS_DIRTY_SCREEN BIT(0)
#define SETTINGS_DIRTY_ARTWORK BIT(1)

static atomic_t settings_dirty;

static void mark_settings_dirty(atomic_val_t mask) {
    atomic_val_t current;

    do {
        current = atomic_get(&settings_dirty);
    } while (!atomic_cas(&settings_dirty, current, current | mask));
}

static atomic_val_t take_settings_dirty(void) {
    atomic_val_t current;

    do {
        current = atomic_get(&settings_dirty);
    } while (!atomic_cas(&settings_dirty, current, 0));

    return current;
}

static void screen_save_work_cb(struct k_work *work) {
    ARG_UNUSED(work);

    atomic_val_t dirty = take_settings_dirty();

    if (dirty & SETTINGS_DIRTY_SCREEN) {
        uint8_t screen = (uint8_t)atomic_get(&requested_screen);
        int err = settings_save_one("toucan/screen", &screen, sizeof(screen));
        if (err < 0) {
            LOG_WRN("Failed to persist status screen: %d", err);
        }
    }

    if (dirty & SETTINGS_DIRTY_ARTWORK) {
        uint8_t artwork = (uint8_t)atomic_get(&requested_artwork);
        int err = settings_save_one("toucan/artwork", &artwork, sizeof(artwork));
        if (err < 0) {
            LOG_WRN("Failed to persist artwork: %d", err);
        }
    }
}

K_WORK_DELAYABLE_DEFINE(screen_save_work, screen_save_work_cb);

static int screen_settings_load_cb(const char *name, size_t len,
                                   settings_read_cb read_cb, void *cb_arg) {
    const char *next;
    uint8_t persisted;
    uint8_t selected;
    bool is_screen = settings_name_steq(name, "screen", &next) && next == NULL;
    bool is_artwork = settings_name_steq(name, "artwork", &next) && next == NULL;

    if (!is_screen && !is_artwork) {
        return -ENOENT;
    }

    if (len != sizeof(persisted)) {
        LOG_WRN("Ignoring invalid persisted Toucan setting length: %u",
                (unsigned int)len);
        return 0;
    }

    int err = read_cb(cb_arg, &persisted, sizeof(persisted));
    if (err != sizeof(persisted)) {
        LOG_WRN("Ignoring unreadable persisted Toucan setting: %d", err);
        return 0;
    }

    err = is_screen
              ? toucan_screen_restore(persisted, &selected)
              : toucan_artwork_restore(persisted, toucan_artwork_count(), &selected);
    if (err < 0) {
        LOG_WRN("Ignoring invalid persisted %s: %u",
                is_screen ? "status screen" : "artwork", persisted);
        return 0;
    }

    atomic_set(is_screen ? &requested_screen : &requested_artwork, selected);
    return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(toucan_screen, "toucan", NULL, screen_settings_load_cb, NULL,
                               NULL);
#endif

static void screen_change_work_cb(struct k_work *work) {
    ARG_UNUSED(work);
    active_screen = (uint8_t)atomic_get(&requested_screen);
    active_artwork = (uint8_t)atomic_get(&requested_artwork);
    animation_frame = 0;
    force_redraw_all_widgets();
    update_animation_schedule();
}

K_WORK_DEFINE(screen_change_work, screen_change_work_cb);

int toucan_screen_request(uint32_t command) {
    atomic_val_t current;
    uint8_t selected;
    int err;

    do {
        current = atomic_get(&requested_screen);
        err = toucan_screen_resolve((uint8_t)current, command, &selected);
        if (err < 0) {
            return err;
        }
        if (current == selected) {
            return 0;
        }
    } while (!atomic_cas(&requested_screen, current, selected));

#if IS_ENABLED(CONFIG_TOUCAN_STATUS_SCREEN_PERSIST)
    mark_settings_dirty(SETTINGS_DIRTY_SCREEN);
    k_work_reschedule(&screen_save_work, K_MSEC(CONFIG_ZMK_SETTINGS_SAVE_DEBOUNCE));
#endif

    if (zmk_display_is_initialized()) {
        k_work_submit_to_queue(zmk_display_work_q(), &screen_change_work);
    }

    return 0;
}

int toucan_artwork_request(uint32_t command) {
    atomic_val_t current;
    uint8_t selected;
    int err;

    do {
        current = atomic_get(&requested_artwork);
        err = toucan_artwork_resolve((uint8_t)current, command,
                                     toucan_artwork_count(), &selected);
        if (err < 0) {
            return err;
        }
        if (current == selected) {
            return 0;
        }
    } while (!atomic_cas(&requested_artwork, current, selected));

#if IS_ENABLED(CONFIG_TOUCAN_STATUS_SCREEN_PERSIST)
    mark_settings_dirty(SETTINGS_DIRTY_ARTWORK);
    k_work_reschedule(&screen_save_work, K_MSEC(CONFIG_ZMK_SETTINGS_SAVE_DEBOUNCE));
#endif

    if (zmk_display_is_initialized()) {
        k_work_submit_to_queue(zmk_display_work_q(), &screen_change_work);
    }

    return 0;
}

/**
 * Draw buffers
 **/

static void draw_top(lv_obj_t *widget, const struct status_state *state) {
    lv_obj_t *canvas = lv_obj_get_child(widget, 0);
    fill_background(canvas);

    if (is_sleep_screen_active()) {
        draw_sleep_screen(canvas);
        return;
    }

    draw_toucan_status_layout(canvas, state, active_screen, active_artwork,
                              animation_frame);
}

/**
 * Battery status
 **/
// L
static void set_battery_status(struct zmk_widget_screen *widget,
                               struct battery_status_state state) {
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
    widget->state.charging = state.usb_present;
#endif /* IS_ENABLED(CONFIG_USB_DEVICE_STACK) */
    widget->state.battery = state.level;

    draw_top(widget->obj, &widget->state);
}

static void battery_status_update_cb(struct battery_status_state state) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { set_battery_status(widget, state); }
}

static struct battery_status_state battery_status_get_state(const zmk_event_t *eh) {
    const struct zmk_battery_state_changed *ev = as_zmk_battery_state_changed(eh);

    return (struct battery_status_state){
        .level = (ev != NULL) ? ev->state_of_charge : zmk_battery_state_of_charge(),
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
        .usb_present = zmk_usb_is_powered(),
#endif /* IS_ENABLED(CONFIG_USB_DEVICE_STACK) */
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_battery_status, struct battery_status_state,
                            battery_status_update_cb, battery_status_get_state);

ZMK_SUBSCRIPTION(widget_battery_status, zmk_battery_state_changed);
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
ZMK_SUBSCRIPTION(widget_battery_status, zmk_usb_conn_state_changed);
#endif /* IS_ENABLED(CONFIG_USB_DEVICE_STACK) */

// R
static void set_battery_peripheral_status(struct zmk_widget_screen *widget,
                               struct battery_peripheral_status_state state) {
    uint8_t level;
    zmk_split_central_get_peripheral_battery_level(0, &level);

    widget->state.battery_p = level;
    draw_top(widget->obj, &widget->state);
}

static void battery_peripheral_status_update_cb(struct battery_peripheral_status_state state) {
    struct zmk_widget_screen *widget;

    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { set_battery_peripheral_status(widget, state); }
}

static struct battery_peripheral_status_state battery_peripheral_status_get_state(const zmk_event_t *eh) {
    const struct zmk_peripheral_battery_state_changed *ev = as_zmk_peripheral_battery_state_changed(eh);


    return (struct battery_peripheral_status_state){
        .level = ev->state_of_charge,
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_battery_peripheral_status, struct battery_peripheral_status_state,
                            battery_peripheral_status_update_cb, battery_peripheral_status_get_state);

ZMK_SUBSCRIPTION(widget_battery_peripheral_status, zmk_peripheral_battery_state_changed);

/**
 * Layer status
 **/

static void set_layer_status(struct zmk_widget_screen *widget, struct layer_status_state state) {
    widget->state.layer_index = zmk_keymap_highest_layer_active();
    draw_top(widget->obj, &widget->state);
}

static void layer_status_update_cb(struct layer_status_state state) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { set_layer_status(widget, state); }
}

static struct layer_status_state layer_status_get_state(const zmk_event_t *eh) {
    uint8_t index = zmk_keymap_highest_layer_active();
    return (struct layer_status_state) {
        .index = index
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_layer_status, struct layer_status_state, layer_status_update_cb,
                            layer_status_get_state)

ZMK_SUBSCRIPTION(widget_layer_status, zmk_layer_state_changed);

/**
 * Output status
 **/

static void set_output_status(struct zmk_widget_screen *widget,
                              const struct output_status_state *state) {
    widget->state.selected_endpoint = state->selected_endpoint;
    widget->state.active_profile_index = state->active_profile_index;
    widget->state.active_profile_connected = state->active_profile_connected;
    widget->state.active_profile_bonded = state->active_profile_bonded;

    draw_top(widget->obj, &widget->state);
}

static void output_status_update_cb(struct output_status_state state) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { set_output_status(widget, &state); }
}

static struct output_status_state output_status_get_state(const zmk_event_t *_eh) {
    return (struct output_status_state){
        .selected_endpoint = zmk_endpoints_selected(),
        .active_profile_index = zmk_ble_active_profile_index(),
        .active_profile_connected = zmk_ble_active_profile_is_connected(),
        .active_profile_bonded = !zmk_ble_active_profile_is_open(),
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_output_status, struct output_status_state,
                            output_status_update_cb, output_status_get_state)
ZMK_SUBSCRIPTION(widget_output_status, zmk_endpoint_changed);

#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
ZMK_SUBSCRIPTION(widget_output_status, zmk_usb_conn_state_changed);
#endif
#if defined(CONFIG_ZMK_BLE)
ZMK_SUBSCRIPTION(widget_output_status, zmk_ble_active_profile_changed);
#endif

/**
 * Activity state handling for sleep screen
 **/

static void force_redraw_all_widgets(void) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) {
        draw_top(widget->obj, &widget->state);
    }
}

static int display_activity_event_handler(const zmk_event_t *eh) {
    struct zmk_activity_state_changed *ev = as_zmk_activity_state_changed(eh);
    if (ev == NULL) {
        return -ENOTSUP;
    }

    switch (ev->state) {
    case ZMK_ACTIVITY_ACTIVE:
        atomic_set(&animation_activity_active, 1);
        set_sleep_screen_active(false);
        if (zmk_display_is_initialized()) {
            int result =
                k_work_submit_to_queue(zmk_display_work_q(), &screen_change_work);
            if (result < 0) {
                LOG_WRN("Failed to resume display animation: %d", result);
            }
        }
        break;
    case ZMK_ACTIVITY_IDLE:
        atomic_clear(&animation_activity_active);
        update_animation_schedule();
        break;
    case ZMK_ACTIVITY_SLEEP:
        atomic_clear(&animation_activity_active);
        update_animation_schedule();
        set_sleep_screen_active(true);
        force_redraw_all_widgets();
        // Force LVGL to process pending updates and flush to display hardware
        // before the CPU enters deep sleep
        lv_task_handler();
        lv_refr_now(NULL);
        break;
    default:
        break; // ignore other states (like IDLE)
    }
    return 0;
}

ZMK_LISTENER(nice_view_gem_display, display_activity_event_handler);
ZMK_SUBSCRIPTION(nice_view_gem_display, zmk_activity_state_changed);

/**
 * WPM status
 */
static void set_chart_status(struct zmk_widget_screen *widget, struct chart_status_state state) {
    widget->state.wpm = state.wpm;
    draw_top(widget->obj, &widget->state);
}

static void chart_status_update_cb(struct chart_status_state state) {
    struct zmk_widget_screen *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) {
        set_chart_status(widget, state);
    }
}

static struct chart_status_state chart_status_get_state(const zmk_event_t *eh) {
    const struct zmk_wpm_state_changed *ev = as_zmk_wpm_state_changed(eh);
    return (struct chart_status_state){
        .wpm = (ev != NULL) ? ev->state : zmk_wpm_get_state(),
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_chart_status, struct chart_status_state,
                            chart_status_update_cb, chart_status_get_state);
ZMK_SUBSCRIPTION(widget_chart_status, zmk_wpm_state_changed);

/**
 * Initialization
 **/

int zmk_widget_screen_init(struct zmk_widget_screen *widget, lv_obj_t *parent) {
    active_screen = (uint8_t)atomic_get(&requested_screen);
    active_artwork = (uint8_t)atomic_get(&requested_artwork);
    widget->obj = lv_obj_create(parent);
    lv_obj_set_size(widget->obj, SCREEN_WIDTH, SCREEN_HEIGHT);

    lv_obj_t *top = lv_canvas_create(widget->obj);
    lv_obj_align(top, LV_ALIGN_TOP_RIGHT, 0, 0);
    lv_canvas_set_buffer(top, widget->cbuf, SCREEN_WIDTH, SCREEN_HEIGHT, LV_IMG_CF_TRUE_COLOR);

    sys_slist_append(&widgets, &widget->node);
    widget_battery_status_init();
    widget_battery_peripheral_status_init();
    widget_layer_status_init();
    widget_output_status_init();

    widget_chart_status_init();

    update_animation_schedule();

    return 0;
}

lv_obj_t *zmk_widget_screen_obj(struct zmk_widget_screen *widget) { return widget->obj; }

