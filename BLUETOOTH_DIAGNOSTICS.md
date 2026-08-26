# Bluetooth diagnostics

The GitHub Actions build includes an optional `toucan_left_bluetooth_diagnostic`
firmware artifact. It enables ZMK debug logging through a USB serial (CDC ACM)
port while the keyboard continues to send key and trackpad reports to the PC
over Bluetooth.

Logging consumes additional power and processing time. Use this image only to
capture a problem, then flash the normal left firmware again.

## Capture a log

1. Download the firmware archive from the latest successful GitHub Actions run.
2. Flash the `toucan_left_bluetooth_diagnostic` image to the left half only.
3. Connect the left half to the PC over USB.
4. Make the keyboard prefer Bluetooth output:
   - Hold the left-middle thumb key to activate `NAV`.
   - While holding it, hold the left-inner thumb key to activate `SET`.
   - While holding both, press the top-right key (the Backspace position).
5. In Windows Device Manager, open **Ports (COM & LPT)** and note the COM port
   exposed by the keyboard.
6. Open that port at 115200 baud with PuTTY, Arduino Serial Monitor, or another
   serial terminal. Enable session logging in the terminal if available.
7. Reproduce the delayed or repeated keystrokes and note the approximate time.
8. Save the complete log, including at least 30 seconds before and after the
   problem.

The keyboard may remember that Bluetooth is preferred after flashing normal
firmware. To prefer USB again, use the same `NAV` + `SET` chord and press the
second key from the right on the top row (the semicolon position).

Do not use the `settings_reset` image for logging. It erases Bluetooth, split,
and other persistent settings.
