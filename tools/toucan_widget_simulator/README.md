# Toucan widget simulator

This host-side tool renders any of the Toucan's four screens into a 144×168 monochrome BMP without building or flashing the keyboard firmware. It uses the same LVGL revision as this ZMK version and compiles the real widget, image, and font sources from the shield.

It provides both a command-line renderer and an interactive desktop preview. It is not a full emulation of ZMK events or display hardware.

## Requirements

- CMake 3.24 or newer
- Ninja
- Clang with a usable Windows C runtime
- Python 3 with Tkinter for the interactive preview and tests (included in standard Windows Python installs)
- Internet access on the first configure, when CMake downloads the pinned LVGL source

## Build

Run these commands from the repository root:

```powershell
cmake -S tools/toucan_widget_simulator -B tools/toucan_widget_simulator/build -G Ninja -DCMAKE_C_COMPILER=clang -DCMAKE_BUILD_TYPE=Debug
cmake --build tools/toucan_widget_simulator/build --target toucan_widget_simulator
```

Building the named target avoids compiling LVGL's bundled examples.

## Open the interactive preview

Build the renderer once, then launch the desktop control panel:

```powershell
python tools/toucan_widget_simulator/preview_gui.py
```

The window magnifies the physical 144×168 display to 432×504. Screen style, battery levels, WPM, layer, Bluetooth profile, endpoint, connection, and charging controls update the preview automatically after a short debounce. The renderer reverses the logical LVGL monochrome polarity at export time to match the physical Memory LCD: logical white becomes dark ink and logical black becomes the unfilled light background.

**Layer #** is the zero-based layer number used internally by ZMK. When **Name** is filled in, that name is displayed and the number has no visible effect. When **Name** is blank, the screen uses the number as a fallback label such as `L#2`.

## Render from the command line

```powershell
New-Item -ItemType Directory -Force tools/toucan_widget_simulator/previews | Out-Null
& tools/toucan_widget_simulator/build/toucan_widget_simulator.exe `
  --screen 2 `
  --left-battery 75 `
  --right-battery 40 `
  --wpm 80 `
  --layer 2 `
  --layer-name NAV `
  --profile 3 `
  --endpoint ble `
  --connected `
  --output tools/toucan_widget_simulator/previews/full-status.bmp
```

Build products and generated previews are ignored by Git.

## Preview options

| Option | Accepted values | Default | Effect |
| --- | --- | --- | --- |
| `--screen` | 0–3 | 2 | Layout: standard, Toucan logo, arcs/WPM, or image-only Naoto art |
| `--left-battery` | 0–100 | 75 | Left-half battery percentage |
| `--right-battery` | 0–100 | 50 | Right-half battery percentage |
| `--wpm` | 0–255 | 0 | Adds the newest sample to the WPM chart |
| `--layer` | 0–255 | 0 | Layer index used by the fallback `L#n` label |
| `--layer-name` | Text | None | Named layer label, such as `NAV` |
| `--profile` | 0–4 | 0 | Filled Bluetooth profile square |
| `--endpoint` | `usb`, `ble`, or `none` | `ble` | Output type |
| `--connected` | Flag | Off | Shows `BLE` for a BLE endpoint; without it BLE shows `NULL` |
| `--left-charging` | Flag | Off | Sets the real left charging state |
| `--right-charging` | Flag | Off | Sets the real right charging state |
| `--output` | BMP filename | Required | Output file to create |

The current battery widgets do not draw a charging glyph, so the charging flags do not visibly change the preview yet. The WPM widget appears only on screen 2 and stores history over time; a one-shot invocation therefore shows only its newest sample column. Screen 3 intentionally ignores all injected status values and displays only `naotoframe1`.

## Test

```powershell
ctest --test-dir tools/toucan_widget_simulator/build --output-on-failure
```

The tests check runtime selection commands, output dimensions, battery fill behavior, every supported screen layout, and the GUI-to-renderer state mapping.

## How it relates to the firmware

The executable creates an in-memory LVGL canvas at the display's real resolution, calls the same runtime layout dispatcher used by the firmware, then exports the canvas. Small compatibility headers stand in for the Zephyr and ZMK types those widgets expect on-device.

This makes widget layout and drawing logic representative of the firmware. It does not currently simulate timers, input events, display refresh behavior, or ZMK's event system. The command-line values are injected directly as one status snapshot.
