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
    if len(set(encoded)) != 4:
        raise AssertionError("screens 0, 1, 2, and 3 should render four distinct frames")
    if frames[3][0][0] != (255, 255, 255):
        raise AssertionError("screen 3 logical black background should preview as unfilled white")
    if not any(pixel == (0, 0, 0) for row in frames[3] for pixel in row):
        raise AssertionError("screen 3 logical white artwork should preview as dark ink")

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
    if alternate_image_frame != frames[3]:
        raise AssertionError("screen 3 should render only the image, independent of status state")


if __name__ == "__main__":
    main()
