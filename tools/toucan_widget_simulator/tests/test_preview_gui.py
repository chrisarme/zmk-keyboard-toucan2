import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from preview_gui import PreviewState, build_renderer_command


class RendererCommandTests(unittest.TestCase):
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
            right_charging=False,
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
