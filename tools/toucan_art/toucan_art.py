#!/usr/bin/env python3
"""Extract LVGL v8 indexed one-bit C images as editable PNG files."""

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        extracted = extract_sources(args.source, args.output)
        if args.gallery:
            write_gallery(extracted, args.output / "index.html")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    for item in extracted:
        print(item.output_path)
    if args.gallery:
        print(args.output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
