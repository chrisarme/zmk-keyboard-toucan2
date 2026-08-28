# Firmware Size Report

This host-only tool reads the linker summary already present in a completed ZMK GitHub Actions
build log. It reports exact linked FLASH and RAM usage without changing the firmware or build
workflow, so it consumes no controller storage.

## Requirements

- Python 3
- GitHub CLI (`gh`), authenticated for the repository
- A completed `Build ZMK firmware` run ID from the run's Actions URL

For example, the run ID in
`https://github.com/chrisarme/zmk-keyboard-toucan2/actions/runs/33210731075` is
`33210731075`.

## Report one build

From the repository root:

```powershell
py -3 tools\firmware_size_report\firmware_size_report.py report 33210731075
```

The table reports exact linked bytes and capacity percentages for the left, right, and
settings-reset firmware targets.

## Compare two builds

Pass the older run first and the newer run second:

```powershell
py -3 tools\firmware_size_report\firmware_size_report.py compare `
  33204865929 `
  33210731075
```

Negative deltas mean the newer firmware is smaller. Positive deltas mean it grew.

## Test

```powershell
py -3 -m unittest discover -s tools\firmware_size_report\tests -v
```

The parser requires FLASH and RAM entries for all three build targets. It exits with an error
instead of presenting an incomplete report when a run is unfinished, expired, inaccessible, or
does not contain the expected targets.
