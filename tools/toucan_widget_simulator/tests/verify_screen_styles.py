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
        for screen in range(4)
    ]
    encoded = [tuple(pixel for row in frame for pixel in row) for frame in frames]
    if len(set(encoded[:4])) != 4:
        raise AssertionError("screens 0, 1, 2, and 3 should render four distinct frames")
    artwork_pixels = [pixel for row in frames[3][:144] for pixel in row]
    if (0, 0, 0) not in artwork_pixels or (255, 255, 255) not in artwork_pixels:
        raise AssertionError("screen 3 artwork should contain both dark and light pixels")
    if frames[3][0][0] != (255, 255, 255):
        raise AssertionError("screen 3 artwork should use the standard light background")
    if frames[3][145][44] != (255, 255, 255):
        raise AssertionError("screen 3 footer should use the standard light background")

    alternate_status_frame = render(
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
    if alternate_status_frame[:144] != frames[3][:144]:
        raise AssertionError("screen 3 artwork should not change with status state")
    if alternate_status_frame[144:] == frames[3][144:]:
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

    charging_frame = render(
        executable,
        output_dir / "screen-3-charging.bmp",
        3,
        ["--left-charging"],
    )
    if charging_frame[:144] != frames[3][:144]:
        raise AssertionError("charging should not change screen 3 artwork")
    for row_before, row_after in zip(frames[3][151:161], charging_frame[151:161]):
        if row_before[:35] != row_after[:35]:
            raise AssertionError("left charging should not move the left battery label")
    for row_before, row_after in zip(frames[3][149:160], charging_frame[149:160]):
        if row_before[35:38] != row_after[35:38] or row_before[45:48] != row_after[45:48]:
            raise AssertionError("left charging bolt should keep three-pixel side gaps")
    if all(
        row_before[38:45] == row_after[38:45]
        for row_before, row_after in zip(frames[3][149:160], charging_frame[149:160])
    ):
        raise AssertionError("left charging should draw its bolt in the fixed footer gap")
    for row_before, row_after in zip(frames[3][144:], charging_frame[144:]):
        if row_before[48:] != row_after[48:]:
            raise AssertionError("left charging should not change profiles or right battery")

    for screen in range(3):
        charging_screen = render(
            executable,
            output_dir / f"screen-{screen}-charging.bmp",
            screen,
            ["--left-charging"],
        )
        if charging_screen == frames[screen]:
            raise AssertionError(f"left charging should be visible on screen {screen}")
        for row_before, row_after in zip(frames[screen], charging_screen):
            if row_before[80:] != row_after[80:]:
                raise AssertionError(
                    f"left charging should not change the right battery on screen {screen}"
                )

    next_animation_frame = render(
        executable,
        output_dir / "screen-3-frame-1.bmp",
        3,
        ["--animation-frame", "1"],
    )
    if next_animation_frame[:144] == frames[3][:144]:
        raise AssertionError("animation frame selection should change the artwork region")
    if next_animation_frame[144:] != frames[3][144:]:
        raise AssertionError("animation frame selection should not change the status footer")

    bonfire_frame = render(
        executable,
        output_dir / "screen-3-bonfire.bmp",
        3,
        ["--artwork", "1"],
    )
    if bonfire_frame[:144] == frames[3][:144]:
        raise AssertionError("artwork selection should change the artwork region")
    if bonfire_frame[144:] != frames[3][144:]:
        raise AssertionError("artwork selection should not change the status footer")

if __name__ == "__main__":
    main()
