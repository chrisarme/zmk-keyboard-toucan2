import subprocess
import sys
from pathlib import Path

from verify_battery_preview import read_bmp


def render(executable: Path, output: Path, screen: int):
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
        for screen in range(3)
    ]
    encoded = [tuple(pixel for row in frame for pixel in row) for frame in frames]
    if len(set(encoded)) != 3:
        raise AssertionError("screens 0, 1, and 2 should render three distinct frames")


if __name__ == "__main__":
    main()
