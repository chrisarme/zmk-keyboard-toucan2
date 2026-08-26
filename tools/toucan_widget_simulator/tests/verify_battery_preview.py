import struct
import subprocess
import sys
from pathlib import Path


def read_bmp(path: Path):
    data = path.read_bytes()
    if data[:2] != b"BM":
        raise AssertionError("simulator output is not a BMP")

    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    bits_per_pixel = struct.unpack_from("<H", data, 28)[0]
    if bits_per_pixel != 24:
        raise AssertionError(f"expected 24-bit BMP, found {bits_per_pixel}")

    row_size = (width * 3 + 3) & ~3
    rows = []
    for y in range(height):
        source_y = height - 1 - y
        row_start = pixel_offset + source_y * row_size
        rows.append(
            [
                tuple(reversed(data[row_start + x * 3 : row_start + x * 3 + 3]))
                for x in range(width)
            ]
        )
    return width, height, rows


def count_lit(rows, x_start, x_end, y_start, y_end):
    return sum(
        1
        for row in rows[y_start:y_end]
        for pixel in row[x_start:x_end]
        if pixel == (255, 255, 255)
    )


def main():
    executable = Path(sys.argv[1])
    output = Path(sys.argv[2])
    result = subprocess.run(
        [
            str(executable),
            "--left-battery",
            "100",
            "--right-battery",
            "10",
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

    left_lit = count_lit(rows, 8, 66, 15, 62)
    right_lit = count_lit(rows, 80, 138, 15, 62)
    if left_lit <= right_lit:
        raise AssertionError(
            f"100% left arc should have more lit pixels than 10% right arc: "
            f"left={left_lit}, right={right_lit}"
        )


if __name__ == "__main__":
    main()
