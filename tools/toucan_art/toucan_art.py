#!/usr/bin/env python3
"""Convert and extract LVGL v8 indexed one-bit display images."""

from __future__ import annotations

import argparse
import binascii
import html
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
STATIC_IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
C_KEYWORDS = {
    "auto",
    "break",
    "case",
    "char",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "inline",
    "int",
    "long",
    "register",
    "restrict",
    "return",
    "short",
    "signed",
    "sizeof",
    "static",
    "struct",
    "switch",
    "typedef",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
    "_Alignas",
    "_Alignof",
    "_Atomic",
    "_Bool",
    "_Complex",
    "_Generic",
    "_Imaginary",
    "_Noreturn",
    "_Static_assert",
    "_Thread_local",
}


@dataclass(frozen=True)
class ImageAsset:
    name: str
    width: int
    height: int
    palette: tuple[tuple[int, int, int, int], tuple[int, int, int, int]]
    pixels: bytes
    declared_size: int | None


@dataclass(frozen=True)
class ExtractedAsset:
    asset: ImageAsset
    source_path: Path
    output_path: Path


@dataclass(frozen=True)
class ConvertedAsset:
    asset: ImageAsset
    source_path: Path
    c_path: Path
    preview_path: Path | None


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//.*?$", "", text, flags=re.MULTILINE)


def parse_assets(text: str) -> list[ImageAsset]:
    arrays: dict[str, bytes] = {}
    array_pattern = re.compile(
        r"\buint8_t\s+(?P<name>[A-Za-z_]\w*)\s*\[\s*\]\s*=\s*"
        r"\{(?P<body>.*?)\}\s*;",
        flags=re.DOTALL,
    )
    for match in array_pattern.finditer(text):
        body = _strip_comments(match.group("body"))
        values = re.findall(r"0[xX][0-9A-Fa-f]+|\b\d+\b", body)
        arrays[match.group("name")] = bytes(int(value, 0) for value in values)

    assets = []
    descriptor_pattern = re.compile(
        r"\blv_img_dsc_t\s+(?P<name>[A-Za-z_]\w*)\s*=\s*"
        r"\{(?P<body>.*?)\}\s*;",
        flags=re.DOTALL,
    )
    for match in descriptor_pattern.finditer(text):
        body = _strip_comments(match.group("body"))
        if "LV_IMG_CF_INDEXED_1BIT" not in body:
            continue

        width_match = re.search(r"\.header\.w\s*=\s*(\d+)", body)
        height_match = re.search(r"\.header\.h\s*=\s*(\d+)", body)
        data_match = re.search(r"\.data\s*=\s*([A-Za-z_]\w*)", body)
        size_match = re.search(r"\.data_size\s*=\s*(\d+)", body)
        if not (width_match and height_match and data_match):
            continue

        data_name = data_match.group(1)
        if data_name not in arrays:
            raise ValueError(f"{match.group('name')}: data array {data_name!r} was not found")

        raw = arrays[data_name]
        if len(raw) < 8:
            raise ValueError(f"{match.group('name')}: image data is shorter than its palette")

        palette = tuple(
            (raw[index + 2], raw[index + 1], raw[index], raw[index + 3])
            for index in (0, 4)
        )
        assets.append(
            ImageAsset(
                name=match.group("name"),
                width=int(width_match.group(1)),
                height=int(height_match.group(1)),
                palette=palette,
                pixels=raw[8:],
                declared_size=int(size_match.group(1)) if size_match else None,
            )
        )

    return assets


def _png_chunk(name: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(name + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", checksum)


def write_indexed_png(asset: ImageAsset, output_path: Path) -> None:
    stride = (asset.width + 7) // 8
    expected_pixels = stride * asset.height
    if len(asset.pixels) != expected_pixels:
        raise ValueError(
            f"{asset.name}: expected {expected_pixels} pixel bytes for "
            f"{asset.width}x{asset.height}, found {len(asset.pixels)}"
        )

    scanlines = b"".join(
        b"\x00" + asset.pixels[row * stride : (row + 1) * stride]
        for row in range(asset.height)
    )
    ihdr = struct.pack(">IIBBBBB", asset.width, asset.height, 1, 3, 0, 0, 0)
    plte = b"".join(bytes(color[:3]) for color in asset.palette)
    alpha = bytes(color[3] for color in asset.palette)

    png = bytearray(PNG_SIGNATURE)
    png.extend(_png_chunk(b"IHDR", ihdr))
    png.extend(_png_chunk(b"PLTE", plte))
    if alpha != b"\xff\xff":
        png.extend(_png_chunk(b"tRNS", alpha))
    png.extend(_png_chunk(b"IDAT", zlib.compress(scanlines, level=9)))
    png.extend(_png_chunk(b"IEND", b""))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png)


def write_physical_preview_png(asset: ImageAsset, output_path: Path) -> None:
    physical_palette = tuple(
        (255 - red, 255 - green, 255 - blue, alpha)
        for red, green, blue, alpha in asset.palette
    )
    write_indexed_png(
        ImageAsset(
            name=asset.name,
            width=asset.width,
            height=asset.height,
            palette=physical_palette,
            pixels=asset.pixels,
            declared_size=asset.declared_size,
        ),
        output_path,
    )


def discover_source_files(inputs: list[Path]) -> list[Path]:
    source_files = []
    seen = set()
    for input_path in inputs:
        candidates = sorted(input_path.rglob("*.c")) if input_path.is_dir() else [input_path]
        for candidate in candidates:
            identity = candidate.resolve()
            if identity not in seen:
                seen.add(identity)
                source_files.append(candidate)
    return source_files


def extract_sources(inputs: list[Path], output_dir: Path) -> list[ExtractedAsset]:
    extracted = []
    names = set()
    for source_path in discover_source_files(inputs):
        assets = parse_assets(source_path.read_text(encoding="utf-8"))
        for asset in assets:
            if asset.name in names:
                raise ValueError(f"duplicate image name {asset.name!r}")
            names.add(asset.name)
            output_path = output_dir / f"{asset.name}.png"
            write_indexed_png(asset, output_path)
            extracted.append(ExtractedAsset(asset, source_path, output_path))
    if not extracted:
        joined_inputs = ", ".join(str(path) for path in inputs)
        raise ValueError(f"no LV_IMG_CF_INDEXED_1BIT images found in: {joined_inputs}")
    return extracted


def write_gallery(extracted: list[ExtractedAsset], output_path: Path) -> None:
    cards = []
    for item in extracted:
        asset = item.asset
        filename = html.escape(item.output_path.name)
        cards.append(
            f"""<figure>
  <div class="preview"><img src="{filename}" alt="{html.escape(asset.name)}"></div>
  <figcaption><strong>{html.escape(asset.name)}</strong><br>
  {asset.width}×{asset.height} · {html.escape(item.source_path.name)}</figcaption>
</figure>"""
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Toucan display assets</title>
<style>
  :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
  body {{ margin: 2rem; background: #171717; color: #f5f5f5; }}
  h1 {{ font-size: 1.5rem; }}
  main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; }}
  figure {{ margin: 0; padding: 1rem; border: 1px solid #444; border-radius: .5rem; background: #222; }}
  .preview {{ min-height: 180px; display: grid; place-items: center; background: #080808;
              background-image: linear-gradient(45deg, #202020 25%, transparent 25%),
                                linear-gradient(-45deg, #202020 25%, transparent 25%),
                                linear-gradient(45deg, transparent 75%, #202020 75%),
                                linear-gradient(-45deg, transparent 75%, #202020 75%);
              background-size: 16px 16px; background-position: 0 0, 0 8px, 8px -8px, -8px 0; }}
  img {{ max-width: 100%; image-rendering: pixelated; transform: scale(2); }}
  figcaption {{ margin-top: 1rem; color: #bbb; line-height: 1.4; }}
  strong {{ color: #fff; }}
</style>
</head>
<body>
<h1>Toucan display assets</h1>
<p>{len(extracted)} extracted image{'s' if len(extracted) != 1 else ''}</p>
<main>
{''.join(cards)}
</main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")


def _require_pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise RuntimeError(
            "static conversion requires Pillow; install it with "
            "'py -3 -m pip install -r tools/toucan_art/requirements.txt'"
        ) from error
    return Image, ImageOps


def _parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)[xX](\d+)\s*", value)
    if not match:
        raise argparse.ArgumentTypeError("size must use WIDTHxHEIGHT, for example 144x168")
    width, height = (int(part) for part in match.groups())
    if width < 1 or height < 1 or width > 2047 or height > 2047:
        raise argparse.ArgumentTypeError("LVGL v8 width and height must be between 1 and 2047")
    return width, height


def _c_identifier(stem: str) -> str:
    identifier = re.sub(r"\W", "_", stem, flags=re.ASCII)
    if not identifier:
        identifier = "image"
    if identifier[0].isdigit():
        identifier = f"_{identifier}"
    if identifier in C_KEYWORDS:
        identifier = f"image_{identifier}"
    return identifier


def _validate_c_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_]\w*", value, flags=re.ASCII):
        raise argparse.ArgumentTypeError(
            "image name must be a C identifier containing only ASCII letters, digits, and underscores"
        )
    if value in C_KEYWORDS:
        raise argparse.ArgumentTypeError(f"{value!r} is a reserved C keyword")
    return value


def discover_image_files(inputs: list[Path], excluded_dir: Path | None = None) -> list[Path]:
    image_files = []
    seen = set()
    excluded_identity = excluded_dir.resolve() if excluded_dir else None
    for input_path in inputs:
        if not input_path.exists():
            raise ValueError(f"input does not exist: {input_path}")
        input_is_directory = input_path.is_dir()
        candidates = sorted(input_path.rglob("*")) if input_is_directory else [input_path]
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() not in STATIC_IMAGE_EXTENSIONS:
                continue
            identity = candidate.resolve()
            if input_is_directory and excluded_identity and (
                identity == excluded_identity or excluded_identity in identity.parents
            ):
                continue
            if identity not in seen:
                seen.add(identity)
                image_files.append(candidate)
    if not image_files:
        joined_inputs = ", ".join(str(path) for path in inputs)
        raise ValueError(f"no supported static images found in: {joined_inputs}")
    return image_files


def _prepare_monochrome_image(
    source_path: Path,
    size: tuple[int, int],
    fit: str,
    background: str,
    threshold: int,
    dither: str,
    invert: bool,
):
    Image, ImageOps = _require_pillow()
    background_value = 0 if background == "black" else 255
    background_rgb = (background_value,) * 3

    with Image.open(source_path) as opened:
        if getattr(opened, "n_frames", 1) > 1:
            raise ValueError(
                f"{source_path}: animated images are reserved for the future GIF converter"
            )
        oriented = ImageOps.exif_transpose(opened)
        rgba = oriented.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, background_rgb)
        flattened.paste(rgba, mask=rgba.getchannel("A"))

    if fit == "contain":
        resized = ImageOps.contain(flattened, size, method=Image.Resampling.LANCZOS)
        fitted = Image.new("RGB", size, background_rgb)
        offset = ((size[0] - resized.width) // 2, (size[1] - resized.height) // 2)
        fitted.paste(resized, offset)
    elif fit == "cover":
        fitted = ImageOps.fit(flattened, size, method=Image.Resampling.LANCZOS)
    else:
        fitted = flattened.resize(size, resample=Image.Resampling.LANCZOS)

    grayscale = fitted.convert("L")
    if invert:
        grayscale = ImageOps.invert(grayscale)
    if dither == "floyd-steinberg":
        return grayscale.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    return grayscale.point(lambda pixel: 255 if pixel >= threshold else 0, mode="1")


def _pack_monochrome_pixels(image) -> bytes:
    width, height = image.size
    pixels = image.load()
    stride = (width + 7) // 8
    packed = bytearray(stride * height)
    for y in range(height):
        for x in range(width):
            # The panel reverses LVGL's logical monochrome polarity. Pack source
            # black as logical white so converted artwork keeps its visible
            # black/white appearance on the physical display and in previews.
            if not pixels[x, y]:
                packed[y * stride + x // 8] |= 1 << (7 - (x % 8))
    return bytes(packed)


def _format_c_asset(asset: ImageAsset) -> str:
    macro_name = asset.name.upper()
    raw = bytearray()
    for red, green, blue, alpha in asset.palette:
        raw.extend((blue, green, red, alpha))
    raw.extend(asset.pixels)

    rows = []
    for offset in range(0, len(raw), 12):
        values = ", ".join(f"0x{value:02x}" for value in raw[offset : offset + 12])
        rows.append(f"    {values},")
    data = "\n".join(rows)
    return f"""#include <lvgl.h>

#ifndef LV_ATTRIBUTE_IMG_{macro_name}
#define LV_ATTRIBUTE_IMG_{macro_name}
#endif

const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST LV_ATTRIBUTE_IMG_{macro_name} uint8_t {asset.name}_map[] = {{
{data}
}};

const lv_img_dsc_t {asset.name} = {{
    .header.cf = LV_IMG_CF_INDEXED_1BIT,
    .header.always_zero = 0,
    .header.reserved = 0,
    .header.w = {asset.width},
    .header.h = {asset.height},
    .data_size = {len(raw)},
    .data = {asset.name}_map,
}};
"""


def convert_images(
    inputs: list[Path],
    output_dir: Path,
    size: tuple[int, int],
    fit: str,
    background: str,
    threshold: int,
    dither: str,
    invert: bool,
    name: str | None,
    preview: bool,
    force: bool,
) -> list[ConvertedAsset]:
    sources = discover_image_files(inputs, excluded_dir=output_dir)
    if name and len(sources) != 1:
        raise ValueError("--name can only be used when exactly one input image is found")

    jobs = []
    names = set()
    for source_path in sources:
        image_name = name or _c_identifier(source_path.stem)
        if image_name in names:
            raise ValueError(f"duplicate generated image name {image_name!r}")
        names.add(image_name)

        c_path = output_dir / f"{image_name}.c"
        preview_path = output_dir / f"{image_name}.preview.png" if preview else None
        targets = [c_path] + ([preview_path] if preview_path else [])
        existing = [path for path in targets if path.exists()]
        if existing and not force:
            raise ValueError(
                f"refusing to overwrite {existing[0]}; pass --force to replace generated files"
            )
        jobs.append((source_path, image_name, c_path, preview_path))

    converted = []
    for source_path, image_name, c_path, preview_path in jobs:
        image = _prepare_monochrome_image(
            source_path, size, fit, background, threshold, dither, invert
        )
        asset = ImageAsset(
            name=image_name,
            width=size[0],
            height=size[1],
            palette=((0, 0, 0, 255), (255, 255, 255, 255)),
            pixels=_pack_monochrome_pixels(image),
            declared_size=8 + ((size[0] + 7) // 8) * size[1],
        )
        c_text = _format_c_asset(asset)

        # Parse our emitted C before writing it. This keeps conversion and extraction
        # compatible. The preview uses those packed bytes with the physical panel's
        # reversed monochrome polarity.
        parsed = parse_assets(c_text)
        if len(parsed) != 1:
            raise ValueError(f"{image_name}: generated C did not round-trip through the extractor")

        output_dir.mkdir(parents=True, exist_ok=True)
        c_path.write_text(c_text, encoding="utf-8")
        if preview_path:
            write_physical_preview_png(parsed[0], preview_path)
        converted.append(ConvertedAsset(parsed[0], source_path, c_path, preview_path))
    return converted


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract", help="extract one-bit LVGL images to PNG")
    extract.add_argument(
        "source",
        type=Path,
        nargs="+",
        help="C source file(s), or directories to scan recursively for .c files",
    )
    extract.add_argument("--output", type=Path, required=True, help="output directory")
    extract.add_argument(
        "--gallery", action="store_true", help="also create a browser gallery at index.html"
    )
    convert = subparsers.add_parser(
        "convert", help="convert ordinary static images to one-bit LVGL v8 C arrays"
    )
    convert.add_argument(
        "source",
        type=Path,
        nargs="+",
        help="image file(s), or directories to scan recursively for supported images",
    )
    convert.add_argument("--output", type=Path, required=True, help="output directory")
    convert.add_argument("--size", type=_parse_size, required=True, help="target WIDTHxHEIGHT")
    convert.add_argument(
        "--fit", choices=("contain", "cover", "stretch"), default="contain"
    )
    convert.add_argument("--background", choices=("black", "white"), default="white")
    convert.add_argument("--threshold", type=int, default=128, metavar="0-255")
    convert.add_argument(
        "--dither", choices=("none", "floyd-steinberg"), default="none"
    )
    convert.add_argument("--invert", action="store_true", help="invert black and white")
    convert.add_argument(
        "--name", type=_validate_c_identifier, help="C image name (single image only)"
    )
    convert.add_argument(
        "--preview", action="store_true", help="write a PNG decoded from the generated C data"
    )
    convert.add_argument("--force", action="store_true", help="overwrite generated files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "extract":
            extracted = extract_sources(args.source, args.output)
            if args.gallery:
                write_gallery(extracted, args.output / "index.html")
        else:
            if not 0 <= args.threshold <= 255:
                raise ValueError("--threshold must be between 0 and 255")
            converted = convert_images(
                args.source,
                args.output,
                args.size,
                args.fit,
                args.background,
                args.threshold,
                args.dither,
                args.invert,
                args.name,
                args.preview,
                args.force,
            )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.command == "extract":
        for item in extracted:
            print(item.output_path)
        if args.gallery:
            print(args.output / "index.html")
    else:
        for item in converted:
            data_size = item.asset.declared_size
            print(
                f"{item.c_path} "
                f"({item.asset.width}x{item.asset.height}, {data_size} data bytes)"
            )
            if item.preview_path:
                print(item.preview_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
