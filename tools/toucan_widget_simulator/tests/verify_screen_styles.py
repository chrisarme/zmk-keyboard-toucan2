import subprocess
import sys
from pathlib import Path

from verify_battery_preview import read_bmp


def render(executable: Path, output: Path, screen: int, overrides=None):
    overrides = overrides or []
    result = subprocess.run(
        [
            str(executable),
            "--screen",
            str(screen),
            "--left-battery",
            "75",
            "--right-battery",
            "40",
            "--layer-name",
            "NAV",
            "--profile",
            "3",
            "--endpoint",
            "ble",
            "--connected",
            *overrides,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    width, height, rows = read_bmp(output)
    if (width, height) != (144, 168):
        raise AssertionError(f"screen {screen}: expected 144x168, found {width}x{height}")
    return rows


def main():
    executable = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    frames = [
        render(executable, output_dir / f"screen-{screen}.bmp", screen)
        for screen in range(7)
    ]
    encoded = [tuple(pixel for row in frame for pixel in row) for frame in frames]
    if len(set(encoded[:4])) != 4:
        raise AssertionError("screens 0, 1, 2, and 3 should render four distinct frames")
    if not (frames[4] == frames[5] == frames[6]):
        raise AssertionError("animation validation screens should share artwork and differ only by FPS")
    artwork_pixels = [pixel for row in frames[3][:144] for pixel in row]
    if (0, 0, 0) not in artwork_pixels or (255, 255, 255) not in artwork_pixels:
        raise AssertionError("screen 3 artwork should contain both dark and light pixels")
    if frames[3][0][0] != (255, 255, 255):
        raise AssertionError("screen 3 artwork should use the standard light background")
    if frames[3][145][44] != (255, 255, 255):
        raise AssertionError("screen 3 footer should use the standard light background")

    alternate_image_frame = render(
        executable,
        output_dir / "screen-3-alternate-state.bmp",
        3,
        [
            "--left-battery",
            "1",
            "--right-battery",
            "99",
            "--layer-name",
            "SHOULD_NOT_APPEAR",
            "--profile",
            "4",
            "--endpoint",
            "usb",
        ],
    )
    if alternate_image_frame[:144] != frames[3][:144]:
        raise AssertionError("screen 3 artwork should not change with status state")
    if alternate_image_frame[144:] == frames[3][144:]:
        raise AssertionError("screen 3 footer should update with battery and profile state")

    footer_regions = {
        "left battery": (0, 40),
        "Bluetooth profiles": (48, 96),
        "right battery": (104, 144),
    }
    for name, (start_x, end_x) in footer_regions.items():
        dark_pixels = sum(
            pixel == (0, 0, 0)
            for row in frames[3][144:]
            for pixel in row[start_x:end_x]
        )
        light_pixels = sum(
            pixel == (255, 255, 255)
            for row in frames[3][144:]
            for pixel in row[start_x:end_x]
        )
        if dark_pixels == 0 or light_pixels == 0:
            raise AssertionError(f"screen 3 footer should visibly render {name}")

    next_animation_frame = render(
        executable,
        output_dir / "screen-4-frame-1.bmp",
        4,
        ["--animation-frame", "1"],
    )
    if next_animation_frame[:144] == frames[4][:144]:
        raise AssertionError("animation frame selection should change the artwork region")
    if next_animation_frame[144:] != frames[4][144:]:
        raise AssertionError("animation frame selection should not change the status footer")


if __name__ == "__main__":
    main()
