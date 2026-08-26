import binascii
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "toucan_art.py"


def png_chunk(name: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(name + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", checksum)


def write_rgb_png(path: Path, rows):
    height = len(rows)
    width = len(rows[0])
    scanlines = b"".join(
        b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in rows
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(scanlines))
        + png_chunk(b"IEND", b"")
    )


def write_rgba_png(path: Path, rows):
    height = len(rows)
    width = len(rows[0])
    scanlines = b"".join(
        b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in rows
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(scanlines))
        + png_chunk(b"IEND", b"")
    )


def read_indexed_png(path: Path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("output is not a PNG")

    offset = 8
    chunks = {}
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        name = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        chunks.setdefault(name, []).append(payload)
        offset += 12 + length

    width, height, bit_depth, color_type, _, _, _ = struct.unpack(
        ">IIBBBBB", chunks[b"IHDR"][0]
    )
    palette_data = chunks[b"PLTE"][0]
    palette = [
        tuple(palette_data[index : index + 3])
        for index in range(0, len(palette_data), 3)
    ]
    raw = zlib.decompress(b"".join(chunks[b"IDAT"]))

    stride = (width + 7) // 8
    rows = []
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        if filter_type != 0:
            raise AssertionError(f"unexpected PNG filter {filter_type}")
        packed = raw[offset + 1 : offset + 1 + stride]
        rows.append(
            [
                palette[(packed[x // 8] >> (7 - (x % 8))) & 1]
                for x in range(width)
            ]
        )
        offset += 1 + stride

    return width, height, bit_depth, color_type, rows


class ExtractCommandTests(unittest.TestCase):
    def test_extracts_an_indexed_one_bit_lvgl_image_to_png(self):
        source = """
        #include <lvgl.h>

        const uint8_t checker_map[] = {
            0x00, 0x00, 0x00, 0xff,
            0xff, 0xff, 0xff, 0xff,
            0x80,
            0x40,
        };

        const lv_img_dsc_t checker = {
            .header.cf = LV_IMG_CF_INDEXED_1BIT,
            .header.w = 2,
            .header.h = 2,
            .data_size = 10,
            .data = checker_map,
        };
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "assets.c"
            output_dir = temp / "output"
            source_path.write_text(source, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "extract",
                    str(source_path),
                    "--output",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output_path = output_dir / "checker.png"
            self.assertTrue(output_path.is_file())

            width, height, bit_depth, color_type, rows = read_indexed_png(output_path)
            self.assertEqual((width, height), (2, 2))
            self.assertEqual((bit_depth, color_type), (1, 3))
            self.assertEqual(
                rows,
                [
                    [(255, 255, 255), (0, 0, 0)],
                    [(0, 0, 0), (255, 255, 255)],
                ],
            )

    def test_extracts_multiple_sources_and_builds_an_html_gallery(self):
        asset_template = """
        const uint8_t {name}_map[] = {{
            0x00, 0x00, 0x00, 0xff,
            0xff, 0xff, 0xff, 0xff,
            {pixel},
        }};

        const lv_img_dsc_t {name} = {{
            .header.cf = LV_IMG_CF_INDEXED_1BIT,
            .header.w = 1,
            .header.h = 1,
            .data_size = 9,
            .data = {name}_map,
        }};
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            first = temp / "first.c"
            second = temp / "second.c"
            output_dir = temp / "output"
            first.write_text(
                asset_template.format(name="black_pixel", pixel="0x00"),
                encoding="utf-8",
            )
            second.write_text(
                asset_template.format(name="white_pixel", pixel="0x80"),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "extract",
                    str(first),
                    str(second),
                    "--output",
                    str(output_dir),
                    "--gallery",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "black_pixel.png").is_file())
            self.assertTrue((output_dir / "white_pixel.png").is_file())
            gallery = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("black_pixel.png", gallery)
            self.assertIn("white_pixel.png", gallery)
            self.assertIn("image-rendering: pixelated", gallery)

    def test_recursively_scans_c_files_in_a_directory_and_ignores_headers(self):
        image_source = """
        const uint8_t {name}_map[] = {{
            0x00, 0x00, 0x00, 0xff,
            0xff, 0xff, 0xff, 0xff,
            0x80,
        }};

        const lv_img_dsc_t {name} = {{
            .header.cf = LV_IMG_CF_INDEXED_1BIT,
            .header.w = 1,
            .header.h = 1,
            .data_size = 9,
            .data = {name}_map,
        }};
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_dir = temp / "shield"
            nested_dir = source_dir / "widgets"
            output_dir = temp / "output"
            nested_dir.mkdir(parents=True)
            (source_dir / "font.c").write_text(
                "const int this_is_not_an_image = 1;", encoding="utf-8"
            )
            (nested_dir / "nested_art.c").write_text(
                image_source.format(name="nested_art"), encoding="utf-8"
            )
            (nested_dir / "header_art.h").write_text(
                image_source.format(name="header_art"), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "extract",
                    str(source_dir),
                    "--output",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "nested_art.png").is_file())
            self.assertFalse((output_dir / "header_art.png").exists())

    def test_extract_still_runs_when_optional_site_packages_are_disabled(self):
        source = """
        const uint8_t pixel_map[] = {
            0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0x80,
        };
        const lv_img_dsc_t pixel = {
            .header.cf = LV_IMG_CF_INDEXED_1BIT,
            .header.w = 1,
            .header.h = 1,
            .data_size = 9,
            .data = pixel_map,
        };
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "asset.c"
            source_path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(TOOL),
                    "extract",
                    str(source_path),
                    "--output",
                    str(temp / "out"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((temp / "out" / "pixel.png").is_file())


class ConvertCommandTests(unittest.TestCase):
    def test_converts_to_c_and_builds_preview_from_round_tripped_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "source.png"
            output_dir = temp / "generated"
            extracted_dir = temp / "extracted"
            write_rgb_png(
                source_path,
                [
                    [(0, 0, 0), (255, 255, 255)],
                    [(255, 255, 255), (0, 0, 0)],
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(output_dir),
                    "--size",
                    "2x2",
                    "--fit",
                    "stretch",
                    "--name",
                    "checker",
                    "--preview",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            c_path = output_dir / "checker.c"
            preview_path = output_dir / "checker.preview.png"
            self.assertTrue(c_path.is_file())
            self.assertTrue(preview_path.is_file())
            c_text = c_path.read_text(encoding="utf-8")
            self.assertIn("LV_IMG_CF_INDEXED_1BIT", c_text)
            self.assertIn(".data_size = 10", c_text)
            self.assertIn("0x80, 0x40", c_text)
            self.assertIn("10 data bytes", result.stdout)

            extract_result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "extract",
                    str(c_path),
                    "--output",
                    str(extracted_dir),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(extract_result.returncode, 0, extract_result.stderr)
            _, _, _, _, preview_rows = read_indexed_png(preview_path)
            _, _, _, _, logical_rows = read_indexed_png(
                extracted_dir / "checker.png"
            )
            black = (0, 0, 0)
            white = (255, 255, 255)
            self.assertEqual(preview_rows, [[black, white], [white, black]])
            self.assertEqual(logical_rows, [[white, black], [black, white]])

    def test_contain_preserves_aspect_ratio_and_uses_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "wide logo.png"
            output_dir = temp / "generated"
            write_rgb_png(source_path, [[(0, 0, 0), (0, 0, 0)]])

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(output_dir),
                    "--size",
                    "4x4",
                    "--preview",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            preview = output_dir / "wide_logo.preview.png"
            width, height, _, _, rows = read_indexed_png(preview)
            black = (0, 0, 0)
            white = (255, 255, 255)
            self.assertEqual((width, height), (4, 4))
            self.assertEqual(rows, [[white] * 4, [black] * 4, [black] * 4, [white] * 4])

    def test_output_preserves_black_white_and_transparent_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "transparent.png"
            output_dir = temp / "generated"
            write_rgba_png(
                source_path,
                [[(0, 0, 0, 255), (255, 255, 255, 255), (0, 0, 0, 0)]],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(output_dir),
                    "--size",
                    "3x1",
                    "--fit",
                    "stretch",
                    "--preview",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            c_text = (output_dir / "transparent.c").read_text(encoding="utf-8")
            self.assertIn("0x80,", c_text)
            _, _, _, _, rows = read_indexed_png(
                output_dir / "transparent.preview.png"
            )
            self.assertEqual(
                rows,
                [[(0, 0, 0), (255, 255, 255), (255, 255, 255)]],
            )

    def test_invert_option_intentionally_reverses_visible_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "art.png"
            output_dir = temp / "generated"
            write_rgb_png(source_path, [[(0, 0, 0), (255, 255, 255)]])

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(output_dir),
                    "--size",
                    "2x1",
                    "--fit",
                    "stretch",
                    "--invert",
                    "--preview",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            _, _, _, _, rows = read_indexed_png(output_dir / "art.preview.png")
            self.assertEqual(rows, [[(255, 255, 255), (0, 0, 0)]])

    def test_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "art.png"
            output_dir = temp / "generated"
            output_dir.mkdir()
            (output_dir / "art.c").write_text("keep me", encoding="utf-8")
            write_rgb_png(source_path, [[(0, 0, 0)]])
            command = [
                sys.executable,
                str(TOOL),
                "convert",
                str(source_path),
                "--output",
                str(output_dir),
                "--size",
                "1x1",
            ]

            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("refusing to overwrite", refused.stderr)
            self.assertEqual((output_dir / "art.c").read_text(encoding="utf-8"), "keep me")

            replaced = subprocess.run(command + ["--force"], capture_output=True, text=True)
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            self.assertIn("LV_IMG_CF_INDEXED_1BIT", (output_dir / "art.c").read_text())

    def test_rejects_threshold_outside_byte_range(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "art.png"
            write_rgb_png(source_path, [[(0, 0, 0)]])
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(temp / "out"),
                    "--size",
                    "1x1",
                    "--threshold",
                    "256",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("between 0 and 255", result.stderr)

    def test_reports_how_to_install_the_optional_dependency(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "art.png"
            write_rgb_png(source_path, [[(0, 0, 0)]])
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(temp / "out"),
                    "--size",
                    "1x1",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("static conversion requires Pillow", result.stderr)
            self.assertIn("requirements.txt", result.stderr)


if __name__ == "__main__":
    unittest.main()
