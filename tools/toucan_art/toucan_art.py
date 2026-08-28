#!/usr/bin/env python3
"""Convert, extract, and manage Toucan LVGL display artwork."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from artwork_codec import (
    _parse_size,
    _validate_c_identifier,
    convert_images,
    extract_sources,
    write_gallery,
)
from artwork_registry import (
    artwork_budget_status,
    install_artwork,
    list_artworks,
    remove_artwork,
    sync_artworks,
)

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
    convert.add_argument("--fps", type=int, default=5, help="animated GIF sample rate (1-30, default: 5)")
    convert.add_argument(
        "--max-frames", type=int, default=16, help="maximum emitted animation frames (1-127, default: 16)"
    )
    convert.add_argument(
        "--start-time", type=int, default=0, metavar="MS", help="start animated GIF conversion at this time"
    )
    convert.add_argument(
        "--duration", type=int, metavar="MS", help="convert only this many milliseconds of an animated GIF"
    )
    convert.add_argument(
        "--name", type=_validate_c_identifier, help="C image name (single image only)"
    )
    convert.add_argument(
        "--preview", action="store_true", help="write a PNG decoded from the generated C data"
    )
    convert.add_argument("--force", action="store_true", help="overwrite generated files")
    install = subparsers.add_parser(
        "install", help="convert and add artwork to the firmware registry"
    )
    install.add_argument("source", type=Path, help="static image or animated GIF")
    install.add_argument("--name", type=_validate_c_identifier, required=True)
    install.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    install.add_argument("--size", type=_parse_size, default=(142, 142))
    install.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain")
    install.add_argument("--background", choices=("black", "white"), default="white")
    install.add_argument("--threshold", type=int, default=128)
    install.add_argument("--dither", choices=("none", "floyd-steinberg"), default="none")
    install.add_argument("--invert", action="store_true")
    install.add_argument("--fps", type=int, default=5)
    install.add_argument("--max-frames", type=int, default=16)
    install.add_argument(
        "--x", type=int, help="left position; defaults to horizontal safe-area centering"
    )
    install.add_argument(
        "--y", type=int, help="top position; defaults to two pixels above the footer"
    )
    install.add_argument(
        "--dry-run",
        action="store_true",
        help="preview and report the installation without changing firmware files",
    )
    install.add_argument("--force", action="store_true")
    list_command = subparsers.add_parser("list", help="list installed artwork")
    list_command.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    budget_command = subparsers.add_parser(
        "budget", help="report installed artwork usage and enforce its configured limit"
    )
    budget_command.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    budget_command.add_argument(
        "--strict", action="store_true", help="exit with an error when the limit is exceeded"
    )
    remove = subparsers.add_parser("remove", help="remove artwork from the registry")
    remove.add_argument("name", type=_validate_c_identifier)
    remove.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    sync = subparsers.add_parser("sync", help="regenerate integration files from the manifest")
    sync.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "extract":
            extracted = extract_sources(args.source, args.output)
            if args.gallery:
                write_gallery(extracted, args.output / "index.html")
        elif args.command == "convert":
            if not 0 <= args.threshold <= 255:
                raise ValueError("--threshold must be between 0 and 255")
            if not 1 <= args.fps <= 30:
                raise ValueError("--fps must be between 1 and 30")
            if not 1 <= args.max_frames <= 127:
                raise ValueError("--max-frames must be between 1 and 127")
            if args.start_time < 0:
                raise ValueError("--start-time must not be negative")
            if args.duration is not None and args.duration < 1:
                raise ValueError("--duration must be at least 1 ms")
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
                args.fps,
                args.max_frames,
                args.start_time,
                args.duration,
            )
        elif args.command == "install":
            if not 0 <= args.threshold <= 255:
                raise ValueError("--threshold must be between 0 and 255")
            if not 1 <= args.fps <= 30:
                raise ValueError("--fps must be between 1 and 30")
            if not 1 <= args.max_frames <= 127:
                raise ValueError("--max-frames must be between 1 and 127")
            installed = install_artwork(args)
        elif args.command == "list":
            artwork_lines = list_artworks(args.repo_root)
        elif args.command == "budget":
            budget_status = artwork_budget_status(args.repo_root)
            if args.strict and budget_status["exceeded"]:
                raise ValueError(
                    "artwork budget exceeded: "
                    f"{budget_status['artwork_data_bytes']} > "
                    f"{budget_status['artwork_data_limit_bytes']} bytes"
                )
        elif args.command == "remove":
            removed = remove_artwork(args.repo_root, args.name)
        else:
            synced_count = sync_artworks(args.repo_root)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.command == "extract":
        for item in extracted:
            print(item.output_path)
        if args.gallery:
            print(args.output / "index.html")
    elif args.command == "convert":
        for item in converted:
            details = f"{item.asset.width}x{item.asset.height}, {item.total_data_size} data bytes"
            if item.frame_count > 1:
                details += f", {item.frame_count} frames, {item.duration_ms} ms cycle"
            print(f"{item.c_path} ({details})")
            if item.preview_path:
                print(item.preview_path)
    elif args.command == "install":
        if installed["dry_run"]:
            print(f"DRY RUN: would install {installed['name']} at index {installed['index']}")
            print(f"Placement: ({installed['x']}, {installed['y']})")
            print(f"Frames: {installed['frame_count']}")
            if installed["animated"]:
                cycle_ms = installed["frame_count"] * installed["interval_ms"]
                print(
                    f"Playback: {installed['fps']} FPS "
                    f"({installed['interval_ms']} ms/frame, {cycle_ms} ms cycle)"
                )
            else:
                print("Playback: static")
            print(f"Image data: {installed['data_bytes']:,} bytes")
            print(f"Current artwork data: {installed['current_data_bytes']:,} bytes")
            print(f"Projected artwork data: {installed['projected_data_bytes']:,} bytes")
            if installed["budget"] is not None:
                capacity = installed["budget"]["left_flash_capacity_bytes"]
                percent = installed["estimated_left_flash_bytes"] * 100 / capacity
                print(
                    f"Estimated left flash: {installed['estimated_left_flash_bytes']:,} / "
                    f"{capacity:,} bytes ({percent:.2f}%)"
                )
            print(f"Preview: {installed['preview_path']}")
            print("Files a real install would change:")
            for path in installed["would_change"]:
                print(f"  {path.relative_to(args.repo_root.resolve())}")
        else:
            print(
                f"installed {installed['name']} at index {installed['index']} "
                f"({installed['frame_count']} frame(s), {installed['data_bytes']} data bytes)"
            )
    elif args.command == "list":
        if artwork_lines:
            print("\n".join(artwork_lines))
        else:
            print("no artwork installed")
    elif args.command == "budget":
        flash_percent = (
            budget_status["estimated_left_flash_bytes"]
            * 100
            / budget_status["left_flash_capacity_bytes"]
        )
        print(
            f"Artwork data: {budget_status['artwork_data_bytes']:,} / "
            f"{budget_status['artwork_data_limit_bytes']:,} bytes"
        )
        print(
            f"Estimated left flash: {budget_status['estimated_left_flash_bytes']:,} / "
            f"{budget_status['left_flash_capacity_bytes']:,} bytes ({flash_percent:.2f}%)"
        )
        print("Budget status: " + ("EXCEEDED" if budget_status["exceeded"] else "within limit"))
    elif args.command == "remove":
        print(f"removed {removed['name']} ({removed['data_bytes']:,} data bytes)")
    else:
        suffix = "" if synced_count == 1 else "s"
        print(f"synced {synced_count} artwork{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
