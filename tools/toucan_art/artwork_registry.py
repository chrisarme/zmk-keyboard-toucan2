from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from artwork_codec import convert_images


ARTWORK_AREA_SIZE = 144
DEFAULT_FOOTER_GAP = 2

def _manifest_path(repo_root: Path) -> Path:
    return repo_root / "config" / "toucan_artworks.json"


def _budget_path(repo_root: Path) -> Path:
    return repo_root / "config" / "toucan_artwork_budget.json"


def _load_artwork_budget(repo_root: Path) -> dict | None:
    path = _budget_path(repo_root)
    if not path.exists():
        return None
    budget = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "artwork_data_limit_bytes",
        "left_flash_estimate_base_bytes",
        "left_flash_capacity_bytes",
    }
    if not isinstance(budget, dict) or not required.issubset(budget):
        raise ValueError(f"invalid artwork budget: {path}")
    if budget["version"] != 1:
        raise ValueError(f"unsupported artwork budget version: {path}")
    for field in required - {"version"}:
        if not isinstance(budget[field], int) or budget[field] < 1:
            raise ValueError(f"{field} must be a positive integer")
    if budget["left_flash_estimate_base_bytes"] >= budget["left_flash_capacity_bytes"]:
        raise ValueError("left flash estimate base must be below capacity")
    return budget


def _load_artwork_manifest(repo_root: Path) -> dict:
    path = _manifest_path(repo_root)
    if not path.exists():
        return {"version": 1, "artworks": []}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or not isinstance(manifest.get("artworks"), list):
        raise ValueError(f"invalid artwork manifest: {path}")
    names = set()
    constant_names = set()
    required = {
        "name", "file", "symbol", "animated", "frame_count", "fps",
        "interval_ms", "x", "y", "data_bytes",
    }
    for artwork in manifest["artworks"]:
        if not isinstance(artwork, dict) or not required.issubset(artwork):
            raise ValueError(f"invalid artwork entry in manifest: {path}")
        name = artwork["name"]
        symbol = artwork["symbol"]
        filename = artwork["file"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_]\w*", name, re.ASCII):
            raise ValueError("artwork name must be a C identifier")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z_]\w*", symbol, re.ASCII):
            raise ValueError(f"{name}: symbol must be a C identifier")
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".c"):
            raise ValueError(f"{name}: file must be a plain C filename")
        if name in names or name.upper() in constant_names:
            raise ValueError(f"duplicate artwork name {name!r}")
        names.add(name)
        constant_names.add(name.upper())
        if not isinstance(artwork["frame_count"], int) or not 1 <= artwork["frame_count"] <= 127:
            raise ValueError(f"{name}: frame_count must be between 1 and 127")
        if not isinstance(artwork["data_bytes"], int) or artwork["data_bytes"] < 1:
            raise ValueError(f"{name}: data_bytes must be positive")
    return manifest


def _write_artwork_integration(repo_root: Path, manifest: dict) -> None:
    artworks = manifest["artworks"]
    if not artworks:
        raise ValueError("the artwork registry must contain at least one entry")
    if len(artworks) > 253:
        raise ValueError("the artwork registry supports at most 253 entries")

    registry_declarations = []
    registry_entries = []
    header_constants = []
    cmake_assets = []
    for index, artwork in enumerate(artworks):
        name = artwork["name"]
        symbol = artwork["symbol"]
        cmake_assets.append(f"  {artwork['file']}")
        header_constants.extend(
            [
                f"#define TOUCAN_ARTWORK_{index} {index}",
                f"#define TOUCAN_ARTWORK_{name.upper()} {index}",
            ]
        )
        if artwork["animated"]:
            registry_declarations.extend(
                [
                    f"extern const lv_img_dsc_t *const {symbol}_frames[];",
                    f"extern const uint8_t {symbol}_frame_count;",
                ]
            )
            frames = f"{symbol}_frames"
            frame_count = f"&{symbol}_frame_count"
        else:
            registry_declarations.extend(
                [
                    f"extern const lv_img_dsc_t {symbol};",
                    f"static const lv_img_dsc_t *const {symbol}_frames[] = {{&{symbol}}};",
                    f"static const uint8_t {symbol}_frame_count = 1;",
                ]
            )
            frames = f"{symbol}_frames"
            frame_count = f"&{symbol}_frame_count"
        registry_entries.append(
            "    {\n"
            f"        .frames = {frames},\n"
            f"        .frame_count = {frame_count},\n"
            f"        .interval_ms = {artwork['interval_ms']},\n"
            f"        .x = {artwork['x']},\n"
            f"        .y = {artwork['y']},\n"
            "    },"
        )

    registry_path = (
        repo_root
        / "boards"
        / "shields"
        / "nice_view_gem"
        / "widgets"
        / "artwork_registry.c"
    )
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        """/* Generated by tools/toucan_art/toucan_art.py. Do not edit manually. */
#include "artwork_registry.h"

#include <stddef.h>

#include <dt-bindings/zmk/toucan_artwork.h>

"""
        + "\n".join(registry_declarations)
        + "\n\nstatic const struct toucan_artwork artwork_registry[] = {\n"
        + "\n".join(registry_entries)
        + "\n};\n\n"
        + "_Static_assert(sizeof(artwork_registry) / sizeof(artwork_registry[0]) ==\n"
        + "                   TOUCAN_ARTWORK_COUNT,\n"
        + '               "artwork constants must match the registry");\n\n'
        + "uint8_t toucan_artwork_count(void) { return TOUCAN_ARTWORK_COUNT; }\n\n"
        + "const struct toucan_artwork *toucan_artwork_get(uint8_t index) {\n"
        + "  return index < toucan_artwork_count() ? &artwork_registry[index] : NULL;\n"
        + "}\n",
        encoding="utf-8",
    )

    header_path = repo_root / "include" / "dt-bindings" / "zmk" / "toucan_artwork.h"
    header_path.parent.mkdir(parents=True, exist_ok=True)
    header_path.write_text(
        "/* Generated by tools/toucan_art/toucan_art.py. Do not edit manually. */\n"
        "#pragma once\n\n"
        + "\n".join(header_constants)
        + f"\n#define TOUCAN_ARTWORK_COUNT {len(artworks)}\n"
        + f"#define TOUCAN_ARTWORK_NEXT {len(artworks)}\n"
        + f"#define TOUCAN_ARTWORK_PREV {len(artworks) + 1}\n",
        encoding="utf-8",
    )

    cmake_path = repo_root / "config" / "toucan_artworks.cmake"
    cmake_path.parent.mkdir(parents=True, exist_ok=True)
    cmake_path.write_text(
        "# Generated by tools/toucan_art/toucan_art.py. Do not edit manually.\n"
        "set(TOUCAN_ARTWORK_ASSETS\n"
        + "\n".join(cmake_assets)
        + "\n)\n",
        encoding="utf-8",
    )


def install_artwork(args) -> dict:
    repo_root = args.repo_root.resolve()
    width, height = args.size
    x = (ARTWORK_AREA_SIZE - width) // 2 if args.x is None else args.x
    y = (
        max(0, ARTWORK_AREA_SIZE - height - DEFAULT_FOOTER_GAP)
        if args.y is None
        else args.y
    )
    if (
        x < 0
        or y < 0
        or x + width > ARTWORK_AREA_SIZE
        or y + height > ARTWORK_AREA_SIZE
    ):
        raise ValueError(
            f"{width}x{height} at ({x}, {y}) must fit the 144x144 artwork area"
        )
    manifest = _load_artwork_manifest(repo_root)
    existing_index = next(
        (index for index, item in enumerate(manifest["artworks"])
         if item["name"] == args.name),
        None,
    )
    if existing_index is not None and not args.force:
        raise ValueError(f"artwork {args.name!r} is already installed")

    generated_dir = repo_root / "tools" / "toucan_art" / "generated"
    conversion_dir = generated_dir / "dry-run" if args.dry_run else generated_dir
    converted = convert_images(
        [args.source], conversion_dir, args.size, args.fit, args.background,
        args.threshold, args.dither, args.invert, args.name, True,
        args.force or args.dry_run,
        args.fps, args.max_frames, 0, None,
    )[0]

    animated = converted.duration_ms is not None
    entry = {
        "name": args.name,
        "file": converted.c_path.name,
        "symbol": args.name,
        "animated": animated,
        "frame_count": converted.frame_count,
        "fps": args.fps if animated else 0,
        "interval_ms": round(1000 / args.fps) if animated else 0,
        "x": x,
        "y": y,
        "data_bytes": converted.total_data_size,
    }
    current_data_bytes = sum(item["data_bytes"] for item in manifest["artworks"])
    replaced_data_bytes = (
        manifest["artworks"][existing_index]["data_bytes"]
        if existing_index is not None
        else 0
    )
    projected_data_bytes = current_data_bytes - replaced_data_bytes + entry["data_bytes"]
    budget = _load_artwork_budget(repo_root)
    estimated_left_flash_bytes = None
    if budget is not None:
        estimated_left_flash_bytes = (
            budget["left_flash_estimate_base_bytes"] + projected_data_bytes
        )
        if projected_data_bytes > budget["artwork_data_limit_bytes"]:
            print(
                f"warning: projected artwork data {projected_data_bytes} exceeds budget "
                f"{budget['artwork_data_limit_bytes']}",
                file=sys.stderr,
            )
    installed_index = (
        len(manifest["artworks"]) if existing_index is None else existing_index
    )
    if args.dry_run:
        firmware_asset = (
            repo_root
            / "boards"
            / "shields"
            / "nice_view_gem"
            / "assets"
            / converted.c_path.name
        )
        generated_preview = generated_dir / converted.preview_path.name
        result = dict(entry)
        result.update(
            {
                "index": installed_index,
                "dry_run": True,
                "preview_path": converted.preview_path,
                "current_data_bytes": current_data_bytes,
                "projected_data_bytes": projected_data_bytes,
                "budget": budget,
                "estimated_left_flash_bytes": estimated_left_flash_bytes,
                "would_change": [
                    generated_dir / converted.c_path.name,
                    generated_preview,
                    firmware_asset,
                    _manifest_path(repo_root),
                    repo_root / "config" / "toucan_artworks.cmake",
                    repo_root / "include" / "dt-bindings" / "zmk" / "toucan_artwork.h",
                    repo_root
                    / "boards"
                    / "shields"
                    / "nice_view_gem"
                    / "widgets"
                    / "artwork_registry.c",
                ],
            }
        )
        return result

    asset_dir = repo_root / "boards" / "shields" / "nice_view_gem" / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_path = asset_dir / converted.c_path.name
    if asset_path.exists() and not args.force:
        raise ValueError(f"refusing to overwrite installed asset {asset_path}")
    shutil.copyfile(converted.c_path, asset_path)

    if existing_index is None:
        manifest["artworks"].append(entry)
    else:
        manifest["artworks"][existing_index] = entry
    _write_artwork_integration(repo_root, manifest)
    manifest_path = _manifest_path(repo_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = dict(entry)
    result["index"] = installed_index
    result["dry_run"] = False
    return result


def list_artworks(repo_root: Path) -> list[str]:
    manifest = _load_artwork_manifest(repo_root.resolve())
    lines = []
    for index, artwork in enumerate(manifest["artworks"]):
        timing = (
            f"{artwork['frame_count']} frames, {artwork['fps']} FPS"
            if artwork["animated"]
            else "1 frame, static"
        )
        lines.append(
            f"{index}  {artwork['name']}  {timing}, "
            f"{artwork['data_bytes']:,} bytes"
        )
    if manifest["artworks"]:
        total = sum(item["data_bytes"] for item in manifest["artworks"])
        lines.append(f"Total image data: {total:,} bytes")
    return lines


def artwork_budget_status(repo_root: Path) -> dict:
    repo_root = repo_root.resolve()
    manifest = _load_artwork_manifest(repo_root)
    budget = _load_artwork_budget(repo_root)
    if budget is None:
        raise ValueError(f"artwork budget configuration is missing: {_budget_path(repo_root)}")
    artwork_data_bytes = sum(item["data_bytes"] for item in manifest["artworks"])
    return {
        "artwork_data_bytes": artwork_data_bytes,
        "artwork_data_limit_bytes": budget["artwork_data_limit_bytes"],
        "estimated_left_flash_bytes": (
            budget["left_flash_estimate_base_bytes"] + artwork_data_bytes
        ),
        "left_flash_capacity_bytes": budget["left_flash_capacity_bytes"],
        "exceeded": artwork_data_bytes > budget["artwork_data_limit_bytes"],
    }


def remove_artwork(repo_root: Path, name: str) -> dict:
    repo_root = repo_root.resolve()
    manifest = _load_artwork_manifest(repo_root)
    removed = next(
        (item for item in manifest["artworks"] if item["name"] == name), None
    )
    if removed is None:
        raise ValueError(f"artwork {name!r} is not installed")
    remaining = [item for item in manifest["artworks"] if item["name"] != name]
    if not remaining:
        raise ValueError("cannot remove the final artwork registry entry")

    updated = {"version": 1, "artworks": remaining}
    _write_artwork_integration(repo_root, updated)
    _manifest_path(repo_root).write_text(
        json.dumps(updated, indent=2) + "\n", encoding="utf-8"
    )
    asset_path = (
        repo_root
        / "boards"
        / "shields"
        / "nice_view_gem"
        / "assets"
        / removed["file"]
    )
    if asset_path.is_file():
        asset_path.unlink()
    return removed


def sync_artworks(repo_root: Path) -> int:
    repo_root = repo_root.resolve()
    manifest = _load_artwork_manifest(repo_root)
    asset_dir = repo_root / "boards" / "shields" / "nice_view_gem" / "assets"
    missing = [
        item["file"] for item in manifest["artworks"]
        if not (asset_dir / item["file"]).is_file()
    ]
    if missing:
        raise ValueError(f"installed artwork asset is missing: {missing[0]}")
    _write_artwork_integration(repo_root, manifest)
    return len(manifest["artworks"])
