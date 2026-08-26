import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "toucan_art.py"


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


if __name__ == "__main__":
    unittest.main()
