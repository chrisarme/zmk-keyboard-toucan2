import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firmware_size_report import (
    MemoryUsage,
    build_cli_output,
    format_comparison,
    format_report,
    parse_build_log,
)


SAMPLE_LOG = """\
build / Build (seeeduino_xiao_ble, toucan_left rgbled_adapter nice_view_gem)\tUNKNOWN STEP\tFLASH:      412908 B       788 KB     51.17%
build / Build (seeeduino_xiao_ble, toucan_left rgbled_adapter nice_view_gem)\tUNKNOWN STEP\tRAM:      111730 B       256 KB     42.62%
build / Build (seeeduino_xiao_ble, toucan_right rgbled_adapter)\tUNKNOWN STEP\tFLASH:      193868 B       788 KB     24.03%
build / Build (seeeduino_xiao_ble, toucan_right rgbled_adapter)\tUNKNOWN STEP\tRAM:       38108 B       256 KB     14.54%
build / Build (seeeduino_xiao_ble, settings_reset)\tUNKNOWN STEP\tFLASH:       49512 B       788 KB      6.14%
build / Build (seeeduino_xiao_ble, settings_reset)\tUNKNOWN STEP\tRAM:       11640 B       256 KB      4.44%
"""


class ParseBuildLogTests(unittest.TestCase):
    def test_extracts_exact_flash_and_ram_for_every_firmware_target(self):
        self.assertEqual(
            parse_build_log(SAMPLE_LOG),
            {
                "left": MemoryUsage(flash=412_908, ram=111_730),
                "right": MemoryUsage(flash=193_868, ram=38_108),
                "settings-reset": MemoryUsage(flash=49_512, ram=11_640),
            },
        )

    def test_formats_a_readable_exact_size_table(self):
        report = format_report("33210731075", parse_build_log(SAMPLE_LOG))

        self.assertIn("ZMK firmware sizes - run 33210731075", report)
        self.assertIn("left", report)
        self.assertIn("412,908 B (51.17%)", report)
        self.assertIn("111,730 B (42.62%)", report)
        self.assertIn("settings-reset", report)

    def test_compares_two_runs_with_signed_byte_deltas(self):
        before = parse_build_log(SAMPLE_LOG.replace("412908", "412956"))
        after = parse_build_log(SAMPLE_LOG)

        report = format_comparison("33204865929", before, "33210731075", after)

        self.assertIn("33204865929 -> 33210731075", report)
        self.assertIn("left", report)
        self.assertIn("412,956", report)
        self.assertIn("412,908", report)
        self.assertIn("-48 B", report)
        self.assertIn("+0 B", report)

    def test_cli_report_loads_the_requested_run(self):
        requested_runs = []

        output = build_cli_output(
            ["report", "33210731075"],
            lambda run_id: requested_runs.append(run_id) or SAMPLE_LOG,
        )

        self.assertEqual(requested_runs, ["33210731075"])
        self.assertIn("ZMK firmware sizes - run 33210731075", output)

    def test_cli_compare_loads_both_runs_in_order(self):
        logs = {
            "33204865929": SAMPLE_LOG.replace("412908", "412956"),
            "33210731075": SAMPLE_LOG,
        }

        output = build_cli_output(
            ["compare", "33204865929", "33210731075"], logs.__getitem__
        )

        self.assertIn("-48 B", output)


if __name__ == "__main__":
    unittest.main()
