#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <lvgl.h>
#include <zmk/keymap.h>

#include "screen_layout.h"
#include "util.h"

static lv_disp_draw_buf_t display_draw_buffer;
static lv_color_t display_pixels[SCREEN_WIDTH * 10];
static lv_color_t canvas_pixels[SCREEN_WIDTH * SCREEN_HEIGHT];

struct preview_options {
    int screen;
    int animation_frame;
    int left_battery;
    int right_battery;
    int wpm;
    int layer;
    const char *layer_name;
    int profile;
    enum zmk_transport endpoint;
    bool connected;
    bool left_charging;
    bool right_charging;
    const char *output_path;
};

static void flush_display(lv_disp_drv_t *display_driver, const lv_area_t *area,
                          lv_color_t *pixels) {
    (void)area;
    (void)pixels;
    lv_disp_flush_ready(display_driver);
}

static int parse_percentage(const char *text, const char *option_name) {
    char *end = NULL;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || value < 0 || value > 100) {
        fprintf(stderr, "%s must be an integer from 0 to 100\n", option_name);
        return -1;
    }
    return (int)value;
}

static int parse_bounded_integer(const char *text, const char *option_name, int maximum) {
    char *end = NULL;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || value < 0 || value > maximum) {
        fprintf(stderr, "%s must be an integer from 0 to %d\n", option_name, maximum);
        return -1;
    }
    return (int)value;
}

static void write_u16(FILE *file, uint16_t value) {
    fputc(value & 0xff, file);
    fputc((value >> 8) & 0xff, file);
}

static void write_u32(FILE *file, uint32_t value) {
    fputc(value & 0xff, file);
    fputc((value >> 8) & 0xff, file);
    fputc((value >> 16) & 0xff, file);
    fputc((value >> 24) & 0xff, file);
}

static int write_canvas_bmp(lv_obj_t *canvas, const char *output_path) {
    const uint32_t row_size = (SCREEN_WIDTH * 3U + 3U) & ~3U;
    const uint32_t pixel_bytes = row_size * SCREEN_HEIGHT;
    const uint32_t pixel_offset = 14U + 40U;
    const uint32_t file_size = pixel_offset + pixel_bytes;
    FILE *file = fopen(output_path, "wb");
    if (file == NULL) {
        fprintf(stderr, "could not open output file: %s\n", output_path);
        return 1;
    }

    fputs("BM", file);
    write_u32(file, file_size);
    write_u16(file, 0);
    write_u16(file, 0);
    write_u32(file, pixel_offset);

    write_u32(file, 40);
    write_u32(file, SCREEN_WIDTH);
    write_u32(file, SCREEN_HEIGHT);
    write_u16(file, 1);
    write_u16(file, 24);
    write_u32(file, 0);
    write_u32(file, pixel_bytes);
    write_u32(file, 2835);
    write_u32(file, 2835);
    write_u32(file, 0);
    write_u32(file, 0);

    const uint32_t padding = row_size - SCREEN_WIDTH * 3U;
    for (int y = SCREEN_HEIGHT - 1; y >= 0; y--) {
        for (int x = 0; x < SCREEN_WIDTH; x++) {
            lv_color_t color = lv_canvas_get_px(canvas, x, y);
            // The physical Memory LCD displays the logical monochrome buffer
            // with reversed polarity: LVGL white is dark ink and LVGL black is
            // the unfilled light background.
            uint8_t value = lv_color_brightness(color) >= 128 ? 0 : 255;
            fputc(value, file);
            fputc(value, file);
            fputc(value, file);
        }
        for (uint32_t index = 0; index < padding; index++) {
            fputc(0, file);
        }
    }

    if (fclose(file) != 0) {
        fprintf(stderr, "could not finish output file: %s\n", output_path);
        return 1;
    }
    return 0;
}

static void print_usage(const char *program) {
    fprintf(stderr,
            "Usage: %s [--left-battery 0..100] [--right-battery 0..100] "
            "[--screen 0..6] [--animation-frame 0..127] "
            "[--wpm 0..255] [--layer 0..255] [--layer-name NAME] "
            "[--profile 0..4] [--endpoint usb|ble|none] [--connected] "
            "[--left-charging] [--right-charging] --output preview.bmp\n",
            program);
}

int main(int argc, char **argv) {
    struct preview_options options = {
        .screen = CONFIG_TOUCAN_STATUS_SCREEN,
        .animation_frame = 0,
        .left_battery = 75,
        .right_battery = 50,
        .wpm = 0,
        .layer = 0,
        .layer_name = NULL,
        .profile = 0,
        .endpoint = ZMK_TRANSPORT_BLE,
        .connected = false,
        .left_charging = false,
        .right_charging = false,
        .output_path = NULL,
    };

    for (int index = 1; index < argc; index++) {
        if (strcmp(argv[index], "--screen") == 0 && index + 1 < argc) {
            options.screen = parse_bounded_integer(argv[++index], "--screen", 6);
            if (options.screen < 0) return 2;
        } else if (strcmp(argv[index], "--animation-frame") == 0 && index + 1 < argc) {
            options.animation_frame =
                parse_bounded_integer(argv[++index], "--animation-frame", 127);
            if (options.animation_frame < 0) return 2;
        } else if (strcmp(argv[index], "--left-battery") == 0 && index + 1 < argc) {
            options.left_battery = parse_percentage(argv[++index], "--left-battery");
            if (options.left_battery < 0) {
                return 2;
            }
        } else if (strcmp(argv[index], "--right-battery") == 0 && index + 1 < argc) {
            options.right_battery = parse_percentage(argv[++index], "--right-battery");
            if (options.right_battery < 0) {
                return 2;
            }
        } else if (strcmp(argv[index], "--wpm") == 0 && index + 1 < argc) {
            options.wpm = parse_bounded_integer(argv[++index], "--wpm", UINT8_MAX);
            if (options.wpm < 0) return 2;
        } else if (strcmp(argv[index], "--layer") == 0 && index + 1 < argc) {
            options.layer = parse_bounded_integer(argv[++index], "--layer", UINT8_MAX);
            if (options.layer < 0) return 2;
        } else if (strcmp(argv[index], "--layer-name") == 0 && index + 1 < argc) {
            options.layer_name = argv[++index];
        } else if (strcmp(argv[index], "--profile") == 0 && index + 1 < argc) {
            options.profile = parse_bounded_integer(argv[++index], "--profile", 4);
            if (options.profile < 0) return 2;
        } else if (strcmp(argv[index], "--endpoint") == 0 && index + 1 < argc) {
            const char *endpoint = argv[++index];
            if (strcmp(endpoint, "usb") == 0) {
                options.endpoint = ZMK_TRANSPORT_USB;
            } else if (strcmp(endpoint, "ble") == 0) {
                options.endpoint = ZMK_TRANSPORT_BLE;
            } else if (strcmp(endpoint, "none") == 0) {
                options.endpoint = TOUCAN_SIMULATOR_TRANSPORT_NONE;
            } else {
                fprintf(stderr, "--endpoint must be usb, ble, or none\n");
                return 2;
            }
        } else if (strcmp(argv[index], "--connected") == 0) {
            options.connected = true;
        } else if (strcmp(argv[index], "--left-charging") == 0) {
            options.left_charging = true;
        } else if (strcmp(argv[index], "--right-charging") == 0) {
            options.right_charging = true;
        } else if (strcmp(argv[index], "--output") == 0 && index + 1 < argc) {
            options.output_path = argv[++index];
        } else {
            print_usage(argv[0]);
            return 2;
        }
    }

    if (options.output_path == NULL) {
        print_usage(argv[0]);
        return 2;
    }

    lv_init();
    lv_disp_draw_buf_init(&display_draw_buffer, display_pixels, NULL,
                          sizeof(display_pixels) / sizeof(display_pixels[0]));

    lv_disp_drv_t display_driver;
    lv_disp_drv_init(&display_driver);
    display_driver.hor_res = SCREEN_WIDTH;
    display_driver.ver_res = SCREEN_HEIGHT;
    display_driver.draw_buf = &display_draw_buffer;
    display_driver.flush_cb = flush_display;
    lv_disp_drv_register(&display_driver);

    lv_obj_t *canvas = lv_canvas_create(lv_scr_act());
    lv_canvas_set_buffer(canvas, canvas_pixels, SCREEN_WIDTH, SCREEN_HEIGHT, LV_IMG_CF_TRUE_COLOR);

    struct status_state state = {
        .battery = (uint8_t)options.left_battery,
        .battery_p = (uint8_t)options.right_battery,
        .charging = options.left_charging,
        .charging_p = options.right_charging,
        .wpm = (uint8_t)options.wpm,
        .selected_endpoint = {
            .transport = options.endpoint == ZMK_TRANSPORT_BLE && !options.connected
                             ? TOUCAN_SIMULATOR_TRANSPORT_NONE
                             : options.endpoint,
        },
        .active_profile_index = options.profile,
        .active_profile_connected = options.connected,
        .active_profile_bonded = true,
        .layer_index = (uint8_t)options.layer,
        .layer_label = options.layer_name,
    };
    toucan_simulator_set_layer_name(options.layer_name);
    fill_background(canvas);
    draw_toucan_status_layout(canvas, &state, (uint8_t)options.screen,
                              (uint8_t)options.animation_frame);

    int result = write_canvas_bmp(canvas, options.output_path);
    lv_deinit();
    return result;
}
