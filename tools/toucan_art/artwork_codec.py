
from __future__ import annotations

import argparse
import binascii
import html
import math
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
    frame_count: int = 1
    duration_ms: int | None = None
    total_data_size: int | None = None


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


def write_physical_preview_gif(
    assets: list[ImageAsset], output_path: Path, duration_ms: int
) -> None:
    Image, _ = _require_pillow()
    frames = []
    for asset in assets:
        stride = (asset.width + 7) // 8
        colors = [
            (255 - red, 255 - green, 255 - blue)
            for red, green, blue, _alpha in asset.palette
        ]
        pixels = []
        for y in range(asset.height):
            row = asset.pixels[y * stride : (y + 1) * stride]
            pixels.extend(colors[(row[x // 8] >> (7 - (x % 8))) & 1] for x in range(asset.width))
        frame = Image.new("RGB", (asset.width, asset.height))
        frame.putdata(pixels)
        frames.append(frame)

    frame_duration = max(1, round(duration_ms / len(frames)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=0,
        disposal=2,
        optimize=False,
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
            raise ValueError(f"{source_path}: expected a static image")
        oriented = ImageOps.exif_transpose(opened)
        rgba = oriented.convert("RGBA")
        return _prepare_monochrome_frame(
            rgba, size, fit, background_rgb, threshold, dither, invert, Image, ImageOps
        )


def _prepare_monochrome_frame(
    rgba,
    size: tuple[int, int],
    fit: str,
    background_rgb: tuple[int, int, int],
    threshold: int,
    dither: str,
    invert: bool,
    Image,
    ImageOps,
):
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


def _prepare_animation_frames(
    source_path: Path,
    size: tuple[int, int],
    fit: str,
    background: str,
    threshold: int,
    dither: str,
    invert: bool,
    fps: int,
    max_frames: int,
    start_time: int,
    duration: int | None,
):
    Image, ImageOps = _require_pillow()
    background_value = 0 if background == "black" else 255
    background_rgb = (background_value,) * 3

    composited = []
    durations = []
    with Image.open(source_path) as opened:
        for index in range(opened.n_frames):
            opened.seek(index)
            composited.append(opened.convert("RGBA").copy())
            durations.append(max(20, int(opened.info.get("duration", 100) or 100)))

    source_duration = sum(durations)
    if start_time >= source_duration:
        raise ValueError(
            f"--start-time must be less than the GIF duration ({source_duration} ms)"
        )
    selected_duration = duration if duration is not None else source_duration - start_time
    if start_time + selected_duration > source_duration:
        raise ValueError(
            f"selected time range ends after the GIF duration ({source_duration} ms)"
        )

    requested_count = max(1, math.ceil(selected_duration * fps / 1000))
    output_count = min(requested_count, max_frames)
    was_capped = requested_count > max_frames
    if was_capped:
        sample_times = [
            start_time + index * selected_duration / output_count
            for index in range(output_count)
        ]
        output_duration = selected_duration
    else:
        frame_interval = 1000 / fps
        sample_times = [start_time + index * frame_interval for index in range(output_count)]
        output_duration = round(output_count * frame_interval)

    selected = []
    source_index = 0
    source_end = durations[0]
    for sample_time in sample_times:
        while source_index + 1 < len(composited) and sample_time >= source_end:
            source_index += 1
            source_end += durations[source_index]
        selected.append(
            _prepare_monochrome_frame(
                composited[source_index],
                size,
                fit,
                background_rgb,
                threshold,
                dither,
                invert,
                Image,
                ImageOps,
            )
        )
    return selected, output_duration, was_capped


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


def _format_animation_c(assets: list[ImageAsset], name: str, duration_ms: int) -> str:
    declarations = []
    frame_names = []
    for asset in assets:
        frame_text = _format_c_asset(asset)
        declarations.append(frame_text.split("\n", 1)[1].rstrip())
        frame_names.append(f"    &{asset.name},")

    return f"""#include <lvgl.h>

{chr(10).join(declarations)}

const lv_img_dsc_t *const {name}_frames[] = {{
{chr(10).join(frame_names)}
}};
const uint8_t {name}_frame_count = {len(assets)};
const uint32_t {name}_duration_ms = {duration_ms};
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
    fps: int,
    max_frames: int,
    start_time: int,
    duration: int | None,
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
        is_animated = False
        if source_path.suffix.lower() == ".gif":
            Image, _ = _require_pillow()
            with Image.open(source_path) as opened:
                is_animated = getattr(opened, "n_frames", 1) > 1
        preview_suffix = ".preview.gif" if is_animated else ".preview.png"
        preview_path = output_dir / f"{image_name}{preview_suffix}" if preview else None
        targets = [c_path] + ([preview_path] if preview_path else [])
        existing = [path for path in targets if path.exists()]
        if existing and not force:
            raise ValueError(
                f"refusing to overwrite {existing[0]}; pass --force to replace generated files"
            )
        jobs.append((source_path, image_name, c_path, preview_path, is_animated))

    converted = []
    for source_path, image_name, c_path, preview_path, is_animated in jobs:
        duration_ms = None
        was_capped = False
        if is_animated:
            if fps > 10:
                print(
                    f"warning: {source_path} requests {fps} FPS, above the "
                    "10 FPS keyboard validation range",
                    file=sys.stderr,
                )
            images, duration_ms, was_capped = _prepare_animation_frames(
                source_path,
                size,
                fit,
                background,
                threshold,
                dither,
                invert,
                fps,
                max_frames,
                start_time,
                duration,
            )
        else:
            images = [
                _prepare_monochrome_image(
                    source_path, size, fit, background, threshold, dither, invert
                )
            ]

        assets = [
            ImageAsset(
                name=(f"{image_name}_frame_{index:03d}" if is_animated else image_name),
                width=size[0],
                height=size[1],
                palette=((0, 0, 0, 255), (255, 255, 255, 255)),
                pixels=_pack_monochrome_pixels(image),
                declared_size=8 + ((size[0] + 7) // 8) * size[1],
            )
            for index, image in enumerate(images)
        ]
        c_text = (
            _format_animation_c(assets, image_name, duration_ms)
            if is_animated
            else _format_c_asset(assets[0])
        )

        # Parse our emitted C before writing it. This keeps conversion and extraction
        # compatible. The preview uses those packed bytes with the physical panel's
        # reversed monochrome polarity.
        parsed = parse_assets(c_text)
        if len(parsed) != len(assets):
            raise ValueError(f"{image_name}: generated C did not round-trip through the extractor")

        output_dir.mkdir(parents=True, exist_ok=True)
        c_path.write_text(c_text, encoding="utf-8")
        if preview_path:
            if is_animated:
                write_physical_preview_gif(parsed, preview_path, duration_ms)
            else:
                write_physical_preview_png(parsed[0], preview_path)
        total_data_size = sum(asset.declared_size or 0 for asset in parsed)
        if was_capped:
            effective_fps = len(parsed) * 1000 / duration_ms
            print(
                f"warning: {source_path} was limited to {max_frames} frames; "
                f"the full cycle duration was preserved at an effective {effective_fps:.2f} FPS",
                file=sys.stderr,
            )
        converted.append(
            ConvertedAsset(
                parsed[0],
                source_path,
                c_path,
                preview_path,
                len(parsed),
                duration_ms,
                total_data_size,
            )
        )
    return converted

