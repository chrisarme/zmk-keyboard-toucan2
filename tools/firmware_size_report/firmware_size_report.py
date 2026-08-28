#!/usr/bin/env python3
"""Report exact linked firmware sizes from a completed ZMK GitHub Actions run."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class MemoryUsage:
    flash: int
    ram: int


_USAGE_PATTERN = re.compile(r"\b(FLASH|RAM):\s+(\d+)\s+B\b")
_TARGET_MARKERS = (
    ("toucan_left", "left"),
    ("toucan_right", "right"),
    ("settings_reset", "settings-reset"),
)
_FLASH_CAPACITY = 788 * 1024
_RAM_CAPACITY = 256 * 1024
_TARGET_ORDER = ("left", "right", "settings-reset")


def parse_build_log(log_text: str) -> dict[str, MemoryUsage]:
    """Extract linked FLASH and RAM bytes for each Toucan build target."""
    values: dict[str, dict[str, int]] = {}
    for line in log_text.splitlines():
        target = next(
            (name for marker, name in _TARGET_MARKERS if marker in line), None
        )
        match = _USAGE_PATTERN.search(line)
        if target is None or match is None:
            continue
        region, byte_count = match.groups()
        values.setdefault(target, {})[region.lower()] = int(byte_count)

    return {
        target: MemoryUsage(flash=regions["flash"], ram=regions["ram"])
        for target, regions in values.items()
        if "flash" in regions and "ram" in regions
    }


def _format_usage(byte_count: int, capacity: int) -> str:
    return f"{byte_count:,} B ({byte_count / capacity:.2%})"


def format_report(run_id: str, sizes: dict[str, MemoryUsage]) -> str:
    """Format one run's exact linked sizes as a compact table."""
    lines = [
        f"ZMK firmware sizes - run {run_id}",
        f"{'Target':<15} {'FLASH':>20} {'RAM':>20}",
    ]
    for target in _TARGET_ORDER:
        if target not in sizes:
            continue
        usage = sizes[target]
        lines.append(
            f"{target:<15} "
            f"{_format_usage(usage.flash, _FLASH_CAPACITY):>20} "
            f"{_format_usage(usage.ram, _RAM_CAPACITY):>20}"
        )
    return "\n".join(lines)


def _format_delta(byte_count: int) -> str:
    return f"{byte_count:+,} B"


def format_comparison(
    before_run_id: str,
    before: dict[str, MemoryUsage],
    after_run_id: str,
    after: dict[str, MemoryUsage],
) -> str:
    """Format exact before/after sizes and signed byte deltas."""
    lines = [
        f"ZMK firmware size comparison - {before_run_id} -> {after_run_id}",
        (
            f"{'Target':<15} {'FLASH before':>14} {'FLASH after':>14} "
            f"{'dFLASH':>11} {'RAM before':>12} {'RAM after':>12} {'dRAM':>11}"
        ),
    ]
    for target in _TARGET_ORDER:
        if target not in before or target not in after:
            continue
        old = before[target]
        new = after[target]
        lines.append(
            f"{target:<15} {old.flash:>14,} {new.flash:>14,} "
            f"{_format_delta(new.flash - old.flash):>11} "
            f"{old.ram:>12,} {new.ram:>12,} "
            f"{_format_delta(new.ram - old.ram):>11}"
        )
    return "\n".join(lines)


def fetch_build_log(run_id: str) -> str:
    """Download one completed workflow run's combined log through GitHub CLI."""
    try:
        result = subprocess.run(
            ["gh", "run", "view", run_id, "--log"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "GitHub CLI (gh) was not found; install and authenticate it first"
        ) from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "GitHub CLI could not read the run"
        raise RuntimeError(detail) from error
    return result.stdout


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report exact FLASH and RAM usage from ZMK GitHub Actions logs."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="show sizes for one completed run")
    report.add_argument("run_id", help="GitHub Actions run ID")
    compare = commands.add_parser("compare", help="compare two completed runs")
    compare.add_argument("before_run_id", help="older GitHub Actions run ID")
    compare.add_argument("after_run_id", help="newer GitHub Actions run ID")
    return parser


def _load_sizes(
    run_id: str, load_log: Callable[[str], str]
) -> dict[str, MemoryUsage]:
    sizes = parse_build_log(load_log(run_id))
    missing = [target for target in _TARGET_ORDER if target not in sizes]
    if missing:
        raise RuntimeError(
            f"run {run_id} is missing size data for: {', '.join(missing)}"
        )
    return sizes


def build_cli_output(
    argv: Sequence[str], load_log: Callable[[str], str] = fetch_build_log
) -> str:
    """Build command output; injectable log loading keeps parsing locally testable."""
    args = _argument_parser().parse_args(argv)
    if args.command == "report":
        return format_report(args.run_id, _load_sizes(args.run_id, load_log))

    before = _load_sizes(args.before_run_id, load_log)
    after = _load_sizes(args.after_run_id, load_log)
    return format_comparison(
        args.before_run_id, before, args.after_run_id, after
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        print(build_cli_output(sys.argv[1:] if argv is None else argv))
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
