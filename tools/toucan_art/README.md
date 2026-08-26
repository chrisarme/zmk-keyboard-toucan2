# Toucan Art Utility

This standalone development utility extracts the firmware's LVGL v8
`LV_IMG_CF_INDEXED_1BIT` C arrays as ordinary indexed PNG files. It is located under
`tools/`, outside the Zephyr module's `boards`, `config`, and `zephyr` source trees, and is
not included in firmware builds.

It uses only the Python standard library. No package installation is required.

## Extract the current artwork

From the repository root, run:

```powershell
py -3 tools/toucan_art/toucan_art.py extract `
    boards/shields/nice_view_gem `
    --output tools/toucan_art/previews `
    --gallery
```

This produces one lossless PNG per LVGL image plus
`tools/toucan_art/previews/index.html`. Open the HTML file in a browser to see a labeled,
pixel-scaled gallery. The `previews` directory is ignored by Git because it is generated
output.

Directory inputs are searched recursively for `.c` files. Files without supported image
descriptors, such as the font sources, are skipped. Header files are not scanned because
they normally contain declarations rather than the packed image data. Explicit file inputs
remain supported, and multiple files and directories may be supplied together.

You can also extract a single source file without generating a gallery:

```powershell
py -3 tools/toucan_art/toucan_art.py extract `
    boards/shields/nice_view_gem/assets/images.c `
    --output tools/toucan_art/previews
```

The generated PNGs preserve the descriptor dimensions, two-entry palette, row padding,
and exact one-bit pixel values. They can be opened in a browser or image editor.

## Run the tests

```powershell
py -3 -m unittest discover -s tools/toucan_art/tests -v
```

## Current scope

The utility currently extracts existing one-bit LVGL C assets for viewing and editing.
Static-image-to-C conversion and GIF frame conversion are planned separately.
