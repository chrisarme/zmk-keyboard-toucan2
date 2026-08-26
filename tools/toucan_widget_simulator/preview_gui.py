from __future__ import annotations

import struct
import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk


@dataclass(frozen=True)
class PreviewState:
    screen: int = 2
    animation_frame: int = 0
    left_battery: int = 75
    right_battery: int = 50
    wpm: int = 0
    layer: int = 0
    layer_name: str = "BASE"
    profile: int = 0
    endpoint: str = "ble"
    connected: bool = True
    left_charging: bool = False
    right_charging: bool = False


def build_renderer_command(
    renderer: Path, output: Path, state: PreviewState
) -> list[str]:
    command = [
        str(renderer),
        "--screen",
        str(state.screen),
        "--animation-frame",
        str(state.animation_frame),
        "--left-battery",
        str(state.left_battery),
        "--right-battery",
        str(state.right_battery),
        "--wpm",
        str(state.wpm),
        "--layer",
        str(state.layer),
    ]
    if state.layer_name:
        command.extend(["--layer-name", state.layer_name])
    command.extend(
        [
            "--profile",
            str(state.profile),
            "--endpoint",
            state.endpoint,
        ]
    )
    if state.connected:
        command.append("--connected")
    if state.left_charging:
        command.append("--left-charging")
    if state.right_charging:
        command.append("--right-charging")
    command.extend(["--output", str(output)])
    return command


def read_bmp_pixels(path: Path) -> tuple[int, int, list[list[str]]]:
    data = path.read_bytes()
    if data[:2] != b"BM":
        raise ValueError("renderer output is not a BMP")

    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    bits_per_pixel = struct.unpack_from("<H", data, 28)[0]
    if width <= 0 or height <= 0 or bits_per_pixel != 24:
        raise ValueError("renderer output must be a bottom-up 24-bit BMP")

    row_size = (width * 3 + 3) & ~3
    rows: list[list[str]] = []
    for y in range(height):
        source_y = height - 1 - y
        row_start = pixel_offset + source_y * row_size
        rows.append(
            [
                "#f4f0df"
                if data[row_start + x * 3] >= 128
                else "#080a09"
                for x in range(width)
            ]
        )
    return width, height, rows


class PreviewApp:
    BACKGROUND = "#151817"
    PANEL = "#202522"
    INK = "#f4f0df"
    MUTED = "#9ba49e"
    ACCENT = "#d7a942"
    DISPLAY = "#080a09"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.base_dir = Path(__file__).resolve().parent
        self.renderer = self.base_dir / "build" / "toucan_widget_simulator.exe"
        self.output = self.base_dir / "previews" / "gui-preview.bmp"
        self.pending_render: str | None = None
        self.preview_image: tk.PhotoImage | None = None
        self.animation_frame = 0

        self.screen = tk.IntVar(value=2)
        self.left_battery = tk.IntVar(value=75)
        self.right_battery = tk.IntVar(value=50)
        self.wpm = tk.IntVar(value=0)
        self.layer = tk.IntVar(value=0)
        self.layer_name = tk.StringVar(value="BASE")
        self.profile = tk.IntVar(value=0)
        self.endpoint = tk.StringVar(value="ble")
        self.connected = tk.BooleanVar(value=True)
        self.left_charging = tk.BooleanVar(value=False)
        self.right_charging = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="READY")

        self._configure_window()
        self._build_layout()
        self._watch_controls()
        self.root.after(100, self.render_preview)

    def _configure_window(self) -> None:
        self.root.title("TOUCAN // DISPLAY LAB")
        self.root.geometry("880x700")
        self.root.minsize(820, 680)
        self.root.configure(bg=self.BACKGROUND)

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.BACKGROUND)
        style.configure(
            "Panel.TFrame", background=self.PANEL, relief="flat", borderwidth=0
        )
        style.configure(
            "TLabel",
            background=self.PANEL,
            foreground=self.INK,
            font=("Cascadia Mono", 9),
        )
        style.configure(
            "Muted.TLabel",
            background=self.PANEL,
            foreground=self.MUTED,
            font=("Cascadia Mono", 8),
        )
        style.configure(
            "Title.TLabel",
            background=self.BACKGROUND,
            foreground=self.INK,
            font=("Bahnschrift SemiCondensed", 20, "bold"),
        )
        style.configure(
            "Accent.TButton",
            background=self.ACCENT,
            foreground="#111411",
            font=("Cascadia Mono", 9, "bold"),
            borderwidth=0,
            padding=(10, 7),
        )
        style.map("Accent.TButton", background=[("active", "#efc76a")])
        style.configure(
            "TCheckbutton",
            background=self.PANEL,
            foreground=self.INK,
            font=("Cascadia Mono", 9),
        )
        style.map("TCheckbutton", background=[("active", self.PANEL)])
        style.configure(
            "TCombobox",
            fieldbackground="#111411",
            background=self.PANEL,
            foreground=self.INK,
            arrowcolor=self.ACCENT,
        )
        style.configure(
            "TSpinbox", fieldbackground="#111411", foreground=self.INK
        )
        style.configure("TEntry", fieldbackground="#111411", foreground=self.INK)

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, padding=20)
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="TOUCAN // DISPLAY LAB", style="Title.TLabel").pack(
            side="left"
        )
        tk.Label(
            header,
            textvariable=self.status,
            bg=self.BACKGROUND,
            fg=self.ACCENT,
            font=("Cascadia Mono", 9, "bold"),
        ).pack(side="right", pady=(9, 0))

        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        controls = ttk.Frame(body, style="Panel.TFrame", padding=18)
        controls.grid(row=0, column=0, sticky="ns", padx=(0, 18))
        controls.configure(width=300)
        controls.grid_propagate(False)
        self.controls = controls
        display_panel = ttk.Frame(body, style="Panel.TFrame", padding=16)
        display_panel.grid(row=0, column=1, sticky="nsew")

        ttk.Label(controls, text="SCREEN", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        ttk.Combobox(
            controls,
            values=(0, 1, 2, 3),
            state="readonly",
            width=5,
            textvariable=self.screen,
        ).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(0, 10))

        ttk.Label(controls, text="POWER", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        self._add_scale(controls, 2, "LEFT", self.left_battery, 100)
        self._add_scale(controls, 3, "RIGHT", self.right_battery, 100)
        ttk.Checkbutton(
            controls, text="L CHG", variable=self.left_charging
        ).grid(row=4, column=0, sticky="w", pady=(2, 12))
        ttk.Checkbutton(
            controls, text="R CHG", variable=self.right_charging
        ).grid(row=4, column=1, sticky="w", pady=(2, 12))

        ttk.Label(controls, text="ACTIVITY", style="Muted.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        self._add_scale(controls, 6, "WPM", self.wpm, 255)

        ttk.Label(controls, text="LAYER", style="Muted.TLabel").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(10, 6)
        )
        ttk.Label(controls, text="LAYER #").grid(row=8, column=0, sticky="w")
        ttk.Spinbox(
            controls, from_=0, to=255, width=5, textvariable=self.layer
        ).grid(row=8, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(controls, text="NAME").grid(row=9, column=0, sticky="w", pady=(5, 0))
        ttk.Entry(controls, width=12, textvariable=self.layer_name).grid(
            row=9, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(5, 0)
        )
        ttk.Label(
            controls,
            text="Layer # is the ZMK layer number. It appears as L#n only when NAME is blank.",
            style="Muted.TLabel",
            wraplength=245,
            justify="left",
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(5, 12))

        ttk.Label(controls, text="WIRELESS", style="Muted.TLabel").grid(
            row=11, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        ttk.Label(controls, text="PROFILE").grid(row=12, column=0, sticky="w")
        ttk.Spinbox(
            controls, from_=0, to=4, width=5, textvariable=self.profile
        ).grid(row=12, column=1, sticky="ew", padx=(8, 0))
        ttk.Combobox(
            controls,
            values=("ble", "usb", "none"),
            state="readonly",
            width=9,
            textvariable=self.endpoint,
        ).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(5, 3))
        ttk.Checkbutton(
            controls, text="CONNECTED", variable=self.connected
        ).grid(row=14, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(
            controls,
            text="PREVIEW UPDATES AUTOMATICALLY",
            style="Muted.TLabel",
        ).grid(row=15, column=0, columnspan=3, sticky="w")
        controls.columnconfigure(1, weight=1)

        ttk.Label(display_panel, text="SHARP MEMORY LCD // 144 × 168", style="Muted.TLabel").pack(
            anchor="w", pady=(0, 10)
        )
        bezel = tk.Frame(display_panel, bg="#050605", padx=12, pady=12)
        bezel.pack(expand=True)
        self.canvas = tk.Canvas(
            bezel,
            width=432,
            height=504,
            bg=self.DISPLAY,
            highlightthickness=1,
            highlightbackground="#3a403c",
        )
        self.canvas.pack()
        self.canvas.create_text(
            216,
            252,
            text="AWAITING RENDERER",
            fill="#667069",
            font=("Cascadia Mono", 10),
            tags="placeholder",
        )

    def _add_scale(
        self, parent: ttk.Frame, row: int, label: str, variable: tk.IntVar, maximum: int
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        scale = tk.Scale(
            parent,
            from_=0,
            to=maximum,
            orient="horizontal",
            length=145,
            showvalue=False,
            resolution=1,
            variable=variable,
            command=lambda _value: self.schedule_render(),
            bg=self.PANEL,
            fg=self.INK,
            troughcolor="#0d100e",
            activebackground=self.ACCENT,
            highlightthickness=0,
            bd=0,
        )
        scale.grid(row=row, column=1, sticky="ew", padx=(8, 6))
        ttk.Label(parent, textvariable=variable, width=3, anchor="e").grid(
            row=row, column=2, sticky="e"
        )

    def _watch_controls(self) -> None:
        for variable in (
            self.screen,
            self.layer,
            self.layer_name,
            self.profile,
            self.endpoint,
            self.connected,
            self.left_charging,
            self.right_charging,
        ):
            variable.trace_add("write", lambda *_args: self.schedule_render())

    def current_state(self) -> PreviewState:
        return PreviewState(
            screen=self.screen.get(),
            animation_frame=self.animation_frame,
            left_battery=self.left_battery.get(),
            right_battery=self.right_battery.get(),
            wpm=self.wpm.get(),
            layer=self.layer.get(),
            layer_name=self.layer_name.get().strip(),
            profile=self.profile.get(),
            endpoint=self.endpoint.get(),
            connected=self.connected.get(),
            left_charging=self.left_charging.get(),
            right_charging=self.right_charging.get(),
        )

    def schedule_render(self) -> None:
        if self.pending_render is not None:
            self.root.after_cancel(self.pending_render)
        self.pending_render = self.root.after(140, self.render_preview)

    def render_preview(self) -> None:
        self.pending_render = None
        if not self.renderer.exists():
            self.status.set("BUILD RENDERER FIRST")
            return

        self.output.parent.mkdir(parents=True, exist_ok=True)
        command = build_renderer_command(self.renderer, self.output, self.current_state())
        startup_info = None
        creation_flags = 0
        if sys.platform == "win32":
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creation_flags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            startupinfo=startup_info,
            creationflags=creation_flags,
        )
        if result.returncode != 0:
            self.status.set((result.stderr or "RENDER FAILED").strip().upper())
            return

        try:
            width, height, rows = read_bmp_pixels(self.output)
            source = tk.PhotoImage(width=width, height=height)
            for y, row in enumerate(rows):
                source.put("{" + " ".join(row) + "}", to=(0, y))
            self.preview_image = source.zoom(3, 3)
            self.canvas.delete("all")
            self.canvas.create_image(216, 252, image=self.preview_image)
            animation_fps = 8 if self.screen.get() == 3 else None
            if animation_fps:
                self.status.set(f"ANIMATION // {animation_fps} FPS")
                self.animation_frame = (self.animation_frame + 1) % 14
                self.pending_render = self.root.after(
                    round(1000 / animation_fps), self.render_preview
                )
            else:
                self.animation_frame = 0
                self.status.set("FRAME CURRENT")
        except (OSError, ValueError, tk.TclError) as error:
            self.status.set(f"DISPLAY ERROR: {error}".upper())


def main() -> None:
    root = tk.Tk()
    PreviewApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
