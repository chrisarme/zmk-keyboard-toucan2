import subprocess
import sys
from pathlib import Path

from verify_battery_preview import count_lit, read_bmp


def main():
    executable = Path(sys.argv[1])
    output = Path(sys.argv[2])
    result = subprocess.run(
        [
            str(executable),
            "--left-battery",
            "75",
            "--right-battery",
            "40",
            "--wpm",
            "80",
            "--layer",
            "2",
            "--layer-name",
            "NAV",
            "--profile",
            "3",
            "--endpoint",
            "ble",
            "--connected",
            "--left-charging",
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
        raise AssertionError(f"expected 144x168 output, found {width}x{height}")

    regions = {
        "WPM chart": (12, 132, 78, 102),
        "layer label": (0, 121, 115, 137),
        "profile selector": (124, 136, 103, 157),
        "output label": (70, 120, 140, 157),
    }
    for name, bounds in regions.items():
        if count_lit(rows, *bounds) == 0:
            raise AssertionError(f"expected the {name} region to contain lit pixels")


if __name__ == "__main__":
    main()
