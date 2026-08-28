import binascii
import json
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
    def test_converts_animated_gif_to_frame_table_and_preview(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "blink.gif"
            output_dir = temp / "generated"
            first = Image.new("RGB", (2, 1), "black")
            second = Image.new("RGB", (2, 1), "white")
            first.save(
                source_path,
                save_all=True,
                append_images=[second],
                duration=[200, 200],
                loop=0,
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
                    "2x1",
                    "--fit",
                    "stretch",
                    "--fps",
                    "5",
                    "--preview",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            c_text = (output_dir / "blink.c").read_text(encoding="utf-8")
            self.assertIn("blink_frame_000", c_text)
            self.assertIn("blink_frame_001", c_text)
            self.assertIn("const lv_img_dsc_t *const blink_frames[]", c_text)
            self.assertIn("const uint8_t blink_frame_count = 2", c_text)
            self.assertIn("const uint32_t blink_duration_ms = 400", c_text)
            self.assertTrue((output_dir / "blink.preview.gif").is_file())
            self.assertIn("2 frames", result.stdout)
            self.assertIn("18 data bytes", result.stdout)

    def test_warns_when_animation_rate_exceeds_keyboard_recommendation(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "fast.gif"
            first = Image.new("RGB", (1, 1), "black")
            second = Image.new("RGB", (1, 1), "white")
            first.save(
                source_path,
                save_all=True,
                append_images=[second],
                duration=[500, 500],
                loop=0,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(temp / "generated"),
                    "--size",
                    "1x1",
                    "--fps",
                    "12",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("above the 10 FPS keyboard validation range", result.stderr)

    def test_frame_cap_preserves_cycle_and_reports_effective_rate(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "capped.gif"
            frames = [
                Image.new("RGB", (2, 2), color)
                for color in ("black", "white", "black", "white")
            ]
            frames[0].save(
                source_path,
                save_all=True,
                append_images=frames[1:],
                duration=[250, 250, 250, 250],
                loop=0,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(temp / "generated"),
                    "--size",
                    "2x2",
                    "--fps",
                    "10",
                    "--max-frames",
                    "3",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            c_text = (temp / "generated" / "capped.c").read_text(encoding="utf-8")
            self.assertIn("const uint8_t capped_frame_count = 3", c_text)
            self.assertIn("const uint32_t capped_duration_ms = 1000", c_text)
            self.assertIn("limited to 3 frames", result.stderr)
            self.assertIn("effective 3.00 FPS", result.stderr)

    def test_sampling_covers_partial_final_frame_interval(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "half_second.gif"
            frames = [Image.new("RGB", (1, 1), color) for color in ("black", "white")]
            frames[0].save(
                source_path,
                save_all=True,
                append_images=frames[1:],
                duration=[250, 250],
                loop=0,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(temp / "generated"),
                    "--size",
                    "1x1",
                    "--fps",
                    "5",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            c_text = (temp / "generated" / "half_second.c").read_text(encoding="utf-8")
            self.assertIn("const uint8_t half_second_frame_count = 3", c_text)

    def test_selects_a_timed_segment_before_sampling(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "segment.gif"
            frames = [
                Image.new("RGB", (1, 1), color)
                for color in ("black", "white", "black", "white")
            ]
            frames[0].save(
                source_path,
                save_all=True,
                append_images=frames[1:],
                duration=[250, 250, 250, 250],
                loop=0,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(temp / "generated"),
                    "--size",
                    "1x1",
                    "--fps",
                    "4",
                    "--start-time",
                    "250",
                    "--duration",
                    "500",
                    "--preview",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            c_text = (temp / "generated" / "segment.c").read_text(encoding="utf-8")
            self.assertIn("const uint8_t segment_frame_count = 2", c_text)
            self.assertIn("const uint32_t segment_duration_ms = 500", c_text)
            with Image.open(temp / "generated" / "segment.preview.gif") as preview:
                self.assertEqual(preview.convert("RGB").getpixel((0, 0)), (255, 255, 255))
                preview.seek(1)
                self.assertEqual(preview.convert("RGB").getpixel((0, 0)), (0, 0, 0))

    def test_composites_partial_gif_frames_using_disposal_rules(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "disposal.gif"
            palette = [255, 0, 255, 255, 255, 255, 0, 0, 0] + [0, 0, 0] * 253
            frames = []
            for pixels in ([2, 1, 1], [0, 2, 0], [0, 0, 2]):
                frame = Image.new("P", (3, 1))
                frame.putpalette(palette)
                frame.putdata(pixels)
                frames.append(frame)
            frames[0].save(
                source_path,
                save_all=True,
                append_images=frames[1:],
                duration=[200, 200, 200],
                loop=0,
                transparency=0,
                background=1,
                disposal=[2, 1, 1],
                optimize=False,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "convert",
                    str(source_path),
                    "--output",
                    str(temp / "generated"),
                    "--size",
                    "3x1",
                    "--fit",
                    "stretch",
                    "--fps",
                    "5",
                    "--preview",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            expected = [
                [(0, 0, 0), (255, 255, 255), (255, 255, 255)],
                [(255, 255, 255), (0, 0, 0), (255, 255, 255)],
                [(255, 255, 255), (0, 0, 0), (0, 0, 0)],
            ]
            with Image.open(temp / "generated" / "disposal.preview.gif") as preview:
                for index, pixels in enumerate(expected):
                    preview.seek(index)
                    self.assertEqual(
                        [preview.convert("RGB").getpixel((x, 0)) for x in range(3)],
                        pixels,
                    )

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


class ArtworkManagerTests(unittest.TestCase):
    def test_install_centers_width_and_leaves_two_pixels_above_footer_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "centered.png"
            write_rgb_png(source, [[(0, 0, 0)]])

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "install",
                    str(source),
                    "--name",
                    "centered",
                    "--repo-root",
                    str(repo),
                    "--size",
                    "120x100",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(
                (repo / "config" / "toucan_artworks.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artworks"][0]["x"], 12)
            self.assertEqual(manifest["artworks"][0]["y"], 42)

    def test_install_converts_and_registers_a_static_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "little ghost.png"
            write_rgb_png(source, [[(0, 0, 0), (255, 255, 255)]])

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "install",
                    str(source),
                    "--name",
                    "little_ghost",
                    "--repo-root",
                    str(repo),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(
                (repo / "config" / "toucan_artworks.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artworks"][0]["name"], "little_ghost")
            self.assertEqual(manifest["artworks"][0]["frame_count"], 1)
            self.assertTrue(
                (
                    repo
                    / "boards"
                    / "shields"
                    / "nice_view_gem"
                    / "assets"
                    / "little_ghost.c"
                ).is_file()
            )
            registry = (
                repo
                / "boards"
                / "shields"
                / "nice_view_gem"
                / "widgets"
                / "artwork_registry.c"
            ).read_text(encoding="utf-8")
            self.assertIn("little_ghost_frames", registry)
            self.assertIn(".interval_ms = 0", registry)
            self.assertTrue((repo / "config" / "toucan_artworks.cmake").is_file())

    def test_list_reports_indexes_timing_and_flash_cost(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            manifest_path = repo / "config" / "toucan_artworks.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "artworks": [
                            {
                                "name": "bonfire",
                                "file": "bonfire.c",
                                "symbol": "bonfire",
                                "animated": True,
                                "frame_count": 8,
                                "fps": 8,
                                "interval_ms": 125,
                                "x": 1,
                                "y": 2,
                                "data_bytes": 20512,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "list",
                    "--repo-root",
                    str(repo),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0  bonfire", result.stdout)
            self.assertIn("8 frames", result.stdout)
            self.assertIn("8 FPS", result.stdout)
            self.assertIn("20,512 bytes", result.stdout)
            self.assertIn("Total image data: 20,512 bytes", result.stdout)

    def test_remove_deletes_the_asset_and_regenerates_indexes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = repo / "config"
            assets = repo / "boards" / "shields" / "nice_view_gem" / "assets"
            config.mkdir(parents=True)
            assets.mkdir(parents=True)
            entries = []
            for name in ("first", "second"):
                (assets / f"{name}.c").write_text(name, encoding="utf-8")
                entries.append(
                    {
                        "name": name,
                        "file": f"{name}.c",
                        "symbol": name,
                        "animated": False,
                        "frame_count": 1,
                        "fps": 0,
                        "interval_ms": 0,
                        "x": 1,
                        "y": 2,
                        "data_bytes": 2564,
                    }
                )
            (config / "toucan_artworks.json").write_text(
                json.dumps({"version": 1, "artworks": entries}), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "remove",
                    "first",
                    "--repo-root",
                    str(repo),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((assets / "first.c").exists())
            self.assertTrue((assets / "second.c").is_file())
            manifest = json.loads(
                (config / "toucan_artworks.json").read_text(encoding="utf-8")
            )
            self.assertEqual([item["name"] for item in manifest["artworks"]], ["second"])
            header = (
                repo / "include" / "dt-bindings" / "zmk" / "toucan_artwork.h"
            ).read_text(encoding="utf-8")
            self.assertIn("#define TOUCAN_ARTWORK_SECOND 0", header)
            self.assertIn("#define TOUCAN_ARTWORK_COUNT 1", header)

    def test_sync_recreates_integration_files_from_the_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = repo / "config"
            assets = repo / "boards" / "shields" / "nice_view_gem" / "assets"
            config.mkdir(parents=True)
            assets.mkdir(parents=True)
            (assets / "campfire.c").write_text("compiled art", encoding="utf-8")
            (config / "toucan_artworks.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "artworks": [
                            {
                                "name": "campfire",
                                "file": "campfire.c",
                                "symbol": "campfire",
                                "animated": True,
                                "frame_count": 8,
                                "fps": 8,
                                "interval_ms": 125,
                                "x": 1,
                                "y": 2,
                                "data_bytes": 20512,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "sync",
                    "--repo-root",
                    str(repo),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("synced 1 artwork", result.stdout)
            registry = (
                repo
                / "boards"
                / "shields"
                / "nice_view_gem"
                / "widgets"
                / "artwork_registry.c"
            ).read_text(encoding="utf-8")
            self.assertIn("campfire_frames", registry)

    def test_install_force_replaces_an_entry_without_changing_its_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "art.png"
            write_rgb_png(source, [[(0, 0, 0)]])
            command = [
                sys.executable,
                str(TOOL),
                "install",
                str(source),
                "--name",
                "art",
                "--repo-root",
                str(repo),
            ]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)

            write_rgb_png(source, [[(255, 255, 255)]])
            replaced = subprocess.run(
                command + ["--force"], capture_output=True, text=True
            )

            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            manifest = json.loads(
                (repo / "config" / "toucan_artworks.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(manifest["artworks"]), 1)
            self.assertEqual(manifest["artworks"][0]["name"], "art")

    def test_sync_rejects_an_asset_path_outside_the_assets_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = repo / "config"
            assets = repo / "boards" / "shields" / "nice_view_gem" / "assets"
            config.mkdir(parents=True)
            assets.mkdir(parents=True)
            escaped = assets.parent / "escaped.c"
            escaped.write_text("do not touch", encoding="utf-8")
            entry = {
                "name": "escaped",
                "file": "../escaped.c",
                "symbol": "escaped",
                "animated": False,
                "frame_count": 1,
                "fps": 0,
                "interval_ms": 0,
                "x": 1,
                "y": 2,
                "data_bytes": 2564,
            }
            (config / "toucan_artworks.json").write_text(
                json.dumps({"version": 1, "artworks": [entry]}), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "sync",
                    "--repo-root",
                    str(repo),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("plain C filename", result.stderr)
            self.assertEqual(escaped.read_text(encoding="utf-8"), "do not touch")

    def test_install_rejects_artwork_that_overlaps_the_footer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            source = repo / "oversized.png"
            write_rgb_png(source, [[(0, 0, 0)]])
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "install",
                    str(source),
                    "--name",
                    "oversized",
                    "--repo-root",
                    str(repo),
                    "--y",
                    "3",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("144x144 artwork area", result.stderr)


if __name__ == "__main__":
    unittest.main()
