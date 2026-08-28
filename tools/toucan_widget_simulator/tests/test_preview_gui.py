import sys
import unittest
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from preview_gui import PreviewState, animation_spec, build_renderer_command


class RendererCommandTests(unittest.TestCase):
    def test_exposes_only_the_supported_left_charging_state(self):
        state_fields = {field.name for field in fields(PreviewState)}
        self.assertIn("left_charging", state_fields)
        self.assertNotIn("right_charging", state_fields)

    def test_uses_the_registered_8_fps_animation_metadata(self):
        self.assertEqual(animation_spec(3, 0), (8, 14))
        self.assertEqual(animation_spec(3, 1), (8, 8))
        self.assertIsNone(animation_spec(2, 0))

    def test_maps_the_complete_gui_state_to_renderer_options(self):
        state = PreviewState(
            screen=1,
            artwork=1,
            animation_frame=3,
            left_battery=82,
            right_battery=37,
            wpm=64,
            layer=2,
            layer_name="NAV",
            profile=3,
            endpoint="ble",
            connected=True,
            left_charging=True,
        )

        command = build_renderer_command(Path("renderer.exe"), Path("preview.bmp"), state)

        self.assertEqual(
            command,
            [
                "renderer.exe",
                "--screen",
                "1",
                "--artwork",
                "1",
                "--animation-frame",
                "3",
                "--left-battery",
                "82",
                "--right-battery",
                "37",
                "--wpm",
                "64",
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
                "preview.bmp",
            ],
        )


if __name__ == "__main__":
    unittest.main()
